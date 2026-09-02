import csv
import gzip
import re
import tempfile
from pathlib import Path
import unittest

from scripts import check_repository_privacy as privacy
from scripts import collect_and_freeze_month_end as month_end


class RepositoryPrivacyTests(unittest.TestCase):
    def test_scanner_decompresses_published_gzip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "published.csv.gz"
            candidate = "C:\\" + "Users" + "\\example-user\\private.csv"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write("source\n" + candidate + "\n")
            original_root = privacy.ROOT
            try:
                privacy.ROOT = root
                findings = privacy.scan([
                    path
                ], [("absolute Windows user path", re.compile(
                    r"(?i)[A-Z]:[\\/]+" + "Users" + r"[\\/]+[^\\/\r\n]+"
                ))])
            finally:
                privacy.ROOT = original_root
            self.assertEqual(findings, ["published.csv.gz:2: absolute Windows user path"])

    def test_integrated_csv_rejects_contact_columns_and_direct_pii(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "data" / "integrated"
            directory.mkdir(parents=True)
            path = directory / "records.csv.gz"
            with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("record_number", "contact_email"))
                writer.writeheader()
                writer.writerow({"record_number": "BLD-1", "contact_email": "person@example.test"})
            original_root = privacy.ROOT
            try:
                privacy.ROOT = root
                findings = privacy.scan_integrated_csv_pii([path])
            finally:
                privacy.ROOT = original_root
            self.assertEqual(len(findings), 2)
            self.assertTrue(any("privacy-blocked column" in finding for finding in findings))
            self.assertTrue(any("email address" in finding for finding in findings))

    def test_month_end_paths_are_made_repository_relative(self):
        original_root = month_end.ROOT
        try:
            home = "C:\\" + "Users" + "\\example-user\\project"
            month_end.ROOT = Path(home)
            value = home + r"\data\raw\accela\response.csv"
            self.assertEqual(
                month_end.repository_relative_text(value),
                "data/raw/accela/response.csv",
            )
        finally:
            month_end.ROOT = original_root

    def test_scanner_reports_absolute_workstation_path_without_echoing_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "candidate.json"
            candidate = "C:\\" + "Users" + "\\example-user\\private.csv"
            path.write_text(json_text := '{"source": ' + repr(candidate) + '}', encoding="utf-8")
            self.assertIn("example-user", json_text)
            original_root = privacy.ROOT
            try:
                privacy.ROOT = root
                findings = privacy.scan([
                    path
                ], [("absolute Windows user path", re.compile(
                    r"(?i)[A-Z]:[\\/]+" + "Users" + r"[\\/]+[^\\/\r\n]+"
                ))])
            finally:
                privacy.ROOT = original_root
            self.assertEqual(findings, ["candidate.json:1: absolute Windows user path"])


if __name__ == "__main__":
    unittest.main()
