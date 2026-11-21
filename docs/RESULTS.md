# Результаты проверки версии v8

Тестовая платформа: Debian GNU/Linux 13 (trixie) на ARM64 (`aarch64`), UTM на Mac M1.
Компиляция: Clang/LLVM 19; LCOV 2.0-1; Python 3.13.5.
Результаты подтверждены запуском на виртуальной машине 21 ноября 2026 г.

## Команды

```bash
make test
bash scripts/check_runtime.sh
bash scripts/demo.sh
```

## Автоматические проверки

- В проверенном прогоне v8 на Debian: **33 Python-теста, OK**
- После добавления универсального CLI и документации: **41 Python-тест, OK** в локальной среде; полный CLI-прогон с `genhtml` на Debian теперь подтвержден ниже
- Runtime: **9/10 (90%)** блоков за три запуска; 0 `unmapped` и 0 `outside LCOV`
- `Instrumentation OK` на обеих библиотеках; все исходные PC учтены
- `Compatibility OK`: 16 HTML-страниц cJSON и 16 страниц inih с идентичными данными покрытия
- `Extended report OK`: счетчики, метки и встроенная BB-метрика
- `Source-line audit`: количество видимых меток и блоков без номера строки


## Независимый сценарий `inih-walkthrough`

Отдельно на Debian 13 ARM64 выполнен универсальный сценарий с `scripts/coverage_project.py` (без `demo.sh`):

```bash
python3 scripts/coverage_project.py build inih-walkthrough \
    --source third_party/inih/ini.c \
    --source demos/inih_driver.c \
    --include third_party/inih
python3 scripts/coverage_project.py run inih-walkthrough -- 0
python3 scripts/coverage_project.py run inih-walkthrough -- 1
python3 scripts/coverage_project.py run inih-walkthrough -- 2
python3 scripts/coverage_project.py report inih-walkthrough --strict-mapping
```

Результат: 3 запуска, **87/128 BB (68,0%)**, 0 `unmapped`, 0 `outside LCOV`; `Instrumentation OK`, `Compatibility OK` (16 страниц), `Extended report OK` (51 метка), аудит 77 BB без номера DWARF-строки (47 выполнено). `llvm-cov` также показал 149/188 Lines, 10/12 Functions и 50/94 Branches. [Порядок действий и снимки](WALKTHROUGH.md).

Снимки хранятся в `docs/screenshots/`. Часть кадров представляет **свой пример `inih-walkthrough`**, а не исходный `demo.sh`, хотя итоговые числа BB совпадают. Совместимость проверена отдельно для каждого сценария.

## Покрытие сторонних проектов

| Показатель | cJSON v1.7.19 | inih r62 |
|---|---:|---:|
| Тестовых запусков | 5 | 3 |
| Basic Blocks покрыто | 311 / 1324 | 87 / 128 |
| Basic Block Coverage | 23,49% | 67,97% |
| Всего функций в CFG | 114 | 12 |
| Видимых BB-меток | 629 | 51 |
| Без строки DWARF | 695 | 77 |
| Из них покрытых | 164 | 47 |
| Известная строка отсутствует в HTML | 0 | 0 |
| Не сопоставлены с LCOV-файлами | 0 | 0 |
| Совпадение HTML-таблиц с исходным genhtml | 16 / 16 | 16 / 16 |

`BB` без строки DWARF учитываются в статистике и доступны через раскрываемый перечень
в HTML. Их не окрашивают на произвольных строках исходного C-кода.
Серые узлы CFG — **неподтвержденные связи LLVM IR с runtime PC**,
а не обязательно невыполненные блоки. Ребра CFG показывают возможные переходы,
не факт исполнения перехода.

## Особенность работы LCOV с LLVM

При построении отчетов LCOV сообщает предупреждение `unsupported` об определении
границ функций. Сборка отчета завершается успешно. В тестах применяется
`--rc check_data_consistency=0`: для данного вывода LLVM это отключает
строгую проверку согласованности данных строк и ветвлений. Параметр одинаков
для системного и модифицированного genhtml. Это ограничение необходимо
упомянуть при воспроизведении эксперимента.

## Созданные результаты

```text
build/cjson/coverage.info
build/cjson/bb_coverage.json
build/cjson/source_line_audit.json
build/cjson/html-original/index.html
build/cjson/html-compatible/index.html
build/cjson/html-extended/index.html
build/inih/coverage.info
build/inih/bb_coverage.json
build/inih/source_line_audit.json
build/inih/html-original/index.html
build/inih/html-compatible/index.html
build/inih/html-extended/index.html
```

Директория `build/` генерируется повторно и исключена из Git.

## Публикация результатов без сборки

После успешного `scripts/demo.sh` выполнить:

```bash
python3 scripts/publish_reports.py
```

Скрипт копирует в `docs/reports/{cjson,inih}/` по три варианта
HTML (`original`, `compatible`, `extended`) и помещает в `docs/index.html`
навигацию по всем шести наборам отчетов. Готовые HTML-файлы являются
снимком проверенного запуска, а не альтернативной системой сбора данных.
Для воспроизведения конкретных чисел необходимы те же версии инструментов,
исходных проектов и входных сценариев.

В публикуемый каталог также включаются тексты лицензий сторонних библиотек.
Ссылки на отчеты после включения GitHub Pages доступны без клонирования
репозитория и без установки LLVM/LCOV.
