#!/usr/bin/env python3
"""Validate raw PC accounting, per-file counts and LLVM source mapping.

In strict mode, a demonstration fails if even one instrumented PC is missing
from the LCOV-scoped statistics. Without strict mode, excluded PCs remain
explicitly reported rather than being silently omitted from the denominator.
"""
import argparse
import json
from pathlib import Path


def verify(report, *, strict=False):
    if report.get('schema_version') != 1:
        raise AssertionError('Unsupported coverage report schema')
    inst = report.get('instrumentation')
    if not isinstance(inst, dict):
        raise AssertionError('Missing total instrumentation accounting')
    seen = set()
    covered = total = 0
    for source, entry in report['files'].items():
        records = entry['blocks']
        if entry['total'] != len(records) or entry['covered'] != sum(x['hit'] for x in records):
            raise AssertionError(f'File counters disagree with blocks: {source}')
        for block in records:
            if block['id'] in seen:
                raise AssertionError(f'Duplicate instrumented PC across files: {block["id"]}')
            seen.add(block['id'])
        covered += entry['covered']
        total += entry['total']
    if report['summary'] != {'covered': covered, 'total': total}:
        raise AssertionError('Project totals disagree with per-file totals')
    outside = {b['id'] for b in report['outside_lcov']}
    unresolved = set(report['unresolved'])
    if seen.intersection(outside | unresolved) or outside.intersection(unresolved):
        raise AssertionError('A PC occurs in multiple attribution categories')
    if inst['total'] != total + len(outside) + len(unresolved):
        raise AssertionError('Some instrumented PCs are unaccounted for')
    if inst['mapped_total'] != total or inst['mapped_covered'] != covered:
        raise AssertionError('Incorrect mapped PC totals')
    if inst['unresolved'] != len(unresolved) or inst['outside_lcov'] != len(outside):
        raise AssertionError('Incorrect mapping diagnostics')
    if inst['covered'] != covered + inst['excluded_covered']:
        raise AssertionError('Incorrect covered PC accounting')
    if not 0 <= inst['covered'] <= inst['total']:
        raise AssertionError('Invalid overall coverage')
    if not 0 <= inst['excluded_covered'] <= len(outside) + len(unresolved):
        raise AssertionError('Invalid excluded coverage count')
    if strict and (outside or unresolved):
        raise AssertionError(f'Strict source attribution failed: '
                             f'{len(unresolved)} unresolved, {len(outside)} outside LCOV')
    print(f"Instrumentation OK: {inst['covered']}/{inst['total']} raw PCs, "
          f"{covered}/{total} mapped to LCOV; "
          f"{len(unresolved)} unresolved, {len(outside)} outside LCOV")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--strict-mapping', action='store_true')
    args = parser.parse_args()
    verify(json.loads(args.report.read_text(encoding='utf-8')), strict=args.strict_mapping)


if __name__ == '__main__':
    main()
