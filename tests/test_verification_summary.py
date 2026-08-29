import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_verification_summary import (
    latest_snapshot_metadata,
    load_manual_reviews,
    require_unique,
    summarize_automated_qa,
    summarize_reviews,
)


def review(identifier, status="", outcome="", second=False):
    return {
        "audit_sample_id": identifier,
        "review_status": status,
        "outcome": outcome,
        "second": "yes" if second else "no",
    }


class VerificationSummaryTests(unittest.TestCase):
    def test_zero_reviewed_records(self):
        result = summarize_reviews(
            [review("a"), review("b")], outcome_field="outcome", allowed_outcomes={"supported", "unknown"}
        )
        self.assertEqual((result.eligible, result.evaluated, result.awaiting), (2, 0, 2))

    def test_partially_reviewed_sample_and_unknown(self):
        rows = [review("a", "complete", "supported"), review("b", "complete", "unknown"), review("c")]
        result = summarize_reviews(rows, outcome_field="outcome", allowed_outcomes={"supported", "unknown"})
        self.assertEqual((result.evaluated, result.supported, result.unknown, result.awaiting), (2, 1, 1, 1))

    def test_completely_reviewed_sample(self):
        rows = [review("a", "complete", "supported"), review("b", "complete", "contradicted")]
        result = summarize_reviews(
            rows, outcome_field="outcome", allowed_outcomes={"supported", "contradicted"}
        )
        self.assertEqual((result.eligible, result.evaluated, result.awaiting), (2, 2, 0))

    def test_duplicate_review_records_fail_loudly(self):
        with self.assertRaises(ValueError):
            require_unique([review("a"), review("a")], "audit_sample_id", "test")

    def test_second_reviews_use_their_own_denominator(self):
        assigned_second_reviews = [review("a", "complete", second=True), review("b", second=True)]
        result = summarize_reviews(assigned_second_reviews)
        self.assertEqual((result.eligible, result.evaluated, result.awaiting), (2, 1, 1))

    def test_denominator_is_eligible_rows_not_evaluated_rows(self):
        result = summarize_reviews([review("a", "complete"), review("b"), review("c")])
        self.assertEqual(result.eligible, 3)
        self.assertEqual(result.evaluated, 1)

    def test_unknown_outcome_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "partal"):
            summarize_reviews(
                [review("a", "complete", "partal")],
                outcome_field="outcome",
                allowed_outcomes={"supported", "partial"},
            )

    def test_failed_aggregate_qa_does_not_mark_every_record_failed(self):
        counts, issues, check_counts = summarize_automated_qa(
            {
                "counts": {"source_records": 10, "raw_features": 10},
                "checks": {"row_schema": True, "manifest_hash": False},
                "mismatch_counts": {},
            }
        )
        self.assertEqual((counts.supported, counts.conflicting), (0, 0))
        self.assertEqual(issues, ["manifest_hash"])
        self.assertEqual(check_counts, {"evaluated": 2, "passed": 1, "flagged": 1})

    def test_latest_snapshot_is_discovered(self):
        with tempfile.TemporaryDirectory(dir=".") as temporary:
            root = Path(temporary)
            for date in ("2026-08-23", "2026-09-01"):
                directory = root / date
                directory.mkdir()
                (directory / "metadata.json").write_text(
                    json.dumps({"snapshot_date": date}), encoding="utf-8"
                )
            self.assertEqual(latest_snapshot_metadata(root)["snapshot_date"], "2026-09-01")

    def test_snapshot_can_be_selected_by_release_content_hash(self):
        with tempfile.TemporaryDirectory(dir=".") as temporary:
            root = Path(temporary)
            for date, content_hash in (("2026-08-23", "release-hash"), ("2026-09-01", "newer-hash")):
                directory = root / date
                directory.mkdir()
                (directory / "metadata.json").write_text(
                    json.dumps({"snapshot_date": date, "source_records_content_sha256": content_hash}),
                    encoding="utf-8",
                )
            selected = latest_snapshot_metadata(root, content_hash="release-hash")
            self.assertEqual(selected["snapshot_date"], "2026-08-23")

    def test_phase_files_are_authoritative_for_review_progress(self):
        with tempfile.TemporaryDirectory(dir=".") as temporary:
            root = Path(temporary)

            def write(name, rows):
                with (root / name).open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(
                        handle, fieldnames=("audit_sample_id", "sample_phase", "review_status")
                    )
                    writer.writeheader()
                    writer.writerows(rows)

            development = {"audit_sample_id": "dev-001", "sample_phase": "development", "review_status": "complete"}
            holdout = {"audit_sample_id": "hol-001", "sample_phase": "holdout", "review_status": ""}
            write("manual_validation_development_sample.csv", [development])
            write("manual_validation_holdout_sample.csv", [holdout])
            write(
                "manual_validation_sample.csv",
                [dict(development, review_status=""), dict(holdout, review_status="")],
            )
            rows = load_manual_reviews(root)
            self.assertEqual(rows[0]["review_status"], "complete")


if __name__ == "__main__":
    unittest.main()
