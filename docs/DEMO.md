# Демонстрация для защиты (5–7 минут)

## Подготовка

```bash
cd ~/share/bb-genhtml-bonus1
make test
bash scripts/check_runtime.sh
bash scripts/demo.sh
xdg-open build/cjson/html-extended/index.html
```

## Ход демонстрации

1. **Постановка задачи.** Обычный `genhtml` показывает Lines, Functions и Branches. Требуется добавить Basic Blocks без потери старого режима.
2. **Сбор.** Открыть `runtime/bb_runtime.c` и показать обработчики `__sanitizer_cov_bool_flag_init` и `__sanitizer_cov_pcs_init`. Одна инструментированная сборка включает обычный профиль LLVM и SanitizerCoverage.
3. **Объединение.** Показать `tools/bb_merge.py` и `build/cjson/bb_coverage.json`: объединение `hit` между пятью запусками по логическому ИЛИ, без повторного подсчета одного блока.
4. **Сводка.** В `build/cjson/html-extended/index.html` показать Basic Blocks в таблице LCOV: 311/1324 (23,5%).
5. **Исходный код.** Перейти к `cJSON.c` и показать метки выполненных/невыполненных BB. Нажать на метку: появятся детали и ссылка в CFG.
6. **CFG.** Переключить Simplified / Full. Показать ENTRY, EXIT, исходы `true` / `false`. Пояснить, что ребра возможные, а их фактическое прохождение не измеряется.
7. **Непривязанные к строке блоки.** Открыть `Inspect ... blocks without a visible source marker`. Показать PC и статус; объяснить, почему не рисуем недостоверные границы блоков на C-строках.
8. **Совместимость.** Показать `html-original/` и `html-compatible/`, а также строки `Compatibility OK` в терминале. Без `--bb-report` наша версия не изменяет стандартные показатели LCOV.
9. **Второй проект.** Показать сводку inih: 87/128 (68,0%).

## Что подготовить в скриншотах

- `cjson-summary.png` — главная страница, четыре метрики
- `cjson-source.png` — метки BB в исходном коде
- `cjson-cfg.png` — CFG с ветвлением и подписями переходов
- `cjson-unknown-blocks.png` — раскрытый список блоков без строки DWARF
- `inih-summary.png` — второй проект

Скриншоты следует получить на виртуальной машине из реального результата v8.
