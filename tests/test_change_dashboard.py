from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
import unittest

from scripts import build_change_dashboard, change_analysis


class ChangeDashboardTests(unittest.TestCase):
    def test_dashboard_is_accessible_static_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dashboard"
            first = build_change_dashboard.build_dashboard(output_dir=output)
            index = output / "index.html"
            detail = output / "comparisons" / "2026-09.html"
            first_hashes = (hashlib.sha256(index.read_bytes()).hexdigest(), hashlib.sha256(detail.read_bytes()).hexdigest())
            second = build_change_dashboard.build_dashboard(output_dir=output)
            second_hashes = (hashlib.sha256(index.read_bytes()).hexdigest(), hashlib.sha256(detail.read_bytes()).hexdigest())
            self.assertEqual(first_hashes, second_hashes)
            self.assertEqual(first["comparison_count"], second["comparison_count"])

            index_text = index.read_text(encoding="utf-8")
            detail_text = detail.read_text(encoding="utf-8")
            for text in (index_text, detail_text):
                self.assertIn(change_analysis.clean(build_change_dashboard.DISCLAIMER), text)
                self.assertNotIn("https://cdn", text)
                self.assertNotIn("<script src=", text)
            self.assertIn('role="img"', index_text)
            self.assertIn("aria-labelledby", index_text)
            self.assertIn("Reveal noncanonical and critical intervals", index_text)
            self.assertIn("Identity-safe record drill-down", detail_text)
            self.assertIn("record_identity", detail_text)
            self.assertIn("source_record_id", detail_text)
            self.assertIn("Search record changes", detail_text)
            self.assertIn("A disappearance does not prove cancellation or deletion", detail_text)


if __name__ == "__main__":
    unittest.main()
