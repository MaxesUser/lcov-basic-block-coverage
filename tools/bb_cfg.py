#!/usr/bin/env python3
"""Recover C/C++ CFG edges from LLVM IR terminators, annotate instrumented PCs.

SanitizerCoverage inserts implementation-only branches when setting flags. They
are traversed, but not shown as user-level decisions. The graph is a static
control-flow graph: no edge is marked as executed. Unknown PC-to-IR matches
remain unknown, never inferred as missed.
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

FUNC = re.compile(r'^define\b.*?@(?P<name>[-\w.$]+)\(.*\)\s*.*\{\s*$')
LABEL = re.compile(r'^\s*(?P<name>[-\w.$]+):\s*(?:;.*)?$')
PC_ENTRY = re.compile(r'ptr\s+(?:@([-\w.$]+)|blockaddress\(@([-\w.$]+),\s*%([-\w.$]+)\))')
DLOC = re.compile(r'^!(\d+)\s*=\s*!DILocation\(line:\s*(\d+)')
DBG = re.compile(r'!dbg\s+!(\d+)')
EDGE = re.compile(r'label\s+%([-\w.$]+)')
TERMINATOR = re.compile(
    r'^\s*(?:(?:%[-\w.$]+)\s*=\s*)?'
    r'(br|switch|indirectbr|invoke|callbr|ret|resume|unreachable|'
    r'catchswitch|catchret|cleanupret)\b'
)
CASE = re.compile(r'i\d+\s+([^,\]\n]+),\s*label\s+%([-\w.$]+)')


def _terminator(instructions):
    """Return the last terminator and its continuation (e.g. switch table)."""
    for index in range(len(instructions) - 1, -1, -1):
        if m := TERMINATOR.match(instructions[index]):
            return m.group(1), '\n'.join(instructions[index:])
    return '', ''


def _successors(op, text):
    labels = EDGE.findall(text)
    if op == 'br' and len(labels) == 2:
        return [(labels[0], 'true'), (labels[1], 'false')]
    if op == 'switch' and labels:
        out = [(labels[0], 'default')]
        cases = text.split('[', 1)[1].rsplit(']', 1)[0] if '[' in text else ''
        out += [(name, f'case {value.strip()}') for value, name in CASE.findall(cases)]
        return out
    if op == 'invoke' and len(labels) == 2:
        return [(labels[0], 'normal'), (labels[1], 'unwind')]
    if op == 'callbr' and labels:
        return [(labels[0], 'normal')] + [(dest, 'indirect') for dest in labels[1:]]
    if op in ('indirectbr', 'catchswitch'):
        return [(dest, 'possible') for dest in labels]
    if op in ('catchret', 'cleanupret'):
        return [(dest, 'next') for dest in labels]
    if op == 'br' and len(labels) == 1:
        return [(labels[0], '')]
    return []


def _source_path(ir_file, lines):
    line = next((x for x in lines[:30] if x.startswith('source_filename = ')), '')
    m = re.search(r'^source_filename\s*=\s*"([^\"]+)"', line)
    if not m:
        return None
    path = Path(m.group(1))
    # The build script enters the project root before calling Clang. Keep this
    # convention, and allow absolute paths from independent callers.
    return str(path.resolve())


def _source_snippet(source_lines, line):
    if not 0 < line <= len(source_lines):
        return ''
    return ' '.join(source_lines[line - 1].strip().split())[:120]


def parse_ir(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    debug = {m.group(1): int(m.group(2)) for line in lines if (m := DLOC.search(line))}
    pc_tables = {}
    for line in lines:
        if 'section "__sancov_pcs"' not in line:
            continue
        matches = PC_ENTRY.findall(line)
        if not matches or not matches[0][0]:
            continue
        fn = matches[0][0]
        pc_tables[fn] = ['entry'] + [target for _, owner, target in matches[1:] if owner == fn]

    source = _source_path(path, lines)
    try:
        source_lines = Path(source).read_text(encoding='utf-8', errors='replace').splitlines() if source else []
    except OSError:
        source_lines = []

    result = {}
    i = 0
    while i < len(lines):
        match = FUNC.match(lines[i])
        if not match:
            i += 1
            continue
        fn = match.group('name')
        i += 1
        body = defaultdict(list)
        current = 'entry'
        body[current] = []
        while i < len(lines) and lines[i].strip() != '}':
            label = LABEL.match(lines[i])
            if label:
                current = label.group('name')
                body[current] = []
            else:
                body[current].append(lines[i])
            i += 1
        i += 1
        if fn not in pc_tables:
            continue
        order = pc_tables[fn]
        if len(set(order)) != len(order) or any(node not in body for node in order):
            continue

        instructions = {}
        node_lines = {}
        internal_flag = {}
        successors = {}
        for node, code in body.items():
            op, term = _terminator(code)
            instructions[node] = {'op': op, 'text': term}
            successors[node] = _successors(op, term)
            # Source attribution matches the first real instruction location,
            # as in v6; the terminator source is stored independently.
            for inst in code:
                if (m := DBG.search(inst)) and m.group(1) in debug:
                    node_lines[node] = debug[m.group(1)]
                    break
            internal_flag[node] = any('@__sancov_gen_' in inst for inst in code)

        targets = set(order)
        edges = defaultdict(set)
        branch_details = {}
        term_types = {}
        # Traverse the instrumentation-internal blocks between two entries.
        # A semantic decision may live in a non-instrumented block: propagate
        # its edge label back to the preceding instrumented entry.
        for start in order:
            queue = [(dest, '' if internal_flag[start] else label, None, None)
                     for dest, label in successors.get(start, [])]
            visited = set()
            while queue:
                dest, branch, cond_line, cond_text = queue.pop()
                key = (dest, branch, cond_line)
                if key in visited:
                    continue
                visited.add(key)
                if dest in targets:
                    edges[(start, dest)].add(branch)
                    if branch or cond_text:
                        branch_details.setdefault((start, dest), (cond_line, cond_text))
                    continue
                if dest not in successors:
                    continue
                op = instructions[dest]['op']
                options = successors[dest]
                meaningful = not internal_flag[dest] and len(options) > 1 and op in (
                    'br', 'switch', 'invoke', 'callbr', 'indirectbr', 'catchswitch')
                location = DBG.search(instructions[dest]['text'])
                line_num = debug.get(location.group(1), 0) if location else 0
                for next_node, edge_label in options:
                    # Prefer the final semantic branch on a path. Any earlier
                    # branch label still represents a possible path; this label
                    # is never interpreted as an observed edge hit.
                    new_label = edge_label if meaningful else branch
                    new_line = line_num if meaningful else cond_line
                    new_text = _source_snippet(source_lines, line_num) if meaningful else cond_text
                    queue.append((next_node, new_label, new_line, new_text))

            # Some returns sit behind an uninstrumented flag-setting suffix.
            # Preserve the terminal kind from the reachable suffix.
            endings = set()
            walk = [start]
            seen = set()
            while walk:
                node = walk.pop()
                if node in seen:
                    continue
                seen.add(node)
                if node != start and node in targets:
                    continue
                op = instructions.get(node, {}).get('op', '')
                if op in ('ret', 'resume', 'unreachable'):
                    endings.add(op)
                walk.extend(dest for dest, _ in successors.get(node, []))
            if endings:
                term_types[start] = sorted(endings)

        branches = []
        for (start, end), labels in sorted(edges.items()):
            condition_line, condition_text = branch_details.get((start, end), (None, None))
            branches.append({'from': start, 'to': end, 'labels': sorted(x for x in labels if x),
                             'condition_line': condition_line or 0,
                             'condition_text': condition_text or ''})
        entries = {}
        for node in order:
            line = node_lines.get(node, 0)
            term = instructions[node]
            term_loc = DBG.search(term['text'])
            condition_line = debug.get(term_loc.group(1), 0) if term_loc else 0
            entries[node] = {
                'line': line,
                'source_text': _source_snippet(source_lines, line),
                'condition_line': condition_line,
                'condition_text': _source_snippet(source_lines, condition_line),
                'terminator': term['text'].strip()[:1500],
                'terminator_kind': term['op'],
            }
        result[fn] = {'order': order,
                      'edges': [(b['from'], b['to']) for b in branches],
                      'branches': branches,
                      'entries': entries,
                      'terminals': term_types,
                      'source': source}
    return result


def _pc(block):
    m = re.search(r'@0x([0-9a-fA-F]+)$', block['id'])
    return int(m.group(1), 16) if m else -1


def attach_cfg(report, ir_files):
    by_function = defaultdict(list)
    for source, entry in report['files'].items():
        for block in entry.get('blocks', []):
            if block.get('function'):
                by_function[(source, block['function'])].append(block)
    display_ids = {}
    for source, entry in report['files'].items():
        visible = sorted((b for b in entry.get('blocks', []) if b['line'] > 0),
                         key=lambda b: (b['line'], b['id']))
        for index, block in enumerate(visible, 1):
            display_ids[(source, block['id'])] = f'BB{index}'
    graphs = []
    diagnostics = []
    for path in ir_files:
        for name, cfg in parse_ir(path).items():
            source_path = cfg['source']
            runtime = sorted(by_function.get((source_path, name), []),
                             key=lambda b: b.get('slot', _pc(b)))
            if not runtime:
                continue
            ordered = cfg['order']
            if len(ordered) != len(runtime) or any('slot' not in b for b in runtime):
                diagnostics.append(f'{source_path}:{name}: PC-table cardinality/slot mismatch')
                continue
            if len({b['slot'] for b in runtime}) != len(runtime):
                diagnostics.append(f'{source_path}:{name}: duplicate PC-table slots')
                continue
            nodes = []
            for ir_node, block in zip(ordered, runtime):
                info = cfg['entries'][ir_node]
                line = info['line']
                verified = bool(line and block['line'] == line)
                nodes.append({
                    'name': ir_node, 'line': block['line'], 'pc': block['id'],
                    'slot': block['slot'], 'display_id': display_ids.get((source_path, block['id']), ''),
                    'hit': block['hit'] if verified else None,
                    'verified': verified, 'source_text': info['source_text'],
                    'condition_line': info['condition_line'],
                    'condition_text': info['condition_text'],
                    'terminator': info['terminator'], 'terminator_kind': info['terminator_kind'],
                })
            graphs.append({'source': source_path, 'function': name,
                           'nodes': nodes, 'edges': cfg['edges'],
                           'branches': cfg['branches'], 'terminals': cfg['terminals']})
    report['cfg'] = graphs
    report['cfg_diagnostics'] = diagnostics
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--ir', type=Path, action='append', required=True)
    args = p.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    attach_cfg(report, args.ir)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    known = sum(node['verified'] for graph in report['cfg'] for node in graph['nodes'])
    unknown = sum(not node['verified'] for graph in report['cfg'] for node in graph['nodes'])
    print(f"CFG: {len(report['cfg'])} functions, {known} verified nodes, {unknown} unverified nodes")
    for warning in report['cfg_diagnostics']:
        print(f'CFG warning: {warning}')


if __name__ == '__main__':
    main()
