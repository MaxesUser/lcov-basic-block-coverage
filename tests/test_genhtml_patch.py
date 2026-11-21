import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GenhtmlPatchTests(unittest.TestCase):
    def test_perl_patch_preserves_legacy_mode_and_supports_bb_report(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            baseline = folder / 'genhtml.orig'
            modified = folder / 'genhtml'
            baseline.write_text('''#!/usr/bin/perl
use strict;
use warnings;
my $out = '.';
for (my $i = 0; $i < @ARGV; ++$i) {
    if ($ARGV[$i] eq '--output-directory') {
        $out = $ARGV[$i+1]; ++$i;
    }
}
mkdir $out unless -d $out;
for my $name ('index.html', 'demo.c.gcov.html') {
    open my $fh, '>', "$out/$name" or die $!;
    print $fh '<html><body><table><tr><td>Line</td><td>1/1</td></tr></table></body></html>';
    close $fh;
}
exit 0;
''')
            subprocess.run(['python3', str(ROOT / 'tools/patch_genhtml.py'), '--original', str(baseline), '--output', str(modified)], check=True, capture_output=True)
            baseline_dir = folder / 'baseline'
            compatible_dir = folder / 'compatible'
            extended_dir = folder / 'extended'
            for command, out in [(baseline, baseline_dir), (modified, compatible_dir)]:
                subprocess.run(['perl', str(command), '--output-directory', str(out)], check=True)
            self.assertEqual((baseline_dir / 'index.html').read_bytes(), (compatible_dir / 'index.html').read_bytes())
            self.assertNotIn('Basic Block Coverage', (compatible_dir / 'index.html').read_text())
            report = folder / 'bb.json'
            report.write_text(json.dumps({'schema_version': 1,
                'files': {'/any/demo.c': {'covered': 2, 'total': 3}}}))
            subprocess.run(['perl', str(modified), '--bb-report', str(report), '--output-directory', str(extended_dir)], check=True, capture_output=True)
            self.assertIn('Basic Block Coverage', (extended_dir / 'index.html').read_text())
            self.assertIn('2 / 3 blocks', (extended_dir / 'demo.c.gcov.html').read_text())


if __name__ == '__main__':
    unittest.main()
