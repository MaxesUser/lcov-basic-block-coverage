# Подключение нового C/C++ проекта

Этот документ показывает, как применить расширение `genhtml` к **другой программе**, собрать покрытие по нескольким входным сценариям и получить HTML с Basic Block Coverage. Программа не обязана быть cJSON или inih.

Для полностью воспроизводимого стороннего примера с фактическими логами и снимками см. [inih: build → run → report](WALKTHROUGH.md).

## 1. Что потребуется от проекта

- Доступные исходники C/C++ и возможность собрать исполняемый файл с Clang 19
- Исполняемая точка входа (`main()`): приложение, CLI или небольшой тестовый драйвер для библиотеки
- Возможность воспроизвести хотя бы два разных тестовых запуска программы
- Linux, `clang-19`, `llvm-19`, `lcov`, `graphviz`, `python3`, Perl и `git`

Для простой программы с одним или несколькими `.c` / `.cpp` файлами используй `scripts/coverage_project.py`. Он не заменяет CMake/Make на больших проектах: для нестандартной сборки см. раздел [Ручная интеграция](#5-ручная-интеграция-с-существующей-системой-сборки).

Установка для Debian 13:

```bash
sudo apt update
sudo apt install -y build-essential clang-19 llvm-19 lcov graphviz python3 git make
```

Команды ниже выполняются **из корня репозитория этого расширения**. Путь к анализируемому проекту может находиться где угодно на диске.

## 2. Сборка C/C++ программы

Однофайловая программа:

```bash
python3 scripts/coverage_project.py build sample \
    --source /absolute/path/to/sample.c
```

Несколько C-файлов и заголовочные каталоги:

```bash
python3 scripts/coverage_project.py build sample \
    --source /path/to/app/main.c \
    --source /path/to/app/logic.c \
    --include /path/to/app/include
```

Несколько C++ файлов (выбор `clang++-19` и линковщика C++ автоматический):

```bash
python3 scripts/coverage_project.py build cpp-sample \
    --source /path/to/main.cpp \
    --source /path/to/library.cpp \
    --include /path/to/include
```

Для дополнительных опций используй повторяющиеся `--cflag=...` и `--ldflag=...`, например `--cflag=-DMODE_TEST` и `--ldflag=-lm`. Значения, начинающиеся с `-`, передавай через знак `=`. Не добавляй вручную `-O2`, если хочешь получать сопоставимый с примером отчет: мы используем `-O0 -g`.

Сценарий компилирует исходники с:

```text
-g -O0 -fprofile-instr-generate -fcoverage-mapping
-fsanitize-coverage=bb,no-prune,inline-bool-flag,pc-table
```

И отдельно компилирует `runtime/bb_runtime.c` **без** SanitizerCoverage. Собранные файлы, LLVM IR и конфигурация сохраняются в `build/projects/sample/`.

**Внимание:** повторная сборка с `--force` удаляет старые профили проекта `sample`. Сведения, полученные из разных бинарных сборок, объединять нельзя.

## 3. Запуск с разными входными данными

```bash
python3 scripts/coverage_project.py run sample -- 10
python3 scripts/coverage_project.py run sample -- 0
python3 scripts/coverage_project.py run sample -- -5
```

Все аргументы после `--` передаются программе. Для программы без аргументов:

```bash
python3 scripts/coverage_project.py run sample
```

Каждый запуск создает два типа данных:

```text
build/projects/sample/raw/bb-<pid>.jsonl
build/projects/sample/profiles/<pid>.profraw
```

`jsonl` содержит PC и булевы флаги выполнения блоков, `profraw` — стандартное покрытие LLVM. При ожидаемом ненулевом коде завершения программы можно указать `--allow-nonzero` **перед** `--`:

```bash
python3 scripts/coverage_project.py run sample --allow-nonzero -- invalid-input
```

Это не гарантирует получение профиля при аварийном завершении (`SIGKILL`, падение процесса): runtime сохраняет данные при штатном выходе через `atexit`.

## 4. Создание HTML и проверка результатов

```bash
python3 scripts/coverage_project.py report sample
```

Сценарий выполняет цепочку:

1. `llvm-profdata merge` объединяет `*.profraw`
2. `llvm-cov export -format=lcov` создает `coverage.info`
3. `bb_merge.py` объединяет BB по уникальному `(module, pc)` и сопоставляет их с исходниками
4. `verify_instrumentation.py` проверяет учет всех PC
5. `bb_cfg.py` строит графы из инструментированного LLVM IR
6. Штатный и модифицированный `genhtml` создают три варианта HTML
7. `compare_compat.py`, `verify_extended.py`, `audit_locations.py` проверяют отчеты

Строгий режим для программ, где **все** PC должны принадлежать файлам LCOV:

```bash
python3 scripts/coverage_project.py report sample --strict-mapping
```

Если часть кода не попала в LCOV или DWARF, отчет все равно содержит диагностические поля `unresolved` и `outside_lcov`. Строгая проверка считает такие записи ошибкой.

Основные файлы:

```text
build/projects/sample/
├── program
├── raw/                  # SanitizerCoverage по запускам
├── profiles/             # профили LLVM по запускам
├── coverage.info         # стандартный LCOV
├── bb_coverage.json      # Basic Block Coverage + CFG
├── source_line_audit.json
├── html-original/        # системный genhtml
├── html-compatible/      # модифицированный genhtml без --bb-report
└── html-extended/        # все четыре метрики
```

Открыть готовый отчет:

```bash
xdg-open build/projects/sample/html-extended/index.html
```

На главной странице доступны Lines / Functions / Branches / Basic Blocks. На страницах исходного кода зеленые и красные метки отражают выполнение BB, а клик по метке открывает детали и CFG. Блоки, у которых нет номера строки DWARF, доступны в отдельном перечне. Стандартное покрытие сравнивается с результатом неизмененного `genhtml`.

### Три состояния покрытия и графа

- **Зеленый BB:** выполнялся хотя бы при одном тестовом входе
- **Красный BB:** не выполнялся ни при одном тестовом входе
- **Серый CFG-узел:** не удалось подтвердить связь узла LLVM IR с runtime PC; это **не** доказательство невыполнения

Стрелки CFG — возможные переходы управления, не измерение фактически пройденных ребер.

## 5. Ручная интеграция с существующей системой сборки

Для проектов с CMake, Make, сгенерированными файлами, нестандартной линковкой или зависимостями удобнее использовать существующую сборку, передав в нее флаги инструментации. Общая схема:

```bash
# Каждый исходный C/C++ модуль, покрытие которого требуется измерять:
clang-19 -g -O0 -fprofile-instr-generate -fcoverage-mapping \
  -fsanitize-coverage=bb,no-prune,inline-bool-flag,pc-table \
  -c /path/to/app.c -o app.o

# Runtime — без -fsanitize-coverage:
clang-19 -g -O0 -c runtime/bb_runtime.c -o bb_runtime.o

# Слинковать все инструментированные объекты вместе с runtime.
clang-19 -g -O0 -fprofile-instr-generate app.o bb_runtime.o -ldl -o app
```

Для C++ используй `clang++-19` при сборке и линковке C++ модулей, а runtime компилируй именно как C. Если проект использует несколько зависимых объектных файлов/библиотек, они тоже должны быть включены в сборку и линковку обычным для проекта способом.

Если нужен **CFG**, сохрани LLVM IR для каждого инструментированного исходника с теми же флагами и исходными файлами:

```bash
clang-19 -g -O0 -fprofile-instr-generate -fcoverage-mapping \
  -fsanitize-coverage=bb,no-prune,inline-bool-flag,pc-table \
  -S -emit-llvm /path/to/app.c -o app.ll
```

Запуск с профилированием (каталоги должны существовать):

```bash
mkdir -p /tmp/bb-example/raw /tmp/bb-example/profiles
BBRAW_DIR=/tmp/bb-example/raw \
LLVM_PROFILE_FILE=/tmp/bb-example/profiles/%p.profraw \
    ./app input1
BBRAW_DIR=/tmp/bb-example/raw \
LLVM_PROFILE_FILE=/tmp/bb-example/profiles/%p.profraw \
    ./app input2
```

Следующий этап:

```bash
llvm-profdata-19 merge -sparse /tmp/bb-example/profiles/*.profraw \
  -o /tmp/bb-example/merged.profdata
llvm-cov-19 export -format=lcov \
  -instr-profile=/tmp/bb-example/merged.profdata ./app \
  > /tmp/bb-example/coverage.info
python3 tools/bb_merge.py \
  --raw-dir /tmp/bb-example/raw \
  --lcov /tmp/bb-example/coverage.info \
  --output /tmp/bb-example/bb_coverage.json
python3 tools/bb_cfg.py \
  --report /tmp/bb-example/bb_coverage.json --ir app.ll
python3 tools/patch_genhtml.py \
  --original "$(command -v genhtml)" --output bin/genhtml
bin/genhtml /tmp/bb-example/coverage.info \
  --branch-coverage --rc check_data_consistency=0 \
  --bb-report /tmp/bb-example/bb_coverage.json \
  --output-directory /tmp/bb-example/html
```

После этого открывай `/tmp/bb-example/html/index.html`. `--rc check_data_consistency=0` используется потому, что экспорт LLVM может конфликтовать со строгой проверкой записей Line/Branch в текущем LCOV. Он отключает соответствующую проверку; это **не** способ исправить ошибочные данные профиля.

Для удобного автоматического сравнения оригинальной и модифицированной версии используй `scripts/coverage_project.py`, который строит все три отчета и проверяет совпадение таблиц.

## 6. Частые проблемы

| Признак | Причина / действие |
|---|---|
| `No bb-*.jsonl files` | Нет вызова инструментированного бинарника или `BBRAW_DIR` не задан / не существует |
| Нет `*.profraw` | Нет `LLVM_PROFILE_FILE` либо процесс завершился до записи профиля |
| `unresolved` / `outside_lcov` ненулевые | Часть PC невозможно отнести к LCOV-файлу; проверь `-g`, список исходников, фильтры LCOV и `bb_coverage.json` |
| У блока нет метки рядом со строкой | В DWARF нет номера строки или такой строки нет в HTML; блок остается в метрике и перечне |
| `genhtml: inconsistent` | Возможна несовместимость проверок LCOV с LLVM; сравни одинаковые входные `.info` и аргументы; см. параметр `check_data_consistency` |
| После изменения исходников пропали совпадения PC | Пересобери и удали профили предыдущего бинарника |
| Сборка со сторонними зависимостями не поддерживается коротким CLI | Используй сборочную систему проекта и ручную интеграцию |

## 7. Пример с открытым исходным кодом

Готовый пример пошагового подключения парсера inih и второго проекта cJSON: [EXAMPLES.md](EXAMPLES.md). Изображения отчетов и графов снимаются непосредственно из результатa запуска на целевой машине: [screenshots/README.md](screenshots/README.md).
