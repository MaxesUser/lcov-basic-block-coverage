import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bb_merge import build_report
from bb_html import inject


class ReportTests(unittest.TestCase):
    def test_union_multiple_runs_no_double_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / 'test.c'
            src.write_text('int main(void) { return 0; }\n')
            exe = root / 'test'
            exe.write_bytes(b'placeholder')
            info = root / 'coverage.info'
            info.write_text(f'SF:{src}\nDA:1,1\nend_of_record\n')
            raw = root / 'raw'
            raw.mkdir()
            for i, hits in enumerate([[True, False], [False, True]]):
                lines = [json.dumps({'module': str(exe), 'pc': f'0x{pc:x}', 'hit': hit})
                         for pc, hit in zip([12, 16], hits)]
                (raw / f'bb-{i}.jsonl').write_text('\n'.join(lines) + '\n')
            with patch('bb_merge.symbolize', return_value={12: (str(src), 1), 16: (str(src), 1)}):
                report = build_report(raw, info, 'llvm-symbolizer')
            self.assertEqual(report['summary'], {'covered': 2, 'total': 2})
            self.assertEqual(report['runs'], 2)

    def test_file_directory_project_and_repeated_injection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / 'bb.json'
            report.write_text(json.dumps({'schema_version': 1,
                'files': {
                    '/sources/a/main.c': {'total': 4, 'covered': 3},
                    '/sources/b/util.c': {'total': 2, 'covered': 1},
                }}))
            html = root / 'html'
            (html / 'a').mkdir(parents=True)
            (html / 'b').mkdir(parents=True)
            for file in ['index.html', 'a/index.html', 'a/main.c.gcov.html',
                         'b/index.html', 'b/util.c.gcov.html']:
                (html / file).write_text('<html><body>LCOV content</body></html>')
            inject(report, html)
            inject(report, html)
            expect = {
                'index.html': (4, 6),
                'a/index.html': (3, 4),
                'a/main.c.gcov.html': (3, 4),
                'b/index.html': (1, 2),
                'b/util.c.gcov.html': (1, 2),
            }
            for file, (covered, total) in expect.items():
                text = (html / file).read_text()
                self.assertEqual(text.count('BEGIN BB-COVERAGE'), 1)
                self.assertIn(f'data-bb-covered="{covered}" data-bb-total="{total}"', text)


if __name__ == '__main__':
    unittest.main()
