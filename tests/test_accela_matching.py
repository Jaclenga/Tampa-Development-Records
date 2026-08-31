import json
import unittest

from tampa_accela.matching import match_records
from tampa_accela.models import NormalizedRecord


class MatchingTests(unittest.TestCase):
    def test_exact_number_wins(self):
        record = NormalizedRecord(record_id="acc-1", record_number="BLD-123", address="1 MAIN ST")
        gis = [{"source_name": "Permits", "source_record_key": "gis-1", "source_record_id": "BLD-123", "properties_json": "{}"}]
        match = match_records([record], gis)[0]
        self.assertEqual(match["match_method"], "exact_record_number")
        self.assertEqual(match["review_required"], "false")

    def test_exact_parcel_and_fuzzy_candidate(self):
        parcel = NormalizedRecord(record_id="acc-1", record_number="X", parcel_id="P-99")
        gis_parcel = [{"source_record_key": "g1", "properties_json": json.dumps({"PARCEL_ID": "P-99"})}]
        self.assertEqual(match_records([parcel], gis_parcel)[0]["match_method"], "exact_parcel")
        fuzzy = NormalizedRecord(record_id="acc-2", record_number="Y", address="101 North Franklin Street", opened_date="2026-08-10")
        gis_fuzzy = [{"source_record_key": "g2", "properties_json": json.dumps({"ADDRESS": "101 N FRANKLIN ST TAMPA", "CREATEDDATE": "2026-08-15"})}]
        match = match_records([fuzzy], gis_fuzzy)[0]
        self.assertEqual(match["match_status"], "candidate")
        self.assertEqual(match["review_required"], "true")

    def test_unmatched_is_retained(self):
        record = NormalizedRecord(record_id="acc-1", record_number="NOPE")
        self.assertEqual(match_records([record], [])[0]["match_status"], "unmatched")

    def test_ambiguous_exact_matches_require_review(self):
        record = NormalizedRecord(record_id="acc-1", record_number="BLD-123")
        gis = [
            {"source_record_key": "g1", "source_record_id": "BLD-123", "properties_json": "{}"},
            {"source_record_key": "g2", "source_record_id": "BLD-123", "properties_json": "{}"},
        ]
        match = match_records([record], gis)[0]
        self.assertEqual(match["match_status"], "candidate")
        self.assertEqual(match["review_required"], "true")


if __name__ == "__main__":
    unittest.main()
