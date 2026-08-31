import unittest

from scripts.integrate_accela import activity_id_for, integrate


FIELDS = [
    "source_memberships", "source_record_id", "activity_stage", "status", "source_endpoint",
    "retrieved_at_utc", "project_name", "description", "activity_class", "record_type", "address",
    "zip", "last_updated", "estimated_cost_usd", "physical_development_candidate", "source_url",
    "activity_id", "record_created_date", "application_or_opened_date", "raw_component_rows",
    "location_count", "realization_evidence_grade", "likely_realized", "realization_basis",
]


def core(activity_id="tpa-core", number="BLD-1"):
    row = {field: "" for field in FIELDS}
    row.update({
        "activity_id": activity_id, "source_record_id": number,
        "source_memberships": "construction_inspections", "raw_component_rows": "1",
        "record_type": "Existing", "status": "Issued",
    })
    return row


def accela(record_id="acc-1", number="BLD-1", module="Building"):
    return {
        "record_id": record_id, "record_number": number, "source_module": module,
        "record_type": "Building Permit", "record_status": "Complete", "opened_date": "2026-08-01",
        "retrieved_at": "2026-08-31T00:00:00Z", "address": "1 MAIN ST", "postal_code": "33602",
        "source_url": "https://example.test/record",
        "event_date": "2026-08-01", "event_date_type": "application_opened",
        "first_observed_date": "2026-08-31", "snapshot_date": "2026-08-31",
        "last_observed_date": "2026-08-31", "historical_reconstruction": "0",
        "temporal_evidence": "prospective_snapshot",
    }


class AccelaIntegrationTests(unittest.TestCase):
    def test_exact_number_enriches_without_appending(self):
        activities, audit, report = integrate(
            [core()],
            [{"source_record_id": "BLD-1", "activity_id": "tpa-core"}],
            [accela()],
        )
        self.assertEqual(len(activities), 1)
        self.assertIn("accela_building", activities[0]["source_memberships"])
        self.assertEqual(activities[0]["record_type"], "Existing")
        self.assertEqual(report["exact_core_record_number_matches"], 1)
        self.assertEqual(audit[0]["disposition"], "merged_existing_activity")

    def test_unmatched_record_appends_deterministically(self):
        record = accela(number="NEW-1")
        activities, _audit, report = integrate([core()], [], [record])
        self.assertEqual(len(activities), 2)
        new = next(row for row in activities if row["source_record_id"] == "NEW-1")
        self.assertEqual(new["activity_id"], activity_id_for(record))
        self.assertEqual(new["realization_evidence_grade"], "U")
        self.assertEqual(new["temporal_evidence"], "prospective_snapshot")
        self.assertEqual(report["new_accela_activities_appended"], 1)

    def test_duplicate_accela_number_is_kept_once(self):
        records = [accela("acc-1", "NEW-1"), accela("acc-2", "new 1")]
        activities, audit, report = integrate([core()], [], records)
        self.assertEqual(len(activities), 2)
        self.assertEqual(report["deduplication"]["duplicate_record_number_rows_removed"], 1)
        self.assertTrue(any(row["disposition"] == "deduplicated_accela_record_number" for row in audit))

    def test_ambiguous_core_match_is_held_not_duplicated(self):
        activities, audit, report = integrate(
            [core("tpa-a"), core("tpa-b")],
            [
                {"source_record_id": "BLD-1", "activity_id": "tpa-a"},
                {"source_record_id": "BLD-1", "activity_id": "tpa-b"},
            ],
            [accela()],
        )
        self.assertEqual(len(activities), 2)
        self.assertEqual(report["ambiguous_exact_matches_held_for_review"], 1)
        self.assertEqual(audit[0]["review_required"], "true")


if __name__ == "__main__":
    unittest.main()
