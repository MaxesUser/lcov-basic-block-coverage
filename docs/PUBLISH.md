# Публикация отчетов и GitHub Pages

## 1. Воспроизводимый прогон на Debian

```bash
cd ~/share/bb-genhtml-bonus1
make test
bash scripts/check_runtime.sh
bash scripts/demo.sh
```

В этом сценарии запускаются ровно пять входов для cJSON и три для inih.
Оба проекта скачиваются по фиксированным тегам (`v1.7.19`, `r62`).
Тестовые драйверы находятся в `demos/`, оригинальные проекты — в
игнорируемой Git директории `third_party/`.

## 2. Статические HTML-отчеты

```bash
python3 scripts/publish_reports.py
```

Команда повторно проверяет совпадение стандартных данных оригинального и
модифицированного genhtml, покрытие и BB-метки, затем копирует **целые**
HTML-каталоги в `docs/reports/`, сохраняя относительные ссылки на CSS, CFG,
страницы исходников и ресурсы LCOV. В `docs/` автоматически создаются
`index.html` и `.nojekyll`.

```text
docs/
  index.html
  .nojekyll
  reports/
    cjson/
      original/index.html
      compatible/index.html
      extended/index.html
      UPSTREAM-LICENSE.txt
    inih/
      original/index.html
      compatible/index.html
      extended/index.html
      UPSTREAM-LICENSE.txt
```

Тексты лицензий обеих библиотек включаются в публикацию, так как HTML-отчеты
воспроизводят их исходный код.

Локальная проверка:

```bash
python3 -m http.server 8000 --directory docs
```

В Firefox открыть `http://127.0.0.1:8000/`. Проверить ссылки на все шесть
вариантов, переходы на исходники и CFG, подсветку BB, раскрытие блока без
номера строки. Остановить сервер `Ctrl+C`.

При повторном запуске публикации `docs/reports/` **заменяется полностью**
на актуальные отчеты. Остальные файлы в `docs/` (README, снимки экрана,
инструкции) сохраняются.

## 3. Шесть скриншотов

Сохранить реальные кадры из Firefox в `docs/screenshots/`:

- `cjson-original.png` — исходная сводка LCOV без BB
- `cjson-summary.png` — расширенная сводка LCOV с BB
- `cjson-source.png` — зеленые и красные BB-метки на `cJSON.c`
- `cjson-cfg.png` — граф с началом/выходом и ветвлением
- `cjson-unknown-blocks.png` — раскрытый список блоков без номера строки
- `inih-summary.png` — расширенная сводка второго проекта

Выберите удобный масштаб браузера и не обрезайте заголовок отчета.

## 4. Запись среды для воспроизведения

```bash
{
  date -Is
  cat /etc/os-release | grep PRETTY_NAME
  uname -m
  clang-19 --version | head -n 1
  llvm-cov-19 --version | head -n 2
  lcov --version
  genhtml --version
  git -C third_party/cJSON rev-parse HEAD
  git -C third_party/inih rev-parse HEAD
} > test-results/04-environment.log
```

Сравнить с `docs/RESULTS.md` и при необходимости обновить документ.
`test-results/` исключен из Git: в логах могут содержаться локальные пути.

## 5. Git и GitHub Pages

Создайте **пустой** GitHub-репозиторий `lcov-basic-block-coverage`
(без автогенерации README). Для Pages по ссылке без авторизации удобнее
публичный репозиторий; не выкладывайте персональные данные и приватные ключи.

Перед первым коммитом:

```bash
git status --short
git add README.md Makefile .gitignore .gitattributes runtime tools scripts demos tests docs
git diff --cached --stat
git status --short
```

Проверьте, что в индексе нет `build/`, `third_party/`, `bin/genhtml`,
`.venv/` и `test-results/`. Затем:

```bash
git commit -m "Add LLVM basic block coverage and reproducible HTML reports"
git remote add origin git@github.com:USERNAME/lcov-basic-block-coverage.git
git push -u origin main
```

Если репозиторий еще не инициализирован, перед коммитом выполните
`git init -b main` и настройте `git config user.name` / `user.email`.
Если SSH не настроен, создайте отдельный ключ `ssh-keygen -t ed25519`,
добавьте **только публичный** ключ в GitHub Settings → SSH and GPG keys
и проверьте `ssh -T git@github.com`.

После push откройте репозиторий → **Settings → Pages**, выберите
`Deploy from a branch`, ветка `main`, каталог `/docs`, нажмите `Save`.
Адрес сайта GitHub покажет в настройках Pages (обычно
`https://USERNAME.github.io/lcov-basic-block-coverage/`).

**Важно:** у репозитория может быть публичный сайт Pages, даже когда сам
репозиторий не общедоступен. Публикуйте только материалы, которые можно
показывать без авторизации.

## 6. Замечания

- HTML является снимком конкретного запуска; при изменении исходников и
  входных данных сначала повторите `demo.sh`, затем `publish_reports.py`
- `genhtml --rc check_data_consistency=0` отключает часть строгих проверок
  согласованности LCOV/LLVM; объяснение находится в основном README
- Инструментированные BB без строки DWARF остаются в статистике и списке,
  но им не назначаются фиктивные строки кода
- Проверка совместимости сравнивает данные покрытия в таблицах HTML,
  а не побайтовую идентичность файлов

Сценарий применения к произвольному проекту находится в [USAGE.md](USAGE.md), а подробный пример с входными данными cJSON/inih — в [EXAMPLES.md](EXAMPLES.md).
