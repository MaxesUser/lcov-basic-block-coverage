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

- Python: **33 теста, OK**
- Runtime: **9/10 (90%)** блоков за три запуска; 0 `unmapped` и 0 `outside LCOV`
- `Instrumentation OK` на обеих библиотеках; все исходные PC учтены
- `Compatibility OK`: 16 HTML-страниц cJSON и 16 страниц inih с идентичными данными покрытия
- `Extended report OK`: счетчики, метки и встроенная BB-метрика
- `Source-line audit`: количество видимых меток и блоков без номера строки

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
