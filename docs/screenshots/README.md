# Скриншоты отчетов

Все изображения в этом каталоге получены из реального HTML, сгенерированного расширением `genhtml` в Debian 13 ARM64. Их не подменяют иллюстрациями из другой версии инструмента.

## Сценарий `inih-walkthrough` — файлы уже добавлены

| Файл | Что показывает |
|---|---|
| `inih-walkthrough-summary.png` | Сводная страница: 87/128 BB (68,0%), Lines / Functions / Branches |
| `inih-walkthrough-driver-directory.png` | `demos/`: 14/15 BB (93,3%) |
| `inih-walkthrough-source.png` | `inih_driver.c`, выполненные и невыполненные BB-маркеры, сообщение о 8 блоках без видимой строки |
| `inih-walkthrough-cfg.png` | CFG `main`, возможные переходы и непроверенные привязки |
| `inih-walkthrough-library-directory.png` | `third_party/inih/`: 73/113 BB (64,6%) |

**Ограничение последнего кадра CFG:** снизу видна панель рабочего стола, перекрывающая часть графа. Для окончательной публикации лучше заменить **только** `inih-walkthrough-cfg.png` кадром, где показаны EXIT и весь граф, не меняя исходных данных.

См. [пошаговый сценарий](../WALKTHROUGH.md), который связывает снимки с командами и результатами измерений.

## Основной эксперимент cJSON / inih — что еще можно добавить

Эти кадры относятся к отчетам из `bash scripts/demo.sh` и должны быть сняты **из соответствующих каталогов**:

| Имя | Файл HTML |
|---|---|
| `cjson-original.png` | `build/cjson/html-original/index.html` |
| `cjson-summary.png` | `build/cjson/html-extended/index.html` |
| `cjson-source.png` | `build/cjson/html-extended/` → `cJSON.c` |
| `cjson-cfg.png` | `cJSON.c` → BB → `Open function CFG` |
| `cjson-unknown-blocks.png` | `cJSON.c` → `Inspect ... blocks without a visible source marker` |
| `inih-summary.png` | `build/inih/html-extended/index.html` |

Для статичного снимка без раскрываемых элементов можно использовать:

```bash
bash scripts/screenshots.sh
```

Сложный CFG и раскрытый список блоков проще сохранить вручную в Firefox с подходящим масштабом.

## Просмотр готовых HTML-отчетов

```bash
python3 scripts/publish_reports.py
python3 -m http.server 8000 --directory docs
```

Открыть `http://127.0.0.1:8000/`. В `docs/reports/` копируются полноценные HTML-страницы **основного** эксперимента `demo.sh`, а не отдельного `inih-walkthrough`. Скриншоты не заменяют HTML: по ссылкам доступны исходники, интерактивные метки и CFG.
