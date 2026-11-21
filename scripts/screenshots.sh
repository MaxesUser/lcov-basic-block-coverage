#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/docs/screenshots"
if command -v chromium >/dev/null 2>&1; then
    BROWSER=chromium
elif command -v chromium-browser >/dev/null 2>&1; then
    BROWSER=chromium-browser
else
    echo 'Chromium not installed. Open HTML in a browser and capture screenshots manually.' >&2
    echo 'Optional: sudo apt install chromium' >&2
    exit 1
fi
for project in cjson inih; do
    for kind in original extended; do
        path="$ROOT/build/$project/html-$kind/index.html"
        [[ -f "$path" ]] || { echo "Missing HTML report: $path" >&2; exit 1; }
        "$BROWSER" --headless --disable-gpu --hide-scrollbars \
            --window-size=1400,1000 \
            --screenshot="$ROOT/docs/screenshots/${project}-${kind}.png" \
            "file://$path" >/dev/null 2>&1
        echo "Screenshot: docs/screenshots/${project}-${kind}.png"
    done
    if [[ "$project" == cjson ]]; then
        source_name='cJSON.c.gcov.html'
    else
        source_name='ini.c.gcov.html'
    fi
    source_page="$(find "$ROOT/build/$project/html-extended" -type f -name "$source_name" -print -quit)"
    if [[ -n "$source_page" ]]; then
        "$BROWSER" --headless --disable-gpu --hide-scrollbars \
            --window-size=1400,1000 \
            --screenshot="$ROOT/docs/screenshots/${project}-source-bb.png" \
            "file://$source_page" >/dev/null 2>&1
        echo "Screenshot: docs/screenshots/${project}-source-bb.png"
    fi
    cfg_page="$(find "$ROOT/build/$project/html-extended/bb-cfg" -type f -name '*.html' -print -quit 2>/dev/null || true)"
    if [[ -n "$cfg_page" ]]; then
        "$BROWSER" --headless --disable-gpu --hide-scrollbars \
            --window-size=1400,1000 \
            --screenshot="$ROOT/docs/screenshots/${project}-cfg.png" \
            "file://$cfg_page" >/dev/null 2>&1
        echo "Screenshot: docs/screenshots/${project}-cfg.png"
    fi
done
