"""Checks for deterministic GitHub Pages export of the LCOV reports."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish_reports import publish, report_summary, site_index


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for project, covered, total, runs in (("cjson", 3, 7, 5), ("inih", 4, 5, 3)):
            base = self.root / "build" / project
            base.mkdir(parents=True)
            (base / "bb_coverage.json").write_text(json.dumps({
                "summary": {"covered": covered, "total": total}, "runs": runs
            }), encoding="utf-8")
            license_name = "LICENSE" if project == "cjson" else "LICENSE.txt"
            upstream_dir = self.root / "third_party" / ("cJSON" if project == "cjson" else "inih")
            upstream_dir.mkdir(parents=True)
            (upstream_dir / license_name).write_text("Copyright upstream", encoding="utf-8")
            for variant in ("original", "compatible", "extended"):
                folder = base / f"html-{variant}"
                folder.mkdir()
                (folder / "index.html").write_text(
                    f'<a href="c.c.gcov.html">{project} {variant}</a>', encoding="utf-8")
                (folder / "c.c.gcov.html").write_text("source contents", encoding="utf-8")
                (folder / "style.css").write_text("body {}", encoding="utf-8")

    def test_publication_preserves_report_files_and_relative_links(self):
        self.assertEqual(publish(self.root), 12)
        for project in ("cjson", "inih"):
            for variant in ("original", "compatible", "extended"):
                folder = self.root / "docs" / "reports" / project / variant
                self.assertIn('href="c.c.gcov.html"', (folder / "index.html").read_text())
                self.assertEqual((folder / "style.css").read_text(), "body {}")
        self.assertTrue((self.root / "docs" / ".nojekyll").exists())
        self.assertIn("Copyright upstream", (self.root / "docs" / "reports" / "inih" / "UPSTREAM-LICENSE.txt").read_text())
        self.assertIn("reports/inih/extended/index.html", (self.root / "docs" / "index.html").read_text())

    def test_rebuild_removes_stale_files_without_touching_other_docs(self):
        publish(self.root)
        (self.root / "docs" / "DEMO.md").write_text("keep", encoding="utf-8")
        (self.root / "docs" / "reports" / "stale.html").write_text("remove", encoding="utf-8")
        publish(self.root)
        self.assertFalse((self.root / "docs" / "reports" / "stale.html").exists())
        self.assertEqual((self.root / "docs" / "DEMO.md").read_text(), "keep")

    def test_bad_coverage_counts_rejected(self):
        report = self.root / "build" / "cjson" / "bb_coverage.json"
        report.write_text(json.dumps({"summary": {"covered": 8, "total": 7}, "runs": 1}))
        with self.assertRaises(ValueError):
            report_summary(self.root)


if __name__ == "__main__":
    unittest.main()
