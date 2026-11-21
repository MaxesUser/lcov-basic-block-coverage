#!/usr/bin/env python3
"""Merge hit flags from SanitizerCoverage runs and symbolize PCs with LLVM."""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def parse_lcov(path):
    sources = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SF:"):
            sources.add(str(Path(line[3:]).resolve()))
    if not sources:
        raise ValueError(f"LCOV file contains no SF records: {path}")
    return sources


def symbolize(binary, addresses, executable):
    args = [executable, f"--obj={binary}", "--functions=linkage", "--inlining=false"]
    text = "".join(f"0x{pc:x}\n" for pc in addresses)
    result = subprocess.run(args, input=text, text=True, capture_output=True, check=True)
    entries = re.split(r"\n\s*\n", result.stdout.strip())
    if len(entries) != len(addresses):
        raise RuntimeError(f"symbolizer returned {len(entries)} entries for {len(addresses)} PCs in {binary}: {result.stdout[:600]!r}")
    locations = {}
    for pc, entry in zip(addresses, entries):
        parts = entry.splitlines()
        function = parts[0].strip() if len(parts) >= 2 else "??"
        location = parts[1].strip() if len(parts) >= 2 else "??:0:0"
        match = re.match(r"^(.*):(\d+):(\d+)$", location)
        if not match or match.group(1) == "??":
            locations[pc] = None
        else:
            locations[pc] = (str(Path(match.group(1)).resolve()), int(match.group(2)), function)
    return locations


def build_report(raw_directory, info_file, symbolizer):
    valid_sources = parse_lcov(info_file)
    records = {}
    slots = {}
    raw_files = sorted(raw_directory.glob("bb-*.jsonl"))
    if not raw_files:
        raise ValueError(f"No bb-*.jsonl files in {raw_directory}")
    for raw_file in raw_files:
        for number, line in enumerate(raw_file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line)
            binary = str(Path(item["module"]).resolve())
            pc = int(item["pc"], 16)
            if not isinstance(item["hit"], bool):
                raise ValueError(f"Bad hit flag at {raw_file}:{number}")
            key = (binary, pc)
            records[key] = records.get(key, False) or item["hit"]
            if "slot" in item:
                slot = item["slot"]
                if not isinstance(slot, int) or slot < 0:
                    raise ValueError(f"Invalid PC-table slot at {raw_file}:{number}")
                if key in slots and slots[key] != slot:
                    raise ValueError(f"Inconsistent PC-table slot for {key}")
                slots[key] = slot
    if not records:
        raise ValueError("No coverage records")

    per_binary = defaultdict(list)
    for binary, pc in records:
        per_binary[binary].append(pc)

    files = defaultdict(list)
    unresolved = []
    not_in_lcov = []
    for binary, pcs in sorted(per_binary.items()):
        locations = symbolize(binary, sorted(pcs), symbolizer)
        for pc in sorted(pcs):
            loc = locations[pc]
            block_id = f"{binary}@0x{pc:x}"
            if loc is None:
                unresolved.append(block_id)
                continue
            source, line = loc[:2]
            function = loc[2] if len(loc) > 2 else None
            if source not in valid_sources:
                not_in_lcov.append({"id": block_id, "source": source})
                continue
            entry = {"id": block_id, "line": line, "hit": records[(binary, pc)]}
            if function and function != "??":
                entry["function"] = function
            if (binary, pc) in slots:
                entry["slot"] = slots[(binary, pc)]
            files[source].append(entry)

    file_report = {}
    for source, blocks in sorted(files.items()):
        file_report[source] = {
            "covered": sum(b["hit"] for b in blocks),
            "total": len(blocks),
            "blocks": blocks,
        }
    covered = sum(f["covered"] for f in file_report.values())
    total = sum(f["total"] for f in file_report.values())
    if not total:
        raise ValueError("No blocks could be mapped to the LCOV source files")
    all_total = len(records)
    all_covered = sum(records.values())
    excluded_ids = set(unresolved) | {item['id'] for item in not_in_lcov}
    excluded_hit = sum(hit for (binary, pc), hit in records.items()
                       if f"{binary}@0x{pc:x}" in excluded_ids)
    if total + len(excluded_ids) != all_total or covered + excluded_hit != all_covered:
        raise ValueError("Instrumented PC accounting does not match source file counts")
    return {
        "schema_version": 1,
        "instrumentation": {
            "total": all_total, "covered": all_covered,
            "mapped_total": total, "mapped_covered": covered,
            "unresolved": len(unresolved), "outside_lcov": len(not_in_lcov),
            "excluded_covered": excluded_hit,
        },
        "runs": len(raw_files),
        "summary": {"covered": covered, "total": total},
        "files": file_report,
        "unresolved": unresolved,
        "outside_lcov": not_in_lcov,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--lcov", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--symbolizer", default="llvm-symbolizer-19")
    args = parser.parse_args()
    try:
        report = build_report(args.raw_dir, args.lcov, args.symbolizer)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    summary = report["summary"]
    print(f"BB coverage: {summary['covered']}/{summary['total']} ({100 * summary['covered'] / summary['total']:.1f}%)")
    print(f"Inputs: {report['runs']}; unmapped: {len(report['unresolved'])}; outside LCOV: {len(report['outside_lcov'])}")
    if report["unresolved"] or report["outside_lcov"]:
        print("Warning: not all PCs could be attributed to an LCOV source; inspect JSON diagnostics", file=sys.stderr)


if __name__ == "__main__":
    main()
