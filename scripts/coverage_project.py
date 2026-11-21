#!/usr/bin/env python3
"""Build, execute and report coverage for a small standalone C/C++ program.

Use the same instrumented executable across every test run. This is a source-
file workflow, not a replacement for CMake/Make or dependency-specific builds.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FLAGS = [
    '-g', '-O0', '-fprofile-instr-generate', '-fcoverage-mapping',
    '-fsanitize-coverage=bb,no-prune,inline-bool-flag,pc-table',
]
CXX_EXTENSIONS = {'.cc', '.cpp', '.cxx', '.C'}


def checked(*args, **kwargs):
    print('+', ' '.join(str(a) for a in args), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def project_dir(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
        raise ValueError('Project name must be a single safe path component')
    return ROOT / 'build' / 'projects' / name


def tools(version):
    def locate(stem):
        candidate = shutil.which(f'{stem}-{version}') or shutil.which(stem)
        if not candidate:
            raise FileNotFoundError(f'Missing tool {stem}-{version} (or {stem})')
        return candidate
    return {stem: locate(stem) for stem in
            ('clang', 'clang++', 'llvm-profdata', 'llvm-cov', 'llvm-symbolizer')}


def compile_project(args):
    dest = project_dir(args.name)
    if not args.source:
        raise ValueError('At least one --source is required')
    sources = [Path(src).resolve(strict=True) for src in args.source]
    includes = [Path(path).resolve(strict=True) for path in args.include]
    cxx = any(path.suffix in CXX_EXTENSIONS for path in sources)
    for path in sources:
        if path.suffix not in CXX_EXTENSIONS | {'.c'}:
            raise ValueError(f'Expected C/C++ source: {path}')
    if dest.exists():
        if not args.force:
            raise ValueError(f'{dest} already exists; use --force to rebuild and discard old profiles')
        shutil.rmtree(dest)
    for folder in ('objects', 'ir', 'raw', 'profiles'):
        (dest / folder).mkdir(parents=True, exist_ok=True)
    tc = tools(args.llvm_version)
    include_flags = [f'-I{path}' for path in includes]
    objects = []
    irs = []
    for i, source in enumerate(sources):
        compiler = tc['clang++'] if source.suffix in CXX_EXTENSIONS else tc['clang']
        obj = dest / 'objects' / f'source_{i:03d}.o'
        ir = dest / 'ir' / f'source_{i:03d}.ll'
        checked(compiler, *FLAGS, *include_flags, *args.cflag, '-c', source, '-o', obj)
        checked(compiler, *FLAGS, *include_flags, *args.cflag, '-S', '-emit-llvm', source, '-o', ir)
        objects.append(obj)
        irs.append(ir)
    runtime = dest / 'objects' / 'bb_runtime.o'
    checked(tc['clang'], '-g', '-O0', '-c', ROOT / 'runtime' / 'bb_runtime.c', '-o', runtime)
    linker = tc['clang++'] if cxx else tc['clang']
    program = dest / 'program'
    checked(linker, '-g', '-O0', '-fprofile-instr-generate', *objects, runtime,
            '-o', program, '-ldl', *args.ldflag)
    (dest / 'build.json').write_text(json.dumps({
        'sources': [str(p) for p in sources], 'ir': [str(p) for p in irs],
        'llvm_version': args.llvm_version, 'includes': [str(p) for p in includes],
        'cflags': args.cflag, 'ldflags': args.ldflag,
    }, indent=2) + '\n', encoding='utf-8')
    print(f'Built: {program}\nRun tests: python3 scripts/coverage_project.py run {args.name} -- ARG...')


def run_project(args):
    dest = project_dir(args.name)
    program = dest / 'program'
    if not program.is_file():
        raise FileNotFoundError(f'Build first: {program}')
    argv = args.args[1:] if args.args and args.args[0] == '--' else args.args
    env = dict(os.environ, BBRAW_DIR=str(dest / 'raw'),
               LLVM_PROFILE_FILE=str(dest / 'profiles' / '%p.profraw'))
    print('+', str(program), *argv, flush=True)
    result = subprocess.run([str(program), *argv], env=env, check=False)
    if result.returncode and not args.allow_nonzero:
        raise RuntimeError(f'Program exited with {result.returncode}; use --allow-nonzero only for expected failures')
    print(f'Run complete: exit={result.returncode}; profiles kept in {dest}')


def generate_report(args):
    dest = project_dir(args.name)
    state_file = dest / 'build.json'
    if not state_file.is_file():
        raise FileNotFoundError('Build the project first')
    state = json.loads(state_file.read_text(encoding='utf-8'))
    tc = tools(state['llvm_version'])
    profiles = sorted((dest / 'profiles').glob('*.profraw'))
    raws = sorted((dest / 'raw').glob('bb-*.jsonl'))
    if not profiles or not raws:
        raise ValueError('No profiles; run the instrumented program at least once')
    merged = dest / 'merged.profdata'
    checked(tc['llvm-profdata'], 'merge', '-sparse', *profiles, '-o', merged)
    info = dest / 'coverage.info'
    print('+ llvm-cov export -format=lcov ...', flush=True)
    with info.open('w', encoding='utf-8') as out:
        checked(tc['llvm-cov'], 'export', '-format=lcov', f'-instr-profile={merged}',
                dest / 'program', stdout=out)
    report = dest / 'bb_coverage.json'
    checked(sys.executable, ROOT / 'tools' / 'bb_merge.py', '--raw-dir', dest / 'raw',
            '--lcov', info, '--symbolizer', tc['llvm-symbolizer'], '--output', report)
    verify = [sys.executable, ROOT / 'tools' / 'verify_instrumentation.py', '--report', report]
    if args.strict_mapping:
        verify.append('--strict-mapping')
    checked(*verify)
    cmd = [sys.executable, ROOT / 'tools' / 'bb_cfg.py', '--report', report]
    for ir in state['ir']:
        cmd.extend(['--ir', ir])
    checked(*cmd)
    original = shutil.which('genhtml')
    if not original:
        raise FileNotFoundError('System genhtml is required (install lcov)')
    patched = ROOT / 'bin' / 'genhtml'
    checked(sys.executable, ROOT / 'tools' / 'patch_genhtml.py',
            '--original', original, '--output', patched)
    env = dict(os.environ, PERL_HASH_SEED='0', PERL_PERTURB_KEYS='0')
    common = [str(info), '--branch-coverage', '--rc', 'check_data_consistency=0']
    for kind, executable in (('original', original), ('compatible', patched),
                             ('extended', patched)):
        cmd = [str(executable), *common]
        if kind == 'extended':
            cmd += ['--bb-report', str(report)]
        cmd += ['--output-directory', str(dest / f'html-{kind}')]
        checked(*cmd, env=env)
    checked(sys.executable, ROOT / 'tools' / 'compare_compat.py',
            dest / 'html-original', dest / 'html-compatible')
    checked(sys.executable, ROOT / 'tools' / 'verify_extended.py',
            '--report', report, '--html', dest / 'html-extended')
    checked(sys.executable, ROOT / 'tools' / 'audit_locations.py',
            '--report', report, '--html', dest / 'html-extended',
            '--output', dest / 'source_line_audit.json')
    print(f'Report ready: {dest / "html-extended" / "index.html"}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build', help='Compile a standalone program from C/C++ source files')
    build.add_argument('name')
    build.add_argument('--source', action='append', required=True, help='Repeat for each source file, including main()')
    build.add_argument('--include', action='append', default=[], help='Repeat for include directories')
    build.add_argument('--cflag', action='append', default=[], help='Extra compiler flag (repeat)')
    build.add_argument('--ldflag', action='append', default=[], help='Extra linker flag, e.g. -lm (repeat)')
    build.add_argument('--llvm-version', default='19', help='Default: 19')
    build.add_argument('--force', action='store_true', help='Discard existing profile data and rebuild')
    run = sub.add_parser('run', help='Execute one test input and save BB and LLVM profiles')
    run.add_argument('name')
    run.add_argument('--allow-nonzero', action='store_true')
    run.add_argument('args', nargs=argparse.REMAINDER, help='Arguments passed after --')
    report = sub.add_parser('report', help='Merge all recorded runs and generate HTML')
    report.add_argument('name')
    report.add_argument('--strict-mapping', action='store_true')
    args = parser.parse_args()
    try:
        {'build': compile_project, 'run': run_project, 'report': generate_report}[args.command](args)
    except (ValueError, FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    main()
