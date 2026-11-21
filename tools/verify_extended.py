#!/usr/bin/env python3
"""Check that the generated BB report contains all visibly placeable markers."""

import argparse
import json
import re
from html import unescape
from urllib.parse import unquote, urldefrag
from pathlib import Path
from bb_html import LINE_TAG, page_source

MARK = re.compile(r'<span class="bb-marker bb-(hit|miss)"(?=\s|>)')


def verify(report: Path, output: Path):
    data = json.loads(report.read_text(encoding="utf-8"))
    sources = data["files"]
    found = set()
    marked_total = 0
    cfg_cache = {}
    for page in sorted(output.rglob("*.gcov.html")):
        source = page_source(page.relative_to(output), sources)
        if source is None:
            continue
        found.add(source)
        content = page.read_text(encoding="utf-8")
        entry = sources[source]
        if f'data-bb-covered="{entry["covered"]}" data-bb-total="{entry["total"]}"' not in content:
            raise AssertionError(f"Incorrect BB totals: {page}")
        visible_lines = set()
        for span in LINE_TAG.finditer(content):
            text = re.sub(r'<[^>]*>', '', span.group(2)).strip()
            if text.isdecimal():
                visible_lines.add(int(text))
        expected = [b for b in entry.get("blocks", []) if b["line"] > 0 and b["line"] in visible_lines]
        actual = MARK.findall(content)
        if len(actual) != len(expected):
            raise AssertionError(f"Incorrect BB markers on {page}: {len(actual)} instead of {len(expected)}")
        if actual.count("hit") != sum(b["hit"] for b in expected):
            raise AssertionError(f"Incorrect hit statuses on {page}")
        if actual.count("miss") != sum(not b["hit"] for b in expected):
            raise AssertionError(f"Incorrect miss statuses on {page}")
        if "Uncovered only" not in content:
            raise AssertionError(f"Source filter is missing: {page}")
        missing = [b for b in entry.get('blocks', [])
                   if b['line'] <= 0 or b['line'] not in visible_lines]
        inventory_hits = len(re.findall(r'<tr data-bb-unplaced-hit="1"', content))
        inventory_misses = len(re.findall(r'<tr data-bb-unplaced-hit="0"', content))
        if inventory_hits != sum(b['hit'] for b in missing) or \
                inventory_misses != sum(not b['hit'] for b in missing):
            raise AssertionError(f"Incomplete unattributed PC inventory on {page}")
        if missing and 'bb-unplaced-details' not in content:
            raise AssertionError(f"Missing inspection panel for blocks without a source line: {page}")
        if re.search(r'<td[^>]*>\s*Branches:\s*</td>', content, re.I) and \
                'Basic Blocks:' not in content:
            raise AssertionError(f"Fourth coverage metric missing from LCOV header on {page}")
        # Every clickable source marker must target a real CFG detail panel.
        for raw_link in re.findall(r'data-bb-cfg="([^"]+)"', content):
            link = unescape(raw_link)
            if not link:
                continue
            path, fragment = urldefrag(link)
            graph_file = (page.parent / unquote(path)).resolve()
            if not graph_file.is_relative_to(output.resolve()) or not graph_file.is_file():
                raise AssertionError(f'Invalid CFG target on {page}: {link}')
            if graph_file not in cfg_cache:
                cfg_cache[graph_file] = graph_file.read_text(encoding='utf-8')
            graph_html = cfg_cache[graph_file]
            if ('data-graph="simple"' not in graph_html or
                    'data-graph="full"' not in graph_html or
                    f'id="{fragment}"' not in graph_html):
                raise AssertionError(f'CFG detail target missing: {link}')
        marked_total += len(actual)
    if found != set(sources):
        raise AssertionError(f"Source pages missing: {sorted(set(sources) - found)}")
    if marked_total == 0:
        raise AssertionError("No basic blocks marked in source code")
    index = (output / "index.html").read_text(encoding="utf-8")
    total = sum(e["total"] for e in sources.values())
    covered = sum(e["covered"] for e in sources.values())
    if f'data-bb-covered="{covered}" data-bb-total="{total}"' not in index:
        raise AssertionError("Top-level BB totals do not match the sum of files")
    if re.search(r'<td[^>]*>\s*Branches:\s*</td>', index, re.I) and \
            'Basic Blocks:' not in index:
        raise AssertionError("Fourth coverage metric is missing from the top-level LCOV header")
    print(f"Extended report OK: {len(found)} source file(s), {marked_total} visible BB markers, {covered}/{total} overall")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--html', required=True, type=Path)
    args = parser.parse_args()
    verify(args.report, args.html)


if __name__ == '__main__':
    main()
