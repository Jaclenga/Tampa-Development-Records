from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
import unittest

from scripts import analyze_snapshot_changes, change_analysis


def snapshot(date: str, counts: dict[str, int]) -> dict[str, object]:
    return {
        "snapshot_date": date,
        "retrieved_at_utc": f"{date}T12:00:00+00:00",
        "record_count": sum(counts.values()),
        "source_counts": counts,
    }


def source_row(source: str, native: str, global_id: str, object_id: str = "1") -> dict[str, str]:
    return {
        "source_name": source,
        "source_record_id": native,
        "source_global_id": global_id,
        "source_object_id": object_id,
        "source_endpoint": "https://example.test/source",
        "retrieved_at_utc": "2026-09-30T12:00:00+00:00",
        "properties_json": "{}",
    }


def change(
    kind: str,
    identity: str,
    *,
    source: str = "permits",
    field: str = "",
    old: object = "",
    new: object = "",
    native: str = "N-1",
) -> dict[str, str]:
    return {
        "change_type": kind,
        "semantic_type": "",
        "source_name": source,
        "record_identity": identity,
        "source_record_id": native,
        "changed_fields": field,
        "old_value": json.dumps({field: old}) if field else str(old),
        "new_value": json.dumps({field: new}) if field else str(new),
        "source_url": "https://example.test/record",
    }


def analyze(
    before: dict,
    after: dict,
    changes: list[dict[str, str]],
    before_rows: list[dict[str, str]] | None = None,
    after_rows: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return change_analysis.analyze_comparison(
        before,
        after,
        before_rows or [],
        after_rows or [],
        changes,
        {"comparison_month": after["snapshot_date"][:7]},
        change_analysis.load_thresholds(),
    )


class ChangeAnalysisTests(unittest.TestCase):
    def test_healthy_and_no_change_comparisons(self) -> None:
        before = snapshot("2026-09-30", {"permits": 10})
        after = snapshot("2026-10-31", {"permits": 10})
        no_change = analyze(before, after, [])
        self.assertEqual(no_change["overall_status"], "healthy")
        self.assertEqual(no_change["overall"]["publication_churn"], 0.0)
        self.assertTrue(no_change["comparison"]["canonical_monthly_comparison"])

        ordinary = analyze(before, after, [
            change("record_disappeared", "p-old"),
            change("new_record", "p-new"),
        ])
        self.assertEqual(ordinary["overall_status"], "healthy")
        self.assertEqual(ordinary["overall"]["retained_records"], 9)
        self.assertAlmostEqual(ordinary["overall"]["publication_churn"], 2 / 11, places=6)

    def test_source_collapse_and_exclusion_view(self) -> None:
        before = snapshot("2026-08-23", {"single_family_permits": 1023, "other": 3446})
        after = snapshot("2026-09-01", {"single_family_permits": 280, "other": 3421})
        changes = [
            change("record_disappeared", f"sf-{index}", source="single_family_permits")
            for index in range(747)
        ] + [
            change("new_record", f"sf-new-{index}", source="single_family_permits")
            for index in range(4)
        ] + [
            change("record_disappeared", f"other-old-{index}", source="other")
            for index in range(30)
        ] + [
            change("new_record", f"other-new-{index}", source="other")
            for index in range(5)
        ]
        result = analyze(before, after, changes)
        codes = {item["alert_code"] for item in result["alerts"]}
        self.assertIn("source_count_collapse", codes)
        self.assertEqual(result["overall_status"], "critical")
        diagnostic = result["overall"]["excluding_critical_sources"]
        self.assertEqual(diagnostic["excluded_source_ids"], ["single_family_permits"])
        self.assertEqual((diagnostic["count_before"], diagnostic["count_after"]), (3446, 3421))
        self.assertEqual(diagnostic["absolute_net_change"], -25)
        self.assertFalse(result["trend_eligibility"]["usable_for_global_aggregate_trend"])
        self.assertTrue(result["trend_eligibility"]["usable_for_unflagged_source_trends"])

    def test_mass_field_refresh_deduplicates_identities(self) -> None:
        before = snapshot("2026-09-30", {"capital": 100})
        after = snapshot("2026-10-31", {"capital": 100})
        rows = [change("other_field_changed", f"c-{index}", source="capital", field="MapScale", old=1, new=2) for index in range(75)]
        rows.append(change("other_field_changed", "c-0", source="capital", field="MapScale", old=1, new=3))
        result = analyze(before, after, rows)
        field = result["field_change_concentration"][0]
        self.assertEqual(field["unique_retained_identities_affected"], 75)
        self.assertEqual(field["change_row_count"], 76)
        self.assertEqual(field["affected_retained_rate"], 0.75)
        self.assertTrue(field["mass_refresh_warning"])

    def test_duplicate_and_blank_native_ids_remain_identity_safe(self) -> None:
        before = snapshot("2026-09-30", {"capital": 3})
        after = snapshot("2026-10-31", {"capital": 3})
        rows = [source_row("capital", "DUP", "g-1", "1"), source_row("capital", "DUP", "g-2", "2"), source_row("capital", "", "g-3", "3")]
        changes = [
            change("status_changed", "CAPITAL|NATIVE|DUP|GLOBALID|G-1", source="capital", field="status", old="A", new="B", native="DUP"),
            change("status_changed", "CAPITAL|NATIVE|DUP|GLOBALID|G-2", source="capital", field="status", old="A", new="C", native="DUP"),
        ]
        result = analyze(before, after, changes, rows, rows)
        quality = result["identity_quality"]
        self.assertEqual(quality["duplicate_native_id_groups_before"], 1)
        self.assertEqual(quality["blank_native_ids_after"], 1)
        self.assertEqual(quality["duplicate_canonical_identities_after"], 0)
        self.assertEqual(quality["native_ids_with_multiple_canonical_identities"][0]["canonical_identity_count"], 2)

    def test_blank_and_malformed_links_are_reported(self) -> None:
        before = snapshot("2026-09-30", {"permits": 2})
        after = snapshot("2026-10-31", {"permits": 2})
        rows = [change("status_changed", "p-1", field="status", old="A", new="B"), change("status_changed", "p-2", field="status", old="A", new="B")]
        rows[0]["source_url"] = ""
        rows[1]["source_url"] = "not a link"
        quality = analyze(before, after, rows)["identity_quality"]
        self.assertEqual(quality["blank_source_links"], 1)
        self.assertEqual(quality["malformed_source_links"], 1)

    def test_interval_classification(self) -> None:
        thresholds = change_analysis.load_thresholds()
        self.assertEqual(change_analysis.classify_comparison("2026-08-23", "2026-09-01", thresholds), ("baseline_followup", False))
        self.assertEqual(change_analysis.classify_comparison("2026-09-30", "2026-10-31", thresholds), ("month_end_to_month_end", True))
        self.assertEqual(change_analysis.classify_comparison("2026-09-01", "2026-09-15", thresholds), ("manual_interval", False))

    def test_undefined_denominators_are_null(self) -> None:
        result = analyze(snapshot("2026-09-30", {"new_source": 0}), snapshot("2026-10-31", {"new_source": 1}), [change("new_record", "n-1", source="new_source")])
        source = result["source_health"][0]
        self.assertIsNone(source["percentage_delta"])
        self.assertIsNone(source["retention_rate"])
        self.assertIsNone(source["disappearance_rate"])

    def test_status_phase_date_and_cost_classification(self) -> None:
        before = snapshot("2026-09-30", {"capital": 8})
        after = snapshot("2026-10-31", {"capital": 8})
        rows = [
            change("status_changed", "c-1", source="capital", field="status", old="Design", new="Review"),
            change("capital_project_phase_changed", "c-2", source="capital", field="capital_phase", old="P2", new="P3"),
            change("planned_date_changed", "c-3", source="capital", field="planned_end", old="2026-10-10", new="2026-10-20"),
            change("planned_date_changed", "c-4", source="capital", field="planned_end", old="2026-10-20", new="2026-10-10"),
            change("estimated_cost_changed", "c-5", source="capital", field="estimated_cost", old="100", new="150"),
            change("estimated_cost_changed", "c-6", source="capital", field="estimated_cost", old="150", new="100"),
            change("estimated_cost_changed", "c-7", source="capital", field="estimated_cost", old="", new="100"),
            change("reported_actual_cost_changed", "c-8", source="capital", field="actual_cost", old="100", new=""),
        ]
        result = analyze(before, after, rows)
        self.assertEqual(result["status_transitions"][0]["unique_record_count"], 1)
        self.assertEqual(result["phase_transitions"][0]["unique_record_count"], 1)
        self.assertEqual({row["classification"] for row in result["planned_date_changes"]["events"]}, {"moved_earlier", "moved_later"})
        self.assertEqual({row["classification"] for row in result["cost_changes"]["events"]}, {"increase", "decrease", "value_added", "value_removed"})

    def test_acceptance_fixture(self) -> None:
        result, _ = change_analysis.analyze_paths("2026-08-23", "2026-09-01")
        self.assertEqual(result["comparison"]["interval_days"], 9)
        self.assertEqual(result["comparison"]["comparison_kind"], "baseline_followup")
        self.assertFalse(result["comparison"]["canonical_monthly_comparison"])
        self.assertEqual((result["overall"]["count_before"], result["overall"]["count_after"]), (4469, 4408))
        self.assertEqual((result["overall"]["new_records"], result["overall"]["disappeared_records"]), (208, 269))
        self.assertEqual(result["overall"]["unique_changed_record_identities"], 2103)
        self.assertEqual(result["overall"]["total_change_rows"], 2822)
        source = next(row for row in result["source_health"] if row["source_id"] == "single_family_permits")
        self.assertEqual((source["before_count"], source["after_count"], source["new_records"], source["disappeared_records"]), (1023, 1016, 24, 31))
        self.assertTrue(result["collection_integrity"]["passed"])
        self.assertNotIn("collection_integrity_failure", {row["alert_code"] for row in result["alerts"]})
        self.assertFalse(result["trend_eligibility"]["usable_for_global_aggregate_trend"])

    def test_artifacts_are_byte_deterministic(self) -> None:
        result, changes = change_analysis.analyze_paths("2026-08-23", "2026-09-01")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            change_analysis.write_analysis_artifacts(result, analysis_dir=root)
            first = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir()}
            change_analysis.write_analysis_artifacts(result, analysis_dir=root)
            second = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir()}
            self.assertEqual(first, second)
        first_markdown = analyze_snapshot_changes.render_report(result, changes).encode("utf-8")
        second_markdown = analyze_snapshot_changes.render_report(result, changes).encode("utf-8")
        self.assertEqual(hashlib.sha256(first_markdown).digest(), hashlib.sha256(second_markdown).digest())


if __name__ == "__main__":
    unittest.main()
