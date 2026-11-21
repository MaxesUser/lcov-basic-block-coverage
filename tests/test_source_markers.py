import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bb_html import inject, add_source_markers


SOURCE_HTML = '''<!DOCTYPE html><html><head><title>LCOV</title></head><body>
<pre class="sourceHeading">Line data Source code</pre>
<pre class="source"><span id="L1"><span class="lineNum">       1 </span><span class="lineCov">  3 : int test(void) {</span></span>
<span id="L2"><span class="lineNum">       2 </span><span class="lineNoCov">  0 :   if (ready) {</span></span>
<span id="L3"><span class="lineNum">       3 </span><span class="lineCov">  3 :   return 1;</span></span>
<span id="L4"><span class="lineNum">       4 </span><span class="lineCov">  3 : }</span></span>
</pre>
</body></html>'''


def block(name, line, hit):
    return {"id": name, "line": line, "hit": hit}


class SourceMarkersTests(unittest.TestCase):
    def test_line_markers_status_filter_and_idempotence(self):
        blocks = [block("pc-1", 2, True), block("pc-2", 2, False),
                  block("pc-3", 3, False), block("pc-4", 0, True)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "/source/demo.c"
            report = root / "bb.json"
            report.write_text(json.dumps({"schema_version": 1, "summary": {"total": 4, "covered": 2},
                                          "files": {src: {"covered": 2, "total": 4, "blocks": blocks}}}))
            directory = root / "html"
            directory.mkdir()
            (directory / "index.html").write_text("<html><body>LCOV index</body></html>")
            page = directory / "demo.c.gcov.html"
            page.write_text(SOURCE_HTML)

            inject(report, directory)
            first = page.read_text()
            self.assertIn('data-bb-covered="2" data-bb-total="4"', first)
            self.assertEqual(first.count('class="bb-marker bb-hit"'), 1)
            self.assertEqual(first.count('class="bb-marker bb-miss"'), 2)
            self.assertIn('title="BB1: covered | pc-1 | line 2"', first)
            self.assertIn('title="BB2: uncovered | pc-2 | line 2"', first)
            self.assertIn('id="bb-line-2"', first)
            self.assertIn('href="#bb-line-2"', first)
            self.assertIn('Uncovered only', first)
            self.assertIn('1 block(s) have no visible source-line marker', first)
            self.assertIn('<span class="lineNoCov">  0 :   if (ready) {</span>', first)
            self.assertIn('data-bb-filter', first)
            self.assertEqual(first.count('<!-- BEGIN BB-LINE -->'), 4)

            inject(report, directory)
            second = page.read_text()
            self.assertEqual(first, second)
            self.assertEqual(second.count('<!-- BEGIN BB-COVERAGE -->'), 1)
            self.assertEqual(second.count('<!-- BEGIN BB-LINE -->'), 4)
            self.assertEqual((directory / "index.html").read_text().count('class="bb-marker'), 0)

            original = re.sub(r'<!-- BEGIN BB-COVERAGE -->.*?<!-- END BB-COVERAGE -->', '',
                              second, flags=re.S)
            original = re.sub(r'<!-- BEGIN BB-LINE -->.*?<!-- END BB-LINE -->', '',
                              original, flags=re.S)
            self.assertEqual(original.replace('<body>\n', '<body>'), SOURCE_HTML)

    def test_unavailable_source_line_counted_but_not_misrepresented(self):
        content, placed, first, rows = add_source_markers(SOURCE_HTML, [
            block('pc-1', 2, True), block('pc-2', 999, False), block('pc-3', 0, False)])
        self.assertEqual((placed, first, rows), (1, None, 4))
        self.assertNotIn('bb-line-999', content)
        self.assertEqual(content.count('class="bb-marker'), 1)

    def test_escape_raw_pc_in_tooltip(self):
        content, _, _, _ = add_source_markers(SOURCE_HTML, [
            block('bad" onmouseover="alert(1)', 3, True)])
        self.assertIn('bad&quot; onmouseover=&quot;alert(1)', content)
        self.assertNotIn('onmouseover="alert(1)"', content)

    def test_missing_line_numbers_is_explicit_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "bb.json"
            report.write_text(json.dumps({"schema_version": 1, "files": {
                "/src/a.c": {"total": 1, "covered": 1,
                             "blocks": [block("p", 1, True)]}}}))
            directory = root / "html"
            directory.mkdir()
            (directory / "a.c.gcov.html").write_text('<html><body>no source lines</body></html>')
            with self.assertRaisesRegex(ValueError, "No LCOV source line numbers"):
                inject(report, directory)

    def test_rejects_inconsistent_report_block_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "bb.json"
            report.write_text(json.dumps({"schema_version": 1, "files": {
                "/src/a.c": {"total": 2, "covered": 1,
                             "blocks": [block("p", 1, True)]}}}))
            directory = root / "html"
            directory.mkdir()
            (directory / "a.c.gcov.html").write_text(SOURCE_HTML)
            with self.assertRaisesRegex(ValueError, "BB counts disagree"):
                inject(report, directory)


if __name__ == "__main__":
    unittest.main()
