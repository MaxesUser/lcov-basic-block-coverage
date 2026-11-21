#!/usr/bin/env python3
"""Create a modified Perl genhtml from the system-installed, unchanged version."""

import argparse
import os
import shutil
import stat
from pathlib import Path

MARKER = "# BONUS1: Basic Block Coverage extension"


def patch(original: Path, destination: Path, injector: Path):
    source = original.read_text(encoding="utf-8")
    if MARKER in source:
        raise ValueError("Source genhtml is already patched")
    if not source.startswith("#!"):
        raise ValueError("Expected Perl script with shebang")
    shebang, remaining = source.split("\n", 1)
    injector_path = str(injector.resolve()).replace("\\", "\\\\").replace("'", "\\'")
    # Both blocks are compiled into the upstream genhtml Perl source. Without --bb-report,
    # all upstream argument processing, rendering and exit codes remain unchanged.
    inserted = r'''# BONUS1: Basic Block Coverage extension
BEGIN {
    my @forward;
    my $bb_report;
    while (@ARGV) {
        my $arg = shift @ARGV;
        if ($arg eq '--bb-report') {
            die "--bb-report requires a JSON path\n" unless @ARGV;
            $bb_report = shift @ARGV;
        } elsif ($arg =~ /^--bb-report=(.+)$/) {
            $bb_report = $1;
        } else {
            push @forward, $arg;
        }
    }
    @ARGV = @forward;
    if (defined $bb_report) {
        require Cwd;
        $ENV{'BONUS1_BB_REPORT'} = Cwd::abs_path($bb_report)
            // die "Cannot open --bb-report: $bb_report\n";
        my $out = '.';
        for (my $i = 0; $i < @ARGV; ++$i) {
            if ($ARGV[$i] eq '-o' || $ARGV[$i] eq '--output-directory') {
                die "Missing output directory\n" unless defined $ARGV[$i+1];
                $out = $ARGV[$i+1]; ++$i;
            } elsif ($ARGV[$i] =~ /^--output-directory=(.+)$/) {
                $out = $1;
            }
        }
        $ENV{'BONUS1_BB_OUTPUT'} = Cwd::abs_path($out) || Cwd::getcwd() . '/' . $out;
    }
}
END {
    if (defined $ENV{'BONUS1_BB_REPORT'} && $? == 0) {
        my $result = system('python3', '__INJECTOR__',
                            '--report', $ENV{'BONUS1_BB_REPORT'},
                            '--output', $ENV{'BONUS1_BB_OUTPUT'});
        if ($result != 0) {
            warn "genhtml: Basic Block Coverage injection failed\n";
            $? = 1;
        }
    }
}
'''.replace("__INJECTOR__", injector_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(shebang + "\n" + inserted + remaining, encoding="utf-8")
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, default=Path(shutil.which('genhtml') or '/usr/bin/genhtml'))
    p.add_argument('--output', type=Path, default=Path('bin/genhtml'))
    args = p.parse_args()
    patch(args.original, args.output, Path(__file__).with_name('bb_html.py'))
    print(f"Modified genhtml: {args.output}")


if __name__ == '__main__':
    main()
