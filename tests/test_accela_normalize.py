import unittest

from tampa_accela.models import NormalizedRecord
from tampa_accela.normalize import (
    apply_detail,
    deduplicate_public_records,
    deduplicate_records,
    iso_date,
    normalize_inspection_row,
    normalize_search_row,
)


class AccelaNormalizeTests(unittest.TestCase):
    def test_normalizes_search_and_detail_fields(self):
        row = {
            "Record Number": " BLD-26-1 ",
            "Record Type": "Building / Commercial",
            "Status": "Issued",
            "Date": "08/13/2026",
            "Address": "123 N TAMPA ST, TAMPA FL 33602",
            "_source_url": "https://example.test/detail?capID1=A&capID2=B&capID3=C",
            "_cap_id_parts": ("A", "B", "C"),
        }
        record = normalize_search_row(row, module="Building", retrieved_at="2026-08-30T00:00:00Z", raw_source_file="raw.html")
        self.assertEqual(record.opened_date, "2026-08-13")
        self.assertEqual(record.street_number, "123")
        enriched = apply_detail(record, {
            "Parcel Number": "P-1", "Job Value": "$1,234.50",
            "Issued Date": "08/14/2026", "Parent Record Number": "BLD-26-9",
        })
        self.assertEqual(enriched.parcel_id, "P-1")
        self.assertEqual(enriched.valuation, "1234.50")
        self.assertEqual(enriched.issued_date, "2026-08-14")
        self.assertEqual(enriched.parent_record_number, "BLD-26-9")
        temporal = enriched.as_row()
        self.assertEqual(temporal["event_date"], "2026-08-14")
        self.assertEqual(temporal["event_date_type"], "permit_issued")
        self.assertEqual(temporal["first_observed_date"], "2026-08-30")
        self.assertEqual(temporal["snapshot_date"], "2026-08-30")
        self.assertEqual(temporal["last_observed_date"], "2026-08-30")
        self.assertEqual(temporal["historical_reconstruction"], "0")
        self.assertEqual(temporal["temporal_evidence"], "prospective_snapshot")

    def test_malformed_dates_become_null(self):
        self.assertIsNone(iso_date("not a date"))
        self.assertIsNone(iso_date(""))

    def test_duplicate_merge_prefers_later_non_null(self):
        first = NormalizedRecord(record_id="acc-1", record_number="A", retrieved_at="2026-08-30", address="1 MAIN ST")
        later = NormalizedRecord(record_id="acc-1", record_number="A", retrieved_at="2026-09-30", record_status="Issued")
        merged = deduplicate_records([later, first])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].address, "1 MAIN ST")
        self.assertEqual(merged[0].record_status, "Issued")
        self.assertEqual(merged[0].as_row()["first_observed_date"], "2026-08-30")
        self.assertEqual(merged[0].as_row()["last_observed_date"], "2026-09-30")

    def test_historical_record_is_labeled_as_retrospective_not_as_old_snapshot(self):
        record = NormalizedRecord(
            source_module="Building", record_id="acc-old", record_number="OLD-1",
            opened_date="2025-08-15", retrieved_at="2026-08-31T02:00:00+00:00",
        ).as_row()
        self.assertEqual(record["event_date"], "2025-08-15")
        self.assertEqual(record["snapshot_date"], "2026-08-31")
        self.assertEqual(record["historical_reconstruction"], "1")
        self.assertEqual(record["temporal_evidence"], "retrospective_source_record")

    def test_public_number_dedup_prefers_cap_link_and_preserves_observation_range(self):
        paged = NormalizedRecord(
            source_module="Building", record_id="acc-cap", record_number="BLD-1",
            opened_date="2025-08-01", source_url="https://example.test/CapDetail.aspx?id=1",
            retrieved_at="2026-08-30T23:00:00Z",
        )
        exported = NormalizedRecord(
            source_module="Building", record_id="acc-number", record_number="bld 1",
            opened_date="2025-08-01", record_status="Complete", retrieved_at="2026-08-31T01:00:00Z",
        )
        records = deduplicate_public_records([exported, paged])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_id, "acc-cap")
        self.assertEqual(records[0].record_status, "Complete")
        self.assertEqual(records[0].as_row()["first_observed_date"], "2026-08-30")
        self.assertEqual(records[0].as_row()["last_observed_date"], "2026-08-31")

    def test_inspection_normalization_has_stable_fallback_id(self):
        record = NormalizedRecord(record_id="acc-1", record_number="A", source_url="https://example.test")
        item = normalize_inspection_row(
            {"Inspection Type": "Final", "Status": "Completed", "Date": "08/20/2026", "Result": "Pass"},
            record=record,
            retrieved_at="2026-08-30T00:00:00Z",
            raw_source_file="inspection.html",
        )
        self.assertTrue(item.inspection_id.startswith("ins-"))
        self.assertEqual(item.result_date, "2026-08-20")


if __name__ == "__main__":
    unittest.main()
