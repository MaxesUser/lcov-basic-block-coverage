"""LCOV-aligned BB summary row and inspectable unattributed source-line PCs.

The original coverage table is left untouched; we clone its last coverage
metric row and replace only the cloned cell content. Unknown HTML layouts
fall back to a standalone BB summary. No PC positions are guessed.
"""

from html import escape, unescape
import re

HEADER_START = '<!-- BEGIN BB-HEADER -->'
HEADER_END = '<!-- END BB-HEADER -->'


def remove_header(content):
    return re.sub(r'\n?' + re.escape(HEADER_START) + r'.*?' + re.escape(HEADER_END),
                  '', content, flags=re.S)


def insert_header_metric(content, covered, total):
    """Return (HTML, success); retain LCOV's own metric column order."""
    content = remove_header(content)
    rows = list(re.finditer(r'<tr\b[^>]*>.*?</tr\s*>', content, flags=re.I | re.S))
    for wanted in ('Branches', 'Functions', 'Lines'):
        for row in rows:
            original = row.group(0)
            cells = list(re.finditer(r'<td\b[^>]*>.*?</td\s*>', original, flags=re.I | re.S))
            if len(cells) < 4:
                continue
            def txt(cell):
                return unescape(re.sub(r'<[^>]*>', '', cell)).strip()
            index = next((i for i, cell in enumerate(cells)
                          if re.fullmatch(wanted + r'\s*:', txt(cell.group(0)), flags=re.I)), None)
            if index is None or len(cells) - index < 4:
                continue
            values = [txt(c.group(0)) for c in cells[index + 1:index + 4]]
            pct_indices = [i for i, val in enumerate(values) if '%' in val]
            if len(pct_indices) != 1:
                continue
            numeric = [(i, int(re.sub(r'[\s,]', '', val))) for i, val in enumerate(values)
                       if i not in pct_indices and re.fullmatch(r'[\d\s,]+', val)]
            if len(numeric) != 2:
                continue
            # LCOV 1.x uses Hit/Total/Coverage; LCOV 2.x can reverse it.
            # Resolve the order from the existing data. If values tie,
            # both are identical, so either order is correct.
            total_idx = max(numeric, key=lambda v: v[1])[0]
            hit_idx = min(numeric, key=lambda v: v[1])[0]
            if total_idx == hit_idx:
                total_idx, hit_idx = numeric[0][0], numeric[1][0]
            percent = 100.0 * covered / total if total else 0.0
            style = 'Hi' if percent >= 90 else 'Med' if percent >= 75 else 'Lo'
            bar_color = {'Hi': '#41ae4a', 'Med': '#e4a51c', 'Lo': '#d9534f'}[style]
            changed = []
            for i, cell in enumerate(cells):
                raw = cell.group(0)
                if i == index:
                    value = 'Basic Blocks:'
                elif i == index + 1 + pct_indices[0]:
                    value = (f'{percent:.1f} % <span class="bb-inline-bar" aria-hidden="true">'
                             f'<span style="width:{percent:.2f}%;background:{bar_color}"></span></span>')
                    raw = re.sub('headerCovTableEntry(?:Lo|Med|Hi)?',
                                 'headerCovTableEntry' + style, raw, count=1)
                elif i == index + 1 + total_idx:
                    value = str(total)
                elif i == index + 1 + hit_idx:
                    value = str(covered)
                else:
                    value = '&nbsp;'
                tag = re.search(r'(<td\b[^>]*>)(.*?)(</td\s*>)', raw, flags=re.I | re.S)
                if tag is None:
                    raise ValueError('Malformed LCOV table cell')
                changed.append(tag.group(1) + value + tag.group(3))
            # Retain each cell's exact outer tag, left-side widths, and spacing.
            rebuilt = original[:cells[0].start()]
            for i, cell in enumerate(cells):
                rebuilt += changed[i] + original[cell.end():cells[i + 1].start() if i + 1 < len(cells) else len(original)]
            return content[:row.end()] + '\n' + HEADER_START + rebuilt + HEADER_END + content[row.end():], True
    return content, False


def render_missing_blocks(blocks, visible_lines):
    missing = [b for b in blocks if not b['line'] or b['line'] not in visible_lines]
    if not missing:
        return ''
    no_line = sum(b['line'] == 0 for b in missing)
    no_html = len(missing) - no_line
    hits = sum(b['hit'] for b in missing)
    rows = []
    for block in sorted(missing, key=lambda b: (b['line'], b['id'])):
        full = str(block['id'])
        short = full.rsplit('@', 1)[-1] if '@' in full else full
        hit = block['hit']
        status = 'Covered' if hit else 'Uncovered'
        reason = 'No DWARF line' if block['line'] == 0 else f'Line {block["line"]} not in HTML'
        css = 'bb-hit' if hit else 'bb-miss'
        rows.append(f'<tr data-bb-unplaced-hit="{int(hit)}"><td class="{css}">{status}</td>'
                    f'<td title="{escape(full, quote=True)}">{escape(short)}</td>'
                    f'<td>{escape(str(block.get("function") or "Unknown"))}</td>'
                    f'<td>{escape(reason)}</td></tr>')
    return (f'<details class="bb-unplaced-details" id="bb-unplaced-details">'
            f'<summary>Inspect {len(missing)} blocks without a visible source marker '
            f'({hits} covered)</summary>'
            f'<p>All blocks remain in the coverage denominator. {no_line} have no DWARF source line; '
            f'{no_html} have a source line missing from LCOV HTML. No line numbers were guessed.</p>'
            '<div class="bb-toolbar" role="group" aria-label="Filter blocks without source location">'
            '<button type="button" data-bb-unplaced-filter="all" aria-pressed="true">All</button>'
            '<button type="button" data-bb-unplaced-filter="covered" aria-pressed="false">Covered</button>'
            '<button type="button" data-bb-unplaced-filter="uncovered" aria-pressed="false">Uncovered</button></div>'
            '<div class="bb-unplaced-scroll"><table class="bb-unplaced-table"><thead><tr>'
            '<th>Status</th><th>PC</th><th>Function</th><th>Reason</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></div></details>')


VISUAL_CSS = '''
.bb-summary.bb-embedded {background:transparent;border:0;max-width:none;margin:0 16px;padding:0}
.bb-summary.bb-embedded.bb-no-tools {display:none}
.bb-inline-bar {display:inline-block;width:38px;height:7px;margin-left:6px;background:#eee;border:1px solid #aaa;vertical-align:middle;overflow:hidden}
.bb-inline-bar>span {display:block;height:100%;background:#245eb5}
.bb-unplaced-details {margin-top:10px;border:1px solid #c7cdd4;padding:7px 9px;background:#fff;max-width:980px}
.bb-unplaced-details>summary {cursor:pointer;font-weight:600}
.bb-unplaced-details p {font-size:12px;line-height:1.4;color:#555}
.bb-unplaced-scroll {max-height:310px;overflow:auto}
.bb-unplaced-table {border-collapse:collapse;font:12px monospace;width:100%}
.bb-unplaced-table td,.bb-unplaced-table th {text-align:left;border-bottom:1px solid #ddd;padding:4px 8px;max-width:290px;overflow-wrap:anywhere}
.bb-unplaced-table .bb-hit {color:#23652c;background:#e5f4e7}
.bb-unplaced-table .bb-miss {color:#942c27;background:#fae6e5}
.bb-unplaced-details[data-filter="covered"] tr[data-bb-unplaced-hit="0"],
.bb-unplaced-details[data-filter="uncovered"] tr[data-bb-unplaced-hit="1"] {display:none}
.bb-unplaced-details button[aria-pressed="true"] {background:#ddd;font-weight:600}
'''

VISUAL_JS = '''
    document.querySelectorAll('[data-bb-unplaced-filter]').forEach(function(button) {
        button.addEventListener('click', function() {
            var panel = button.closest('.bb-unplaced-details');
            if (!panel) return;
            panel.dataset.filter = button.getAttribute('data-bb-unplaced-filter');
            panel.querySelectorAll('[data-bb-unplaced-filter]').forEach(function(item) {
                item.setAttribute('aria-pressed', String(item === button));
            });
        });
    });
'''
