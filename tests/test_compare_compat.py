"""Compatibility comparison must ignore row order but detect changed coverage."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from compare_compat import compare  # noqa: E402


def page(*rows):
    return '<html><body><table>' + ''.join(f'<tr><td>{x}</td></tr>' for x in rows) + '</table></body></html>'


class CompatComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.left = Path(self.tmp.name) / 'original'
        self.right = Path(self.tmp.name) / 'modified'
        self.left.mkdir()
        self.right.mkdir()

    def write(self, original, modified):
        (self.left / 'demo.func-c.html').write_text(original)
        (self.right / 'demo.func-c.html').write_text(modified)

    def test_equal_rows_in_different_order_pass(self):
        self.write(page('foo', 'bar', 'bar'), page('bar', 'foo', 'bar'))
        compare(self.left, self.right)

    def test_lcov_test_date_metadata_difference_is_ignored(self):
        def page_at(test_date, hits):
            return (
                '<html><body><table>'
                '<tr><td class="headerItem">Test Date:</td>'
                f'<td class="headerValue">{test_date}</td>'
                '<td class="headerItem">Functions:</td>'
                '<td class="headerCovTableEntry">100.0&nbsp;%</td>'
                '<td class="headerCovTableEntry">1</td>'
                '<td class="headerCovTableEntry">1</td></tr>'
                f'<tr><td>demo</td><td>{hits}</td></tr>'
                '</table></body></html>'
            )

        self.write(
            page_at('2026-11-19 22:15:00', 1),
            page_at('2026-11-19 22:15:01', 1),
        )
        compare(self.left, self.right)

        self.write(
            page_at('2026-11-19 22:15:00', 1),
            page_at('2026-11-19 22:15:01', 2),
        )
        with self.assertRaisesRegex(AssertionError, 'Different HTML coverage table rows'):
            compare(self.left, self.right)

    def test_changed_hit_count_fails(self):
        self.write(page('foo 1 hit', 'bar 0 hits'), page('bar 0 hits', 'foo 2 hits'))
        with self.assertRaisesRegex(AssertionError, 'Different HTML coverage table rows'):
            compare(self.left, self.right)

    def test_missing_duplicate_fails(self):
        self.write(page('foo', 'foo', 'bar'), page('foo', 'bar', 'bar'))
        with self.assertRaisesRegex(AssertionError, 'Different HTML coverage table rows'):
            compare(self.left, self.right)

    def test_missing_page_fails(self):
        self.write(page('foo'), page('foo'))
        (self.right / 'demo.func-c.html').unlink()
        with self.assertRaisesRegex(AssertionError, 'Different HTML pages'):
            compare(self.left, self.right)


if __name__ == '__main__':
    unittest.main()
