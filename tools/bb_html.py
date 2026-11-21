#!/usr/bin/env python3
"""Extend genhtml pages with basic-block totals and source-line annotations.

The source view marks *symbolized PC locations*, not the full LLVM basic-block
boundaries. No original LCOV coverage values or source markup are replaced.
"""

import argparse
from collections import defaultdict
from html import escape
import json
import os
import re
from cfg_graph import render_graphs
from bb_visual import (insert_header_metric, remove_header, render_missing_blocks,
                       VISUAL_CSS, VISUAL_JS)
from pathlib import Path

START = "<!-- BEGIN BB-COVERAGE -->"
END = "<!-- END BB-COVERAGE -->"
LINE_START = "<!-- BEGIN BB-LINE -->"
LINE_END = "<!-- END BB-LINE -->"

# Both classic genhtml and LCOV 2.x use a lineNum span for source line numbers.
LINE_TAG = re.compile(
    r'(<span\b[^>]*\bclass\s*=\s*["\'][^"\']*\blineNum\b[^"\']*["\'][^>]*>)(.*?)(</span\s*>)',
    flags=re.I | re.S,
)


def coverage_color(covered, total):
    percent = 100 * covered / total if total else 0
    return "#41ae4a" if percent >= 90 else "#e4a51c" if percent >= 75 else "#d9534f"


def metric(covered, total, *, source=False, placed=None, missed_anchor=None, notice=None,
           embedded=False, missing_blocks=None, visible_lines=None):
    percent = 100 * covered / total if total else 0.0
    color = coverage_color(covered, total)
    missing = (total - placed) if placed is not None else 0
    if missing < 0:
        raise ValueError("More placed blocks than total blocks")
    tools = ""
    if source:
        tools = '''
  <div class="bb-toolbar" role="group" aria-label="Basic block markers">
    <span class="bb-toolbar-label">Source markers:</span>
    <button class="bb-filter bb-active" type="button" data-bb-filter="all" aria-pressed="true">All blocks</button>
    <button class="bb-filter" type="button" data-bb-filter="missed" aria-pressed="false">Uncovered only</button>
'''
        if missed_anchor:
            tools += f'    <a class="bb-next" href="#{escape(missed_anchor, quote=True)}">First uncovered block</a>\n'
        tools += '''  </div>
  <dialog class="bb-dialog" id="bb-dialog">
    <h3>Instrumented basic block</h3>
    <dl>
      <dt>Block</dt><dd id="bb-detail-label"></dd>
      <dt>Function</dt><dd id="bb-detail-function"></dd>
      <dt>PC / module</dt><dd id="bb-detail-pc"></dd>
      <dt>Source line</dt><dd id="bb-detail-line"></dd>
      <dt>Status</dt><dd id="bb-detail-status"></dd>
    </dl>
    <p><a id="bb-detail-cfg" href="#" hidden>Open function CFG</a></p>
    <form method="dialog"><button type="submit">Close</button></form>
  </dialog>
'''
        if missing:
            tools += (f'  <div class="bb-unplaced">{missing} block(s) have no visible source-line marker '
                      '(line unavailable or missing from HTML). They remain included in the coverage totals.</div>\n')
            if missing_blocks is not None and visible_lines is not None:
                tools += render_missing_blocks(missing_blocks, visible_lines)
        else:
            tools += ('  <div class="bb-hint">The BB markers indicate instrumented PC locations from '
                      'DWARF, not the complete source span of each LLVM basic block.</div>\n')

    if notice:
        tools += f'<div class="bb-unplaced">{escape(notice)}</div>'
    heading = ('' if embedded else
               f'<div class="bb-summary-heading"><span class="bb-summary-label">Basic Block Coverage</span>'
               f'<span class="bb-summary-value">{percent:.1f}%</span>'
               f'<span class="bb-summary-count">{covered} / {total} blocks</span></div>'
               f'<div class="bb-progress" role="progressbar" aria-label="Basic block coverage" '
               f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{percent:.1f}">'
               '<div class="bb-progress-fill"></div></div>')
    classname = 'bb-summary' + (' bb-embedded' if embedded else '')
    if embedded and not (source or notice):
        classname += ' bb-no-tools'
    return f'''{START}
<style>
.bb-summary {{font: 13px Arial,sans-serif; color: #222; margin: 12px 16px; padding: 11px 14px; border: 1px solid #aaa; background: #f7f7f7; max-width: 900px; box-sizing: border-box}}
.bb-summary * {{box-sizing: border-box}}
{VISUAL_CSS}
.bb-summary-heading {{display: flex; align-items: baseline; flex-wrap: wrap; gap: 14px}}
.bb-summary-label {{font-weight: bold}}
.bb-summary-value {{font-weight: bold}}
.bb-summary-count {{color: #444}}
.bb-progress {{height: 11px; background: #dedede; margin-top: 8px; border: 1px solid #ccc}}
.bb-progress-fill {{height: 100%; width: {percent:.2f}%; background: {color}}}
.bb-toolbar {{display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 11px}}
.bb-toolbar-label {{margin-right: 5px}}
.bb-filter {{font: inherit; padding: 4px 9px; border: 1px solid #aaa; background: #fff; color: #222; cursor: pointer}}
.bb-filter.bb-active {{border-color: #555; background: #ddd; font-weight: bold}}
.bb-next {{margin-left: 8px; color: #154e88}}
.bb-hint,.bb-unplaced {{margin-top: 9px; font-size: 12px; color: #555}}
.bb-unplaced {{color: #8a351b}}
.bb-gutter {{display: inline-block; width: 18ch; max-width: 18ch; vertical-align: baseline; white-space: nowrap; overflow: hidden; color: #333; font: 11px/1.35 monospace}}
.bb-gutter:hover,.bb-gutter:focus-within {{overflow: visible; position: relative; z-index: 2; background: #fff; width: auto; max-width: none; margin-right: 0}}
.bb-marker {{display: inline-block; padding: 0 3px; margin: 0 1px; border: 1px solid; border-radius: 2px; font: 10px/1.4 monospace; white-space: nowrap; vertical-align: baseline; cursor: help}}
.bb-hit {{background: #e5f4e7; border-color: #76b982; color: #23652c}}
.bb-miss {{background: #fae6e5; border-color: #d78b85; color: #942c27}}
.bb-show-missed .bb-marker.bb-hit {{display: none}}
.bb-gutter:hover .bb-marker {{box-shadow: 0 1px 3px #aaa}}
.bb-marker[role="button"] {{cursor:pointer}}
.bb-marker:focus-visible {{outline:2px solid #174c98}}
.bb-dialog {{font:13px Arial,sans-serif; border:1px solid #777; padding:15px 20px; min-width:340px; max-width:90vw; background:#fff; color:#222}}
.bb-dialog::backdrop {{background:rgba(0,0,0,.25)}}
.bb-dialog h3 {{margin:0 0 12px}}
.bb-dialog dl {{display:grid;grid-template-columns:100px minmax(0,1fr);gap:8px 12px}}
.bb-dialog dd {{overflow-wrap:anywhere;margin:0}}
.bb-dialog dt {{font-weight:bold}}
</style>
<div class="{classname}" data-bb-covered="{covered}" data-bb-total="{total}">
{heading}
{tools}</div>
<script>
document.addEventListener('DOMContentLoaded', function () {{
    var buttons = document.querySelectorAll('.bb-filter');
    buttons.forEach(function (button) {{
        button.addEventListener('click', function () {{
            var missed = button.getAttribute('data-bb-filter') === 'missed';
            document.body.classList.toggle('bb-show-missed', missed);
            buttons.forEach(function (item) {{
                var active = item === button;
                item.classList.toggle('bb-active', active);
                item.setAttribute('aria-pressed', String(active));
            }});
        }});
    }});
    {VISUAL_JS}
    var dialog = document.getElementById('bb-dialog');
    if (dialog) {{
        function openBlock(marker) {{
            var fields = {{label: marker.textContent, function: marker.dataset.bbFunction || 'Unknown',
                pc: marker.dataset.bbPc || 'Unknown', line: marker.dataset.bbLine || 'Unknown',
                status: marker.dataset.bbHit === '1' ? 'Covered' : 'Uncovered'}};
            Object.keys(fields).forEach(function (key) {{
                document.getElementById('bb-detail-' + key).textContent = fields[key];
            }});
            var link = document.getElementById('bb-detail-cfg');
            if (marker.dataset.bbCfg) {{
                link.href = marker.dataset.bbCfg;
                link.hidden = false;
            }} else {{
                link.removeAttribute('href');
                link.hidden = true;
            }}
            dialog.showModal();
        }}
        document.querySelectorAll('.bb-marker[role="button"]').forEach(function (marker) {{
            marker.addEventListener('click', function () {{openBlock(marker);}});
            marker.addEventListener('keydown', function (e) {{
                if (e.key === 'Enter' || e.key === ' ') {{e.preventDefault(); openBlock(marker);}}
            }});
        }});
    }}
}});
</script>
{END}'''


def page_source(page, sources):
    if not page.name.endswith(".gcov.html"):
        return None
    source_name = page.name[:-len(".gcov.html")]
    candidates = [path for path in sources if Path(path).name == source_name]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        ranked = []
        for path in candidates:
            count = 0
            for a, b in zip(reversed(page.parts[:-1]), reversed(Path(path).parent.parts)):
                if a != b:
                    break
                count += 1
            ranked.append((count, path))
        ranked.sort(reverse=True)
        if len(ranked) == 1 or ranked[0][0] > ranked[1][0]:
            return ranked[0][1]
        raise ValueError(f"Ambiguous source for {page}: {candidates}")
    return None


def validate_entry(source, entry):
    covered, total = entry["covered"], entry["total"]
    if not isinstance(covered, int) or not isinstance(total, int) or not 0 <= covered <= total:
        raise ValueError(f"Invalid BB counts in {source}")
    blocks = entry.get("blocks", [])
    ids = set()
    for block in blocks:
        if not isinstance(block.get("hit"), bool) or not isinstance(block.get("line"), int) or block["line"] < 0:
            raise ValueError(f"Invalid block in {source}: {block}")
        if not isinstance(block.get("id"), str) or not block["id"] or block["id"] in ids:
            raise ValueError(f"Duplicate or invalid block ID in {source}")
        ids.add(block["id"])
    if blocks and (len(blocks) != total or sum(b["hit"] for b in blocks) != covered):
        raise ValueError(f"BB counts disagree with block records in {source}")
    return blocks


def add_source_markers(content, blocks, links=None):
    """Add individual BB chips after lineNum spans; preserve LCOV source HTML."""
    links = links or {}
    by_line = defaultdict(list)
    for i, block in enumerate(sorted((b for b in blocks if b["line"] > 0),
                                      key=lambda b: (b["line"], b["id"])), 1):
        by_line[block["line"]].append((i, block))

    # Source annotations are also removed before repeat injection (idempotence).
    content = re.sub(re.escape(LINE_START) + r".*?" + re.escape(LINE_END), "", content, flags=re.S)
    displayed = set()
    first_missed = None

    def mark(m):
        nonlocal first_missed
        raw = re.sub(r"<[^>]*>", "", m.group(2)).strip()
        if not raw.isdecimal():
            return m.group(0)
        line = int(raw)
        if line in displayed:
            return m.group(0)
        displayed.add(line)
        parts = []
        for ordinal, block in by_line.get(line, []):
            hit = block["hit"]
            if not hit and first_missed is None:
                first_missed = f"bb-line-{line}"
            status = "covered" if hit else "uncovered"
            tooltip = escape(f"BB{ordinal}: {status} | {block['id']} | line {line}", quote=True)
            label = f"BB{ordinal}"
            function = block.get("function", "")
            cfg_base = links.get(function, "")
            cfg_url = cfg_base + "#node-" + label if cfg_base else ""
            parts.append(f'<span class="bb-marker {"bb-hit" if hit else "bb-miss"}" '
                         f'role="button" tabindex="0" data-bb-hit="{1 if hit else 0}" '
                         f'data-bb-pc="{escape(block["id"], quote=True)}" '
                         f'data-bb-function="{escape(function, quote=True)}" '
                         f'data-bb-line="{line}" data-bb-cfg="{escape(cfg_url, quote=True)}" '
                         f'title="{tooltip}" aria-label="{tooltip}">{label}</span>')
        suffix = f' id="bb-line-{line}"' if parts else ""
        gutter = f'{LINE_START}<span class="bb-gutter"{suffix}>{"".join(parts)}</span>{LINE_END}'
        return m.group(0) + gutter

    content, rows = LINE_TAG.subn(mark, content)
    placed = sum(len(v) for line, v in by_line.items() if line in displayed)
    return content, placed, first_missed, rows


def inject(report_path, output):
    data = json.loads(report_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported bb-report schema")
    sources = data["files"]
    for source, entry in sources.items():
        validate_entry(source, entry)

    html_pages = sorted(output.rglob("*.html"))
    if not html_pages:
        raise ValueError(f"No genhtml pages in {output}")
    source_pages = {}
    for page in html_pages:
        source = page_source(page.relative_to(output), sources)
        if source:
            source_pages[page] = source
    represented = set(source_pages.values())
    missing = set(sources) - represented
    if missing:
        raise ValueError(f"genhtml did not render {len(missing)} mapped source(s): {sorted(missing)}")

    graph_paths, graph_count = render_graphs(data.get("cfg", []), output,
                                             {source: page for page, source in source_pages.items()})
    changed = 0
    total_marked = 0
    total_unplaced = 0
    for page in html_pages:
        source = source_pages.get(page)
        if source:
            counts = [sources[source]]
        elif page.name.startswith("index"):
            counts = [sources[s] for source_page, s in source_pages.items()
                      if source_page.parent == page.parent or page.parent in source_page.parents]
        else:
            continue
        covered = sum(c["covered"] for c in counts)
        total = sum(c["total"] for c in counts)
        if not total:
            continue
        content = page.read_text(encoding="utf-8")
        content = re.sub(r"\n?" + re.escape(START) + r".*?" + re.escape(END), "", content, flags=re.S)
        content = re.sub(re.escape(LINE_START) + r".*?" + re.escape(LINE_END), "", content, flags=re.S)
        content = remove_header(content)
        placed = None
        visible_lines = None
        first_missed = None
        if source:
            blocks = sources[source].get("blocks", [])
            if blocks:
                links = {fn: os.path.relpath(dest, page.parent).replace(os.sep, "/")
                         for (src, fn), dest in graph_paths.items() if src == source}
                content, placed, first_missed, rows = add_source_markers(content, blocks, links)
                # A matching source file with no lineNum elements is not a readable
                # annotated source report. Fail instead of silently omitting marks.
                if rows == 0:
                    raise ValueError(f"No LCOV source line numbers found on {page}; cannot mark basic blocks")
                visible_lines = {int(re.sub(r"<[^>]*>", "", m.group(2)).strip())
                                 for m in LINE_TAG.finditer(content)
                                 if re.sub(r"<[^>]*>", "", m.group(2)).strip().isdecimal()}
                total_marked += placed
                total_unplaced += total - placed
            else:
                # Compatibility with summary-only reports: no block locations.
                placed = 0
                total_unplaced += total

        notice = None
        instrument = data.get('instrumentation', {})
        if page == output / 'index.html' and instrument:
            missing = instrument.get('unresolved', 0)
            outside = instrument.get('outside_lcov', 0)
            if missing or outside:
                notice = (f'{missing} instrumented PC(s) lack source attribution; '
                          f'{outside} map to sources outside LCOV. '
                          'Project/file totals include only PCs mapped to LCOV source files. '
                          'Inspect bb_coverage.json for full instrumentation totals.')
        content, embedded = insert_header_metric(content, covered, total)
        rendered = metric(covered, total, source=bool(source), placed=placed,
                          missed_anchor=first_missed, notice=notice, embedded=embedded,
                          missing_blocks=sources[source].get('blocks') if source else None,
                          visible_lines=visible_lines)
        content, num = re.subn(r"(<body\b[^>]*>)", lambda m: m.group(1) + "\n" + rendered,
                               content, count=1, flags=re.I)
        if not num:
            raise ValueError(f"HTML lacks body element: {page}")
        page.write_text(content, encoding="utf-8")
        changed += 1
    if not changed:
        raise ValueError("No HTML pages received BB coverage")
    print(f"Added BB coverage to {changed} HTML pages; {total_marked} source markers; {total_unplaced} without visible source location; {graph_count} CFG pages")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    inject(args.report.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
