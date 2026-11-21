#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DIR=build/runtime-check
rm -rf "$DIR"
mkdir -p "$DIR/raw" "$DIR/profiles"
FLAGS=(-g -O0 -fprofile-instr-generate -fcoverage-mapping \
       -fsanitize-coverage=bb,no-prune,inline-bool-flag,pc-table)
clang-19 "${FLAGS[@]}" -c tests/fixture.c -o "$DIR/program.o"
clang-19 "${FLAGS[@]}" -S -emit-llvm tests/fixture.c -o "$DIR/program.ll"
clang-19 -g -O0 -c runtime/bb_runtime.c -o "$DIR/runtime.o"
clang-19 -g -O0 -fprofile-instr-generate "$DIR/program.o" "$DIR/runtime.o" \
    -ldl -o "$DIR/program"
for arg in -2 0 1; do
    BBRAW_DIR="$ROOT/$DIR/raw" LLVM_PROFILE_FILE="$ROOT/$DIR/profiles/%p.profraw" \
        "$ROOT/$DIR/program" "$arg"
done
llvm-profdata-19 merge -sparse "$DIR"/profiles/*.profraw -o "$DIR/merged.profdata"
llvm-cov-19 export -format=lcov -instr-profile="$DIR/merged.profdata" \
    "$DIR/program" > "$DIR/coverage.info"
python3 tools/bb_merge.py --raw-dir "$DIR/raw" --lcov "$DIR/coverage.info" \
    --symbolizer llvm-symbolizer-19 --output "$DIR/bb_coverage.json"
python3 tools/verify_instrumentation.py --report "$DIR/bb_coverage.json" --strict-mapping
python3 tools/bb_cfg.py --report "$DIR/bb_coverage.json" --ir "$DIR/program.ll"
python3 - <<'PY'
import json
from pathlib import Path
r = json.loads(Path('build/runtime-check/bb_coverage.json').read_text())
assert r['runs'] == 3
assert r['summary']['total'] > 0
assert 0 <= r['summary']['covered'] <= r['summary']['total']
assert len(r['files']) == 1
assert not r['unresolved'], r['unresolved']
assert not r['outside_lcov'], r['outside_lcov']
assert r['cfg'], 'Missing CFG'
assert any(n['verified'] for g in r['cfg'] for n in g['nodes'])
assert all('slot' in b for f in r['files'].values() for b in f['blocks'])
print('Runtime integration OK')
PY
