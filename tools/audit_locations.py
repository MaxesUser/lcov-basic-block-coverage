#!/usr/bin/env python3
"""Audit mapping quality without guessing source line numbers.

A block can be attributed to a source *file* and counted in BB Coverage even
when DWARF offers no source *line*. PC addresses are not shifted to find a
convenient nearby line: that could assign instructions to a different block.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from bb_html import LINE_TAG, page_source


def audit(data, html=None):
    result = {'files': {}, 'summary': {}}
    pages = {}
    if html is not None:
        for page in html.rglob('*.gcov.html'):
            source = page_source(page.relative_to(html), data['files'])
            if source is not None:
                if source in pages:
                    raise ValueError(f'Duplicate HTML source page: {source}')
                text = page.read_text(encoding='utf-8')
                lines = {int(raw) for m in LINE_TAG.finditer(text)
                         if (raw := re.sub(r'<[^>]*>', '', m.group(2)).strip()).isdecimal()}
                pages[source] = lines
        if set(pages) != set(data['files']):
            raise ValueError('Source pages are missing from HTML output')

    grand = Counter()
    for source, entry in sorted(data['files'].items()):
        counts = Counter()
        blocks = entry['blocks']
        if len(blocks) != entry['total'] or sum(b['hit'] for b in blocks) != entry['covered']:
            raise ValueError(f'Mismatched counters for {source}')
        shown = pages.get(source)
        for block in blocks:
            if block['line'] <= 0:
                kind = 'without_dwarf_line'
            elif shown is not None and block['line'] not in shown:
                kind = 'line_not_in_html'
            else:
                kind = 'visible' if shown is not None else 'with_dwarf_line'
            counts[kind] += 1
            counts[kind + '_covered'] += int(block['hit'])
        counts['total'] = len(blocks)
        counts['covered'] = entry['covered']
        grand.update(counts)
        result['files'][source] = dict(counts)
    summary = data.get('summary', {'total': grand['total'], 'covered': grand['covered']})
    if grand['total'] != summary['total'] or grand['covered'] != summary['covered']:
        raise ValueError('Audit totals disagree with coverage summary')
    result['summary'] = dict(grand)
    result['instrumentation'] = data.get('instrumentation', {})
    result['note'] = ('DWARF line 0 is unknown, not uncovered. Blocks without a usable line '
                      'remain included in BB Coverage. No guessed offsets or addresses are used.')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--html', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    data = json.loads(args.report.read_text(encoding='utf-8'))
    stats = audit(data, args.html)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    s = stats['summary']
    label = 'visible source markers' if args.html else 'with DWARF source lines'
    readable = s.get('visible', 0) if args.html else s.get('with_dwarf_line', 0)
    print(f"Source-line audit: {readable}/{s['total']} {label}; "
          f"{s.get('without_dwarf_line', 0)} without DWARF line "
          f"({s.get('without_dwarf_line_covered', 0)} covered); "
          f"{s.get('line_not_in_html', 0)} missing from HTML")
    for name, fields in stats['files'].items():
        print(f"  {Path(name).name}: {fields['total']} blocks, "
              f"{fields.get('without_dwarf_line', 0)} without DWARF line")


if __name__ == '__main__':
    main()
