import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bb_html import inject
from bb_visual import insert_header_metric, render_missing_blocks
from audit_locations import audit
from test_source_markers import SOURCE_HTML


class LCOVIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.leading = '<html><body><table class="header">'
        self.ending = '</table><p>Other LCOV content</p></body></html>'

    def row(self, fields):
        return '<tr>' + ''.join(f'<td class="{cls}">{val}</td>' for cls, val in fields) + '</tr>'

    def test_two_lcov_column_orders(self):
        for older in (False, True):
            with self.subTest(older=older):
                data = [('headerItem', 'Test:'), ('headerCovTableEntry', 'coverage.info'),
                        ('headerItem', 'Branches:')]
                if older:
                    data += [('headerCovTableEntry', '190'),
                             ('headerCovTableEntry', '1064'),
                             ('headerCovTableEntryLo', '17.9 %')]
                else:
                    data += [('headerCovTableEntryLo', '17.9&nbsp;%'),
                             ('headerCovTableEntry', '1064'),
                             ('headerCovTableEntry', '190')]
                initial = self.leading + self.row(data) + self.ending
                result, integrated = insert_header_metric(initial, 311, 1324)
                self.assertTrue(integrated)
                self.assertIn('Basic Blocks:', result)
                self.assertIn('311', result)
                self.assertIn('1324', result)
                self.assertIn('23.5 %', result)
                self.assertIn('bb-inline-bar', result)
                self.assertEqual(result.count('Branches:'), 1)
                self.assertEqual(result.count('Basic Blocks:'), 1)
                self.assertEqual(result.count('<tr>'), 2)
                self.assertEqual(result.count('</tr>'), 2)
                self.assertIn('17.9', result)
                second, integrated2 = insert_header_metric(result, 311, 1324)
                self.assertTrue(integrated2)
                self.assertEqual(result, second)
                self.assertEqual(re.sub(r'\n?<!-- BEGIN BB-HEADER -->.*?<!-- END BB-HEADER -->',
                                        '', result, flags=re.S), initial)

    def test_full_report_embedded_header_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            report = folder / 'bb.json'
            report.write_text(json.dumps({'schema_version': 1, 'files': {
                '/src/test.c': {'total': 2, 'covered': 1, 'blocks': [
                    {'id': 'pc1', 'line': 1, 'hit': True},
                    {'id': 'pc2', 'line': 0, 'hit': False}]}}}))
            html = folder / 'html'
            html.mkdir()
            row = self.row([('headerItem', 'Branches:'),
                            ('headerCovTableEntryLo', '0.0 %'),
                            ('headerCovTableEntry', '2'),
                            ('headerCovTableEntry', '0')])
            base = self.leading + row + self.ending
            (html / 'index.html').write_text(base)
            source = html / 'test.c.gcov.html'
            # The source view has the same header row and source markup.
            source.write_text(SOURCE_HTML.replace('<pre class="sourceHeading">',
                                                 '<table>' + row + '</table><pre class="sourceHeading">'))
            inject(report, html)
            original = (html / 'index.html').read_text()
            self.assertIn('Basic Blocks:', original)
            self.assertNotIn('bb-progress-fill', original.split('<!-- END BB-COVERAGE -->')[-1])
            self.assertIn('bb-no-tools', original)
            text = source.read_text()
            self.assertIn('Basic Blocks:', text)
            self.assertIn('Inspect 1 blocks without a visible source marker', text)
            inject(report, html)
            self.assertEqual(original, (html / 'index.html').read_text())
            self.assertEqual(text, source.read_text())

    def test_no_header_uses_fallback(self):
        original = '<html><body>no known coverage table</body></html>'
        content, inserted = insert_header_metric(original, 1, 2)
        self.assertFalse(inserted)
        self.assertEqual(original, content)

    def test_report_injection_displays_hidden_pc_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            source = '/src/example.c'
            blocks = [{'id': 'binary@0x111', 'line': 2, 'hit': True},
                      {'id': 'binary@0x222', 'line': 0, 'hit': True, 'function': 'example'},
                      {'id': 'binary@0x333', 'line': 0, 'hit': False},
                      {'id': 'binary@0x444', 'line': 99, 'hit': False}]
            path = folder / 'report.json'
            path.write_text(json.dumps({'schema_version': 1,
                                        'files': {source: {'covered': 2, 'total': 4,
                                                           'blocks': blocks}}}), encoding='utf-8')
            html = folder / 'html'
            html.mkdir()
            (html / 'index.html').write_text('<html><body>index</body></html>')
            page = html / 'example.c.gcov.html'
            original = SOURCE_HTML
            page.write_text(original)
            inject(path, html)
            text = page.read_text()
            self.assertIn('Inspect 3 blocks without a visible source marker (1 covered)', text)
            self.assertIn('2 have no DWARF source line', text)
            self.assertIn('1 have a source line missing from LCOV HTML', text)
            self.assertIn('0x222', text)
            self.assertIn('0x333', text)
            self.assertIn('0x444', text)
            self.assertEqual(text.count('<tr data-bb-unplaced-hit="1"'), 1)
            self.assertEqual(text.count('<tr data-bb-unplaced-hit="0"'), 2)
            self.assertIn('data-bb-unplaced-filter="covered"', text)
            self.assertIn('data-bb-unplaced-filter="uncovered"', text)
            self.assertIn('No DWARF line', text)
            self.assertIn('Line 99 not in HTML', text)
            inject(path, html)
            self.assertEqual(text, page.read_text())

    def test_html_escape_in_unplaced_inventory(self):
        blocks = [{'id': 'binary@\"<script>', 'line': 0, 'hit': True, 'function': '<unsafe>'}]
        output = render_missing_blocks(blocks, set())
        self.assertNotIn('<script>', output)
        self.assertNotIn('<unsafe>', output)
        self.assertIn('&lt;unsafe&gt;', output)
        self.assertIn('&lt;script&gt;', output)


class AuditTests(unittest.TestCase):
    def test_counts_do_not_hide_dwarf_unknowns(self):
        data = {'summary': {'covered': 2, 'total': 4}, 'files': {'/src/a.c': {
            'total': 4, 'covered': 2, 'blocks': [
                {'id': 'a', 'line': 0, 'hit': True},
                {'id': 'b', 'line': 0, 'hit': False},
                {'id': 'c', 'line': 2, 'hit': True},
                {'id': 'd', 'line': 99, 'hit': False}]}}}
        self.assertEqual(audit(data)['summary']['without_dwarf_line'], 2)
        self.assertEqual(audit(data)['summary']['with_dwarf_line'], 2)
        with tempfile.TemporaryDirectory() as d:
            html = Path(d)
            (html / 'a.c.gcov.html').write_text(SOURCE_HTML)
            got = audit(data, html)['summary']
            self.assertEqual(got['without_dwarf_line'], 2)
            self.assertEqual(got['without_dwarf_line_covered'], 1)
            self.assertEqual(got['line_not_in_html'], 1)
            self.assertEqual(got['visible'], 1)
            self.assertEqual(got['visible_covered'], 1)
            self.assertEqual(got['total'], 4)
            self.assertEqual(got['covered'], 2)
            data['files']['/src/a.c']['total'] = 5
            with self.assertRaisesRegex(ValueError, 'Mismatched counters'):
                audit(data, html)


if __name__ == '__main__':
    unittest.main()
