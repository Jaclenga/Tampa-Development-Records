import csv
import tempfile
import unittest
from pathlib import Path

from tampa_accela.csv_safety import neutralize_csv_cell, restore_csv_cell
from tampa_accela.output import _read_csv, write_csv


class AccelaCsvSafetyTests(unittest.TestCase):
    def test_neutralizes_spreadsheet_formula_prefixes(self):
        for value in ("=1+1", "+cmd", "-2+3", "@SUM(A1:A2)", "  =HYPERLINK(\"x\")", "\t=1"):
            with self.subTest(value=value):
                safe = neutralize_csv_cell(value)
                self.assertEqual(safe, "'" + value)
                self.assertEqual(restore_csv_cell(safe), value)
        self.assertEqual(neutralize_csv_cell("Ordinary text"), "Ordinary text")
        self.assertEqual(neutralize_csv_cell("-82.457"), "-82.457")
        self.assertEqual(neutralize_csv_cell("+27.951e0"), "+27.951e0")

    def test_literal_leading_apostrophes_round_trip(self):
        for value in ("'=SUM(1,1)", "''+cmd", "'''  @remote", "'-82.457"):
            with self.subTest(value=value):
                serialized = neutralize_csv_cell(value)
                self.assertEqual(serialized, "'" + value)
                self.assertEqual(restore_csv_cell(str(serialized)), value)

    def test_writer_is_excel_safe_and_internal_reader_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "safe.csv"
            write_csv(path, [{"id": "1", "description": "=WEBSERVICE(\"https://evil.test\")"}], ["id", "description"])
            with path.open(encoding="utf-8", newline="") as handle:
                serialized = list(csv.DictReader(handle))
            self.assertTrue(serialized[0]["description"].startswith("'="))
            self.assertEqual(_read_csv(path)[0]["description"], '=WEBSERVICE("https://evil.test")')


if __name__ == "__main__":
    unittest.main()
