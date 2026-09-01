from __future__ import annotations

import datetime as dt
import unittest

from scripts import backfill_accela, backfill_accela_inspections
from tampa_accela.models import SearchQuery


class AccelaDateBoundaryTests(unittest.TestCase):
    def test_direct_bounded_search_rejects_pre_2020_start(self) -> None:
        query = SearchQuery("Building", dt.date(2019, 12, 1), dt.date(2020, 1, 31))
        with self.assertRaisesRegex(ValueError, "2020-01-01"):
            query.validate()

    def test_direct_bounded_search_accepts_boundary(self) -> None:
        SearchQuery("Building", dt.date(2020, 1, 1), dt.date(2020, 1, 31)).validate()

    def test_record_number_lookup_remains_available_for_verification(self) -> None:
        SearchQuery("Building", record_number="BDE-19-0000001").validate()

    def test_record_backfill_rejects_pre_2020_month(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            backfill_accela.main([
                "--from-month", "2019-12", "--to-month", "2020-01"
            ])
        self.assertEqual(raised.exception.code, 2)

    def test_inspection_backfill_rejects_pre_2020_month(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            backfill_accela_inspections.main([
                "--from-month", "2019-12", "--to-month", "2020-01", "--dry-run"
            ])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
