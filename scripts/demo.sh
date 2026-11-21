#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for tool in git clang-19 llvm-cov-19 llvm-profdata-19 llvm-symbolizer-19 genhtml python3 dot; do
    command -v "$tool" >/dev/null || { echo "Missing command: $tool" >&2; exit 1; }
done

mkdir -p third_party build bin
if [[ ! -e third_party/cJSON/cJSON.c ]]; then
    git clone --depth 1 --branch v1.7.19 https://github.com/DaveGamble/cJSON.git third_party/cJSON
fi
if [[ ! -e third_party/inih/ini.c ]]; then
    git clone --depth 1 --branch r62 https://github.com/benhoyt/inih.git third_party/inih
fi

python3 tools/patch_genhtml.py --original "$(command -v genhtml)" --output bin/genhtml
clang-19 -g -O0 -c runtime/bb_runtime.c -o build/bb_runtime.o

FLAGS=(-g -O0 -fprofile-instr-generate -fcoverage-mapping \
       -fsanitize-coverage=bb,no-prune,inline-bool-flag,pc-table)

run_input() {
    local project="$1"
    shift
    BBRAW_DIR="$ROOT/build/$project/raw" \
    LLVM_PROFILE_FILE="$ROOT/build/$project/profiles/%p.profraw" \
        "$ROOT/build/$project/program" "$@"
}

build_project() {
    local project="$1"
    local source_dir="$2"
    local library_source="$3"
    local driver="$4"
    local extra_link="$5"
    local dir="build/$project"
    rm -rf "$dir"
    mkdir -p "$dir/raw" "$dir/profiles"
    clang-19 "${FLAGS[@]}" -I"$source_dir" -c "$library_source" -o "$dir/library.o"
    clang-19 "${FLAGS[@]}" -I"$source_dir" -S -emit-llvm "$library_source" -o "$dir/library.ll"
    clang-19 "${FLAGS[@]}" -I"$source_dir" -c "$driver" -o "$dir/driver.o"
    clang-19 "${FLAGS[@]}" -I"$source_dir" -S -emit-llvm "$driver" -o "$dir/driver.ll"
    clang-19 -g -O0 -fprofile-instr-generate "$dir/library.o" "$dir/driver.o" \
        build/bb_runtime.o -o "$dir/program" -ldl $extra_link
}

render_project() {
    local project="$1"
    local dir="build/$project"
    llvm-profdata-19 merge -sparse "$dir"/profiles/*.profraw -o "$dir/merged.profdata"
    llvm-cov-19 export -format=lcov -instr-profile="$dir/merged.profdata" \
        "$dir/program" > "$dir/coverage.info"
    python3 tools/bb_merge.py --raw-dir "$dir/raw" --lcov "$dir/coverage.info" \
        --symbolizer llvm-symbolizer-19 --output "$dir/bb_coverage.json"
    python3 tools/verify_instrumentation.py --report "$dir/bb_coverage.json" --strict-mapping
    python3 tools/bb_cfg.py --report "$dir/bb_coverage.json" \
        --ir "$dir/library.ll" --ir "$dir/driver.ll"

    # LLVM-generated LCOV can record branch hits for lines with zero line hits.
    # LCOV's strict consistency check rejects that combination. Use the same
    # option for all three variants so the baseline comparison stays valid.
    local genhtml_flags=(--branch-coverage --rc check_data_consistency=0)

    # Perl randomizes hash iteration order per process; equal-hit functions
    # can appear in different rows on *.func-c.html between separate runs.
    # Freeze hash seed for reproducible original-vs-patched comparisons.
    export PERL_HASH_SEED=0 PERL_PERTURB_KEYS=0

    # Baseline used as a control: no Basic Block Coverage extension.
    /usr/bin/genhtml "$dir/coverage.info" "${genhtml_flags[@]}" \
        --output-directory "$dir/html-original" >/dev/null
    # Compatibility mode of modified genhtml (no --bb-report).
    "$ROOT/bin/genhtml" "$dir/coverage.info" "${genhtml_flags[@]}" \
        --output-directory "$dir/html-compatible" >/dev/null
    # Extended mode. This argument is handled by the modified genhtml Perl source.
    "$ROOT/bin/genhtml" "$dir/coverage.info" "${genhtml_flags[@]}" \
        --bb-report "$dir/bb_coverage.json" \
        --output-directory "$dir/html-extended" >/dev/null
    python3 tools/compare_compat.py "$dir/html-original" "$dir/html-compatible"
    python3 tools/verify_extended.py --report "$dir/bb_coverage.json" --html "$dir/html-extended"
    python3 tools/audit_locations.py --report "$dir/bb_coverage.json" \
        --html "$dir/html-extended" --output "$dir/source_line_audit.json"
    echo "[$project] all reports generated: $dir/html-extended/index.html"
}

build_project cjson third_party/cJSON third_party/cJSON/cJSON.c demos/cjson_driver.c -lm
run_input cjson '{"value":10}'
run_input cjson '{"value":"text"}'
run_input cjson '{"other":null}'
run_input cjson '[1,2,3]'
run_input cjson '{broken'
render_project cjson

build_project inih third_party/inih third_party/inih/ini.c demos/inih_driver.c ''
run_input inih 0
run_input inih 1
run_input inih 2
render_project inih

echo 'Done: build/{cjson,inih}/html-extended/index.html'
