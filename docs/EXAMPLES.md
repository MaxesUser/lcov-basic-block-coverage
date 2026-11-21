# Воспроизводимый пример: cJSON и inih

Пример показывает, как инструмент применяется к **двум сторонним C-библиотекам**, а не к специальной программе, написанной только для метрики BB. Для библиотек созданы собственные CLI-драйверы, чтобы контролировать входные сценарии и наблюдать изменение покрытия.

## 1. Автоматический эксперимент

Из корня репозитория:

```bash
make test
bash scripts/check_runtime.sh
bash scripts/demo.sh
```

Скрипт скачивает исходники по фиксированным тегам:

- [cJSON v1.7.19](https://github.com/DaveGamble/cJSON/releases/tag/v1.7.19)
- [inih r62](https://github.com/benhoyt/inih/releases/tag/r62)

После запуска доступны три отчета для каждой библиотеки: `html-original`, `html-compatible`, `html-extended`. Для первого отчета вызывается системный `genhtml`, для второго — измененная версия без `--bb-report`, для третьего — версия с BB Coverage.

### Входные сценарии

| Проект | Аргумент драйвера | Проверяемый сценарий |
|---|---|---|
| cJSON | `'{"value":10}'` | Числовое поле JSON |
| cJSON | `'{"value":"text"}'` | Строковое поле JSON |
| cJSON | `'{"other":null}'` | Объект без ожидаемого поля |
| cJSON | `'[1,2,3]'` | JSON-массив |
| cJSON | `'{broken'` | Некорректный JSON |
| inih | `0` | INI с портом 8080 |
| inih | `1` | Несколько INI-секций |
| inih | `2` | Ошибка синтаксиса INI |

Драйверы: [`demos/cjson_driver.c`](../demos/cjson_driver.c) и [`demos/inih_driver.c`](../demos/inih_driver.c). Их задача — воспроизводимые тестовые входы, а не тестирование всего функционала сторонней библиотеки.

## 2. Пример применения CLI к inih отдельно

Этот раздел демонстрирует тот же инструмент на отдельном проекте, **без вызова `demo.sh`**. Сначала получим upstream-исходники, если они еще не скачаны:

```bash
mkdir -p third_party
[ -f third_party/inih/ini.c ] || \
  git clone --depth 1 --branch r62 https://github.com/benhoyt/inih.git third_party/inih
```

Собираем библиотеку и тестовый драйвер в один исполняемый файл:

```bash
python3 scripts/coverage_project.py build inih-walkthrough \
    --source third_party/inih/ini.c \
    --source demos/inih_driver.c \
    --include third_party/inih
```

Выполняем три запуска **одного** бинарника:

```bash
python3 scripts/coverage_project.py run inih-walkthrough -- 0
python3 scripts/coverage_project.py run inih-walkthrough -- 1
python3 scripts/coverage_project.py run inih-walkthrough -- 2
```

Генерируем покрытие и проверяем все PC:

```bash
python3 scripts/coverage_project.py report inih-walkthrough --strict-mapping
xdg-open build/projects/inih-walkthrough/html-extended/index.html
```

Результаты сохраняются в `build/projects/inih-walkthrough/` и не пересекаются с `build/inih/` основного эксперимента. Входные сценарии совпадают с `demo.sh`; числа покрытия при одинаковых версиях Clang/LLVM и флагах должны быть близки, но могут различаться из-за настроек компиляции и расположения инструментированных PC.

Для cJSON аналогичная команда сборки:

```bash
python3 scripts/coverage_project.py build cjson-walkthrough \
    --source third_party/cJSON/cJSON.c \
    --source demos/cjson_driver.c \
    --include third_party/cJSON \
    --ldflag=-lm
```

Далее аналогично используй `run` для пяти аргументов из таблицы и `report`.

## 3. Результаты зафиксированного прогона

Платформа: Debian 13 ARM64, Clang/LLVM 19. Числа ниже получены при автоматическом `scripts/demo.sh`.

| Показатель | cJSON | inih |
|---|---:|---:|
| Запуски | 5 | 3 |
| Выполненные / всего BB | **311/1324** | **87/128** |
| Покрытие | **23,49%** | **67,97%** |
| Без номера строки DWARF | 695 | 77 |
| Из них выполнено | 164 | 47 |
| PC вне файлов LCOV | 0 | 0 |
| Таблицы стандартного покрытия совпали | 16/16 HTML-страниц | 16/16 HTML-страниц |

Более подробная методика и ограничения — в [RESULTS.md](RESULTS.md).

## 4. Пошаговый пример со скриншотами

Для отдельного запуска через `coverage_project.py` подготовлено [руководство по inih](WALKTHROUGH.md): команды `build / run / report`, реальные значения из терминала, пять скриншотов и проверка совместимости.

## 5. Изображения отчета

Снимки создаются из фактически сгенерированных HTML на Debian и хранятся в [`docs/screenshots/`](screenshots/). Набор включает:

- **cjson-original.png** — стандартные три метрики без BB
- **cjson-summary.png** — четвертая метрика в таблице LCOV
- **cjson-source.png** — цветные метки BB в `cJSON.c`
- **cjson-cfg.png** — граф управления функции с условными переходами
- **cjson-unknown-blocks.png** — блоки без номера строки DWARF
- **inih-summary.png** — сводка второго исходного проекта

Пять реальных снимков отдельного запуска `inih-walkthrough` уже находятся в `docs/screenshots/`. Снимки `cjson-*` из основного эксперимента пока нужно сохранить отдельно. Изображения с другими входными данными нельзя выдавать за результаты `demo.sh`. [Инструкция по подготовке снимков](screenshots/README.md).

## 6. Статические отчеты без сборки

После `bash scripts/demo.sh`:

```bash
python3 scripts/publish_reports.py
python3 -m http.server 8000 --directory docs
```

В браузере открой `http://127.0.0.1:8000/`. Там можно сравнить три режима для каждого проекта. Генератор сохраняет целые каталоги HTML, включая CFG и исходные файлы. Перед публикацией проверь страницы на наличие нежелательных локальных путей или иной информации о среде.
