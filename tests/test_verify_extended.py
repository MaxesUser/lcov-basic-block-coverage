import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bb_html import inject
from verify_extended import verify
from test_source_markers import SOURCE_HTML


class VerifyExtendedTests(unittest.TestCase):
    def test_source_counts_and_markers_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / 'bb.json'
            report.write_text(json.dumps({'schema_version': 1,
                                          'files': {'/s/demo.c': {'total': 2, 'covered': 1,
                                              'blocks': [
                                                  {'id': 'p1', 'line': 2, 'hit': True},
                                                  {'id': 'p2', 'line': 3, 'hit': False}]}}}))
            html = root / 'html'
            html.mkdir()
            (html / 'index.html').write_text('<html><body>index</body></html>')
            page = html / 'demo.c.gcov.html'
            page.write_text(SOURCE_HTML)
            inject(report, html)
            verify(report, html)
            page.write_text(page.read_text().replace('bb-marker bb-miss', 'bb-marker bb-hit'))
            with self.assertRaisesRegex(AssertionError, 'hit statuses'):
                verify(report, html)
