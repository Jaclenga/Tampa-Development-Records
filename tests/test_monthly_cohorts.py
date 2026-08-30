from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts import monthly_cohorts, snapshot_tracker


def record(
    source: str,
    native_id: str,
    properties: dict,
    observed: str,
    *,
    object_id: str = "1",
    global_id: str = "g-1",
) -> dict[str, str]:
    return {
        "source_record_key": f"src-{source}-{native_id}",
        "activity_id": f"tpa-{native_id}",
        "source_name": source,
        "source_record_id": native_id,
        "source_object_id": object_id,
        "source_global_id": global_id,
        "source_endpoint": f"https://example.test/{source}",
        "retrieved_at_utc": observed,
        "properties_json": json.dumps(properties, separators=(",", ":")),
    }


class MonthlyCohortTests(unittest.TestCase):
    def test_source_specific_event_date_semantics(self) -> None:
        issued = {
            "APPLICATION_STATUS": "Issued",
            "TASK": "Issuance",
            "TASK_STATUS_DATE": 1744934400000,
            "OPENED_DATE": 1740009600000,
        }
        self.assertEqual(
            monthly_cohorts.select_event_date("single_family_permits", issued),
            ("2025-04-18", "permit_issued", "TASK_STATUS_DATE", "source_reported_event", "0"),
        )

        capital = {"planstart": 1790812800000, "CreationDate": 1609459200000}
        self.assertEqual(
            monthly_cohorts.select_event_date("capital_improvements", capital),
            ("2026-10-01", "capital_planned_start", "planstart", "source_reported_plan", "1"),
        )

        construction = {"PROJECTSTATUS": "Issued", "CREATEDDATE": 1556064000000, "LASTUPDATE": 1559001600000}
        self.assertEqual(
            monthly_cohorts.select_event_date("construction_inspections", construction),
            ("2019-04-24", "permit_record_created", "CREATEDDATE", "source_record_metadata", "0"),
        )
        self.assertEqual(monthly_cohorts.parse_source_date(-2208988800000), "")

    def test_build_retains_disappeared_records_and_separates_three_months(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshots = root / "snapshots"
            processed = root / "processed"
            monthly_events = root / "monthly_events"
            planned_events = root / "planned_events"
            current_path = root / "source_records.csv"

            permit_august = record(
                "single_family_permits",
                "BLD-1",
                {
                    "APPLICATION_STATUS": "Issued",
                    "TASK": "Issuance",
                    "TASK_STATUS_DATE": 1744934400000,
                    "APPLICATION_TYPE": "Residential new construction",
                },
                "2026-08-23T00:00:00Z",
            )
            disappeared = record(
                "development_coordination",
                "DEV-OLD",
                {"APPSTATUS": "Open", "CREATEDDATE": 1643673600000},
                "2026-08-23T00:00:00Z",
                object_id="2",
                global_id="g-2",
            )
            snapshot_tracker.archive_rows([permit_august, disappeared], snapshots)

            permit_september = dict(permit_august)
            permit_september["retrieved_at_utc"] = "2026-09-01T00:00:00Z"
            capital = record(
                "capital_improvements",
                "CIP-NEW",
                {"status": "Planning", "projname": "Project", "planstart": 1790812800000},
                "2026-09-01T00:00:00Z",
                object_id="3",
                global_id="g-3",
            )
            snapshot_tracker.archive_rows([permit_september, capital], snapshots)

            with current_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(permit_september))
                writer.writeheader()
                writer.writerows([permit_september, capital])

            rows = monthly_cohorts.build_rows(snapshots, current_path)
            by_native = {row["source_record_id"]: row for row in rows}

            permit = by_native["BLD-1"]
            self.assertEqual(permit["event_month"], "2025-04")
            self.assertEqual(permit["first_observed_month"], "2026-08")
            self.assertEqual(permit["snapshot_month"], "2026-09")
            self.assertEqual(permit["observation_count"], "2")
            self.assertEqual(permit["currently_observed"], "1")
            self.assertEqual(permit["activity_id"], "tpa-BLD-1")

            self.assertEqual(by_native["DEV-OLD"]["currently_observed"], "0")
            self.assertEqual(by_native["DEV-OLD"]["last_observed_date"], "2026-08-23")
            self.assertEqual(by_native["CIP-NEW"]["event_date_is_planned"], "1")
            self.assertEqual(by_native["CIP-NEW"]["event_date_is_after_snapshot"], "1")

            summary = monthly_cohorts.write_outputs(
                rows,
                processed / "activity_by_month.csv",
                monthly_events,
                planned_events,
            )
            self.assertEqual(summary["row_count"], 3)
            self.assertEqual(summary["monthly_event_record_count"], 2)
            self.assertEqual(summary["planned_event_record_count"], 1)
            self.assertEqual(summary["monthly_events"]["month_count"], 2)
            self.assertEqual(summary["planned_events"]["month_count"], 1)
            self.assertTrue((monthly_events / "2025-04.csv").exists())
            self.assertTrue((monthly_events / "2022-02.csv").exists())
            self.assertFalse((monthly_events / "2026-10.csv").exists())
            self.assertTrue((planned_events / "2026-10.csv").exists())

    def test_future_non_plan_is_rejected_from_researcher_extracts(self) -> None:
        row = {field: "" for field in monthly_cohorts.COHORT_FIELDS}
        row.update({
            "record_id": "rec-future",
            "event_date": "2026-09-01",
            "event_month": "2026-09",
            "event_date_is_planned": "0",
            "event_date_is_after_snapshot": "1",
            "snapshot_date": "2026-08-23",
        })
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "must be explicit plans"):
                monthly_cohorts.write_outputs(
                    [row],
                    root / "activity_by_month.csv",
                    root / "monthly_events",
                    root / "planned_events",
                )


if __name__ == "__main__":
    unittest.main()
