#!/usr/bin/env python3
"""Render self-contained, navigable CFG pages: simplified or full static LLVM CFG.

Only node hits are observed. Edges mean *possible* control flow, not execution.
The simplified view folds linear chains without removing any branch alternatives.
"""

from collections import defaultdict
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import subprocess


def filename(source, function):
    key = f'{source}\0{function}'.encode('utf-8')
    slug = ''.join(c if c.isalnum() or c in '_-' else '-' for c in function)[:45]
    return f'{slug}-{sha256(key).hexdigest()[:14]}.html'


def dot_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def branches_for(graph):
    if graph.get('branches') is not None:
        return graph['branches']
    return [{'from': a, 'to': b, 'labels': [], 'condition_line': 0, 'condition_text': ''}
            for a, b in graph.get('edges', [])]


def collapsed_groups(graph, limit=8):
    """Collapse only 1-in/1-out chains, never skipping a decision or a join."""
    order = [node['name'] for node in graph['nodes']]
    adj, prev = defaultdict(set), defaultdict(set)
    for edge in branches_for(graph):
        if edge['from'] in order and edge['to'] in order:
            adj[edge['from']].add(edge['to'])
            prev[edge['to']].add(edge['from'])
    used = set()
    groups = []
    # We preserve the original node order; no topological ordering is assumed
    # because CFGs may contain arbitrary backward or irreducible edges.
    for name in order:
        if name in used:
            continue
        group = [name]
        used.add(name)
        while len(group) < limit:
            current = group[-1]
            if len(adj[current]) != 1:
                break
            following = next(iter(adj[current]))
            if following in used or following == order[0] or len(prev[following]) != 1:
                break
            group.append(following)
            used.add(following)
        groups.append(group)
    return groups


def _status(nodes):
    values = [n['hit'] for n in nodes]
    if all(x is True for x in values):
        return 'covered', '#e3f3e7', '#32804b'
    if all(x is False for x in values):
        return 'uncovered', '#fee9e7', '#b2423d'
    if all(x is None for x in values):
        return 'unverified', '#edf0f3', '#8793a0'
    return 'mixed', '#fff3db', '#b58327'


def _label(node, branches):
    # Prefer the source condition over a brace or compiler-generated IR label.
    alternatives = [b.get('condition_text', '') for b in branches
                    if b['from'] == node['name'] and b.get('condition_text')]
    excerpt = alternatives[0] if alternatives else node.get('source_text', '')
    return (excerpt or 'Source location unavailable')[:70]


def _back_edges(start, edge_pairs):
    """DFS ancestor edges are drawn as dashed loop-backs, without reinterpreting hits."""
    adj = defaultdict(list)
    for a, b in edge_pairs:
        adj[a].append(b)
    seen, active, backs = set(), set(), set()
    def visit(node):
        seen.add(node)
        active.add(node)
        for dest in sorted(set(adj[node])):
            if dest in active:
                backs.add((node, dest))
            elif dest not in seen:
                visit(dest)
        active.remove(node)
    visit(start)
    return backs


def build_dot(graph, groups, *, simple):
    nodes = {node['name']: node for node in graph['nodes']}
    group_by = {name: i for i, group in enumerate(groups) for name in group}
    branches = branches_for(graph)
    lines = [
        'digraph CFG {',
        'graph [rankdir=TB, bgcolor="transparent", pad="0.3", nodesep=0.45, '
        'ranksep=0.70, splines=polyline, outputorder=edgesfirst];',
        'node [shape=box, style="rounded,filled", fontname="DejaVu Sans", fontsize=11, '
        'margin="0.20,0.13", penwidth=1.3];',
        'edge [color="#69798a", fontcolor="#475569", fontname="DejaVu Sans", '
        'fontsize=10, arrowsize=0.70, penwidth=1.25];',
        'start [label="ENTRY", shape=oval, fillcolor="#f0f4f8", color="#64748b"];',
        'finish [label="EXIT", shape=oval, fillcolor="#f0f4f8", color="#64748b"];',
        'abort [label="STOP / EXCEPTION", shape=oval, fillcolor="#fff0ed", color="#b2423d"];',
    ]
    for i, group in enumerate(groups):
        parts = [nodes[name] for name in group]
        state, fill, border = _status(parts)
        code = _label(parts[0], branches)
        first = parts[0].get('display_id') or f'IR %{parts[0]["name"]}'
        if len(group) > 1:
            last = parts[-1].get('display_id') or f'IR %{parts[-1]["name"]}'
            summary = f'{first} … {last} · {len(group)} blocks'
        else:
            summary = first
        verified = sum(node['hit'] is True for node in parts)
        missed = sum(node['hit'] is False for node in parts)
        unknown = len(parts) - verified - missed
        stats = f'{verified} covered / {missed} missed' + (f' / {unknown} unknown' if unknown else '')
        line = parts[0].get('line') or 0
        label = f'{summary}  |  line {line or "?"}\n{code}\n{stats}'
        target_id = parts[0].get('display_id') or f'ir-{parts[0]["name"]}'
        attrs = [f'label={dot_quote(label)}', f'fillcolor="{fill}"', f'color="{border}"',
                 f'tooltip={dot_quote(state + ": " + summary)}',
                 f'URL={dot_quote("#node-" + target_id)}', 'target="_self"']
        lines.append(f'g{i} [{", ".join(attrs)}];')

    first = graph['nodes'][0]['name']
    lines.append(f'start -> g{group_by[first]} [penwidth=1.8];')
    aggregate = defaultdict(set)
    for branch in branches:
        a, b = branch['from'], branch['to']
        if a not in group_by or b not in group_by or group_by[a] == group_by[b]:
            continue
        for label in branch.get('labels') or ['']:
            aggregate[(group_by[a], group_by[b])].add(label)
    loops = _back_edges(first, [(a, b) for a, b in graph.get('edges', [])])
    for (a, b), labels in sorted(aggregate.items()):
        real_from, real_to = groups[a][-1], groups[b][0]
        backward = (real_from, real_to) in loops or any((x, y) in loops for x in groups[a] for y in groups[b])
        caption = ', '.join(sorted(x for x in labels if x))
        attrs = [f'label={dot_quote(caption)}'] if caption else []
        if backward:
            attrs += ['style=dashed', 'color="#a16a27"', 'constraint=false']
        lines.append(f'g{a} -> g{b}' + (f' [{", ".join(attrs)}]' if attrs else '') + ';')

    terminals = graph.get('terminals', {})
    # Fall back to topology for legacy graphs which have no explicit return kind.
    outgoing = {edge['from'] for edge in branches}
    for index, group in enumerate(groups):
        kinds = set().union(*(set(terminals.get(name, [])) for name in group))
        if 'ret' in kinds:
            lines.append(f'g{index} -> finish;')
        if kinds.intersection({'resume', 'unreachable'}):
            lines.append(f'g{index} -> abort [style=dashed];')
        if not kinds and not any(name in outgoing for name in group):
            lines.append(f'g{index} -> finish;')
    if not any('resume' in x or 'unreachable' in x for x in terminals.values()):
        lines.append('abort [style=invis];')
    lines.append('}')
    return '\n'.join(lines)


def _svg(dot_source, dot='dot'):
    result = subprocess.run([dot, '-Tsvg'], input=dot_source, capture_output=True,
                            text=True, check=True)
    svg = result.stdout
    start = svg.find('<svg')
    if start < 0:
        raise ValueError('Graphviz did not produce SVG')
    return svg[start:]


def render_one(graph, target, source_page, dot='dot'):
    nodes = graph['nodes']
    if not nodes:
        return
    small = collapsed_groups(graph)
    # The simple view groups only straight-line sections; the full view keeps
    # each instrumented block, and both preserve all conditional branches.
    small_svg = _svg(build_dot(graph, small, simple=True), dot=dot)
    full_svg = _svg(build_dot(graph, [[n['name']] for n in nodes], simple=False), dot=dot)
    counts = {'covered': sum(n['hit'] is True for n in nodes),
              'uncovered': sum(n['hit'] is False for n in nodes),
              'unverified': sum(n['hit'] is None for n in nodes)}
    back = escape(os.path.relpath(source_page, target.parent).replace(os.sep, '/'), quote=True)
    title = escape(f'{Path(graph["source"]).name}: {graph["function"]}')
    details = []
    for i, n in enumerate(nodes, 1):
        label = n.get('display_id') or f'IR %{n["name"]}'
        state = 'covered' if n['hit'] is True else 'uncovered' if n['hit'] is False else 'unverified'
        line = int(n.get('line', 0))
        src_link = f'<a href="{back}#bb-line-{line}">Open source line {line}</a>' if line else 'No source line'
        source_text = escape(n.get('source_text') or '(no source line available)')
        condition_text = escape(n.get('condition_text') or '(not resolved)')
        term = escape(n.get('terminator') or '(not available)')
        details.append(f'''<details class="node-detail" id="node-{escape(label, quote=True)}">
<summary>{escape(label)} <span class="state {state}">{state}</span> · line {line or '?'}</summary>
<div class="detail-body"><p><strong>Source:</strong> <code>{source_text}</code></p>
<p><strong>Condition:</strong> <code>{condition_text}</code></p>
<p><strong>IR block:</strong> <code>%{escape(n['name'])}</code>
 · <strong>PC:</strong> <code>{escape(n['pc'])}</code>
 · <strong>slot:</strong> {escape(str(n.get('slot', '?')))}</p>
<p><strong>Mapping:</strong> {'verified by DWARF' if n['verified'] else 'unverified; status not inferred'}</p>
<pre>{term}</pre><p>{src_link}</p></div></details>''')
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>CFG — {title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font:14px/1.55 Arial,sans-serif;color:#27313d;background:#fff;margin:0}}
header{{border-bottom:1px solid #dee3e8;padding:18px 24px;background:#f9fafc}}
main{{padding:18px 24px;max-width:1450px;margin:auto}}
a{{color:#135b93}}h1{{font-size:20px;margin:8px 0}}h2{{font-size:16px;margin:20px 0 8px}}
.meta{{color:#586675}}.toolbar{{display:flex;gap:8px;align-items:center;margin:14px 0}}
button{{font:inherit;padding:6px 13px;background:#fff;border:1px solid #aebbc7;border-radius:5px;cursor:pointer}}
button[aria-pressed="true"]{{background:#1e4f78;color:white;border-color:#1e4f78}}
.graph{{overflow:auto;border:1px solid #d8dfe6;border-radius:6px;background:#fcfcfd;padding:20px;min-height:220px}}
.graph svg{{display:block;height:auto;max-width:none;margin:auto}}
.graph[hidden]{{display:none}}
.note{{max-width:900px;color:#53616e}}.legend{{display:flex;gap:18px;flex-wrap:wrap}}
.legend b{{font-weight:600}}
.legend-item{{display:inline-flex;align-items:center;gap:6px}}
.legend-swatch{{height:12px;width:12px;border:1px solid;border-radius:3px;display:inline-block}}
.legend-swatch.covered{{background:#e3f3e7;border-color:#32804b}}
.legend-swatch.uncovered{{background:#fee9e7;border-color:#b2423d}}
.legend-swatch.unverified{{background:#edf0f3;border-color:#8793a0}}
.graph-explainer{{margin:8px 0;color:#53616e;font-size:13px}}
.node-detail{{border:1px solid #d8dfe6;margin:7px 0;border-radius:5px;background:#fff}}
.node-detail[open]{{border-color:#8aa4ba}}
.node-detail summary{{cursor:pointer;padding:10px 13px;font-weight:600}}
.detail-body{{padding:0 15px 12px;overflow-wrap:anywhere}}
.detail-body pre{{padding:12px;overflow:auto;background:#f1f4f6;border-radius:4px;font:12px/1.5 monospace}}
.state{{font-size:12px;font-weight:400;padding:3px 6px;border-radius:3px}}
.covered{{background:#e3f3e7;color:#21633a}}.uncovered{{background:#fee9e7;color:#94312b}}
.unverified{{background:#edf0f3;color:#566574}}code{{font-size:12px}}
</style></head><body>
<header><a href="{back}">Back to source code</a><h1>Control-flow graph — {title}</h1>
<div class="meta">LLVM instrumented CFG · {len(nodes)} blocks · {len(graph.get('edges', []))} possible block-to-block transitions</div></header>
<main><div class="legend">
<span class="legend-item"><i class="legend-swatch covered"></i><b>Covered:</b> {counts['covered']}</span>
<span class="legend-item"><i class="legend-swatch uncovered"></i><b>Uncovered:</b> {counts['uncovered']}</span>
<span class="legend-item"><i class="legend-swatch unverified"></i><b>Unverified:</b> {counts['unverified']}</span></div>
<p class="graph-explainer"><strong>Gray does not mean missed:</strong> mapping to runtime PC was not confirmed. Arrows are <strong>possible</strong> transitions, not measured edge hits.</p>
<div class="toolbar" role="group" aria-label="Graph detail">
<button type="button" data-mode="simple" aria-pressed="true">Simplified ({len(small)} groups)</button>
<button type="button" data-mode="full" aria-pressed="false">Full ({len(nodes)} blocks)</button></div>
<div class="graph" data-graph="simple">{small_svg}</div>
<div class="graph" data-graph="full" hidden>{full_svg}</div>
<p class="note">ENTRY is the start of the function. EXIT marks normal return; STOP / EXCEPTION marks exceptional or unreachable termination. True/false/case labels come from LLVM IR terminators. Dashed arrows are loop-back candidates. <strong>Every arrow is a possible transfer, not proof that the edge executed.</strong> A colored node has a validated runtime PC match; gray means no reliable match. Simplified mode folds linear chains but retains every branch alternative.</p>
<h2>Blocks and LLVM details</h2>{''.join(details)}
</main><script>
(function() {{
  var buttons = document.querySelectorAll('button[data-mode]');
  buttons.forEach(function(button) {{
    button.addEventListener('click', function() {{
      var mode = button.getAttribute('data-mode');
      document.querySelectorAll('.graph[data-graph]').forEach(function(graph) {{
        graph.hidden = graph.getAttribute('data-graph') !== mode;
      }});
      buttons.forEach(function(item) {{item.setAttribute('aria-pressed', String(item === button));}});
    }});
  }});
  function focusDetail() {{
    var id = decodeURIComponent(window.location.hash.slice(1));
    if (!id || !id.startsWith('node-')) return;
    var detail = document.getElementById(id);
    if (detail) {{detail.open = true; detail.scrollIntoView({{block:'start'}});}}
  }}
  window.addEventListener('hashchange', focusDetail);
  focusDetail();
}})();
</script></body></html>'''
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding='utf-8')


def render_graphs(graphs, output, source_pages, dot='dot'):
    mapped = {}
    created = 0
    for graph in graphs:
        source, fn = graph['source'], graph['function']
        page = source_pages.get(source)
        if not page or not graph['nodes']:
            continue
        out = output / 'bb-cfg' / filename(source, fn)
        render_one(graph, out, page, dot=dot)
        mapped[(source, fn)] = out
        created += 1
    return mapped, created
