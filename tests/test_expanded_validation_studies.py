from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest

from scripts import validation_sampling


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

STUDIES = {
    "manual_validation_accela_source_fidelity.csv": (200, "record_id"),
    "manual_validation_accela_normalization.csv": (125, "record_id"),
    "manual_validation_integration_links.csv": (100, "accela_record_id"),
    "manual_validation_change_events.csv": (75, "change_id"),
}
SECOND_STUDIES = {
    "manual_validation_accela_source_fidelity_second_review.csv": 50,
    "manual_validation_accela_normalization_second_review.csv": 31,
    "manual_validation_integration_links_second_review.csv": 25,
    "manual_validation_change_events_second_review.csv": 19,
}


def read(name: str) -> list[dict[str, str]]:
    with (PROCESSED / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ExpandedValidationStudyTests(unittest.TestCase):
    def test_shared_draw_is_deterministic_and_stratified(self):
        rows = [
            {"id": f"a-{index}", "sampling_stratum": "a"}
            for index in range(20)
        ] + [
            {"id": f"b-{index}", "sampling_stratum": "b"}
            for index in range(5)
        ]
        first = validation_sampling.deterministic_stratified_draw(
            rows,
            identity_field="id",
            stratum_field="sampling_stratum",
            target=10,
            seed=42,
            study_id="test",
            minimum_per_stratum=2,
        )
        second = validation_sampling.deterministic_stratified_draw(
            rows,
            identity_field="id",
            stratum_field="sampling_stratum",
            target=10,
            seed=42,
            study_id="test",
            minimum_per_stratum=2,
        )
        self.assertEqual([item.row["id"] for item in first], [item.row["id"] for item in second])
        self.assertEqual(len(first), 10)
        self.assertEqual({item.stratum for item in first}, {"a", "b"})

    def test_published_samples_have_expected_sizes_and_unique_units(self):
        for name, (expected, identity_field) in STUDIES.items():
            rows = read(name)
            self.assertEqual(len(rows), expected, name)
            identities = [row[identity_field] for row in rows]
            self.assertEqual(len(identities), len(set(identities)), name)
            self.assertEqual(len({row["validation_sample_id"] for row in rows}), expected, name)
            self.assertTrue(all(row["sampling_universe_sha256"] for row in rows))
            self.assertTrue(all(float(row["sampling_weight"]) >= 1 for row in rows))

    def test_accela_source_and_normalization_samples_do_not_overlap(self):
        source_ids = {row["record_id"] for row in read("manual_validation_accela_source_fidelity.csv")}
        normalization_ids = {row["record_id"] for row in read("manual_validation_accela_normalization.csv")}
        self.assertTrue(source_ids.isdisjoint(normalization_ids))

    def test_required_accela_and_linkage_strata_are_represented(self):
        source_strata = {row["sampling_stratum"] for row in read("manual_validation_accela_source_fidelity.csv")}
        self.assertTrue(any(value.startswith("Building|retrospective|") for value in source_strata))
        self.assertTrue(any(value.startswith("Planning|retrospective|") for value in source_strata))
        self.assertTrue(any("|prospective|" in value for value in source_strata))
        self.assertTrue(any(value.endswith("|relatively_rare_type") for value in source_strata))
        linkage_strata = {row["sampling_stratum"] for row in read("manual_validation_integration_links.csv")}
        self.assertEqual(linkage_strata, {"matched_gis_accela", "retained_unmatched_accela"})
        change_strata = {row["sampling_stratum"] for row in read("manual_validation_change_events.csv")}
        self.assertTrue({"new_record", "record_disappeared", "status_changed"}.issubset(change_strata))

    def test_review_outcomes_are_blank_or_explicit_and_no_generic_verified_field_exists(self):
        outcome_fields = {
            "manual_validation_accela_source_fidelity.csv": "source_fidelity_outcome",
            "manual_validation_accela_normalization.csv": "normalization_outcome",
            "manual_validation_integration_links.csv": "linkage_outcome",
            "manual_validation_change_events.csv": "change_validation_outcome",
        }
        allowed = {"", "yes", "no", "unknown", "not_applicable"}
        for name, outcome_field in outcome_fields.items():
            rows = read(name)
            self.assertTrue({row[outcome_field] for row in rows}.issubset(allowed))
            self.assertNotIn("verified", rows[0])

    def test_second_review_assignments_are_independent(self):
        for name, expected in SECOND_STUDIES.items():
            rows = read(name)
            self.assertEqual(len(rows), expected, name)
            self.assertEqual(len({row["second_review_assignment_id"] for row in rows}), expected)
            for row in rows:
                self.assertEqual(row["first_reviewer_code"], "")
                self.assertEqual(row["first_outcome"], "")
                self.assertEqual(row["second_outcome"], "")

    def test_frozen_writer_refuses_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "primary.csv"
            second = root / "second.csv"
            primary.write_text("validation_sample_id\nx\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                validation_sampling.write_frozen_study(
                    primary_path=primary,
                    second_path=second,
                    primary_rows=[],
                    second_rows=[],
                    context_fields=(),
                    review_fields=(),
                    force=False,
                )

    def test_verification_summary_reconciles_study_files_and_not_measured(self):
        with (ROOT / "verification" / "verification_summary.csv").open(encoding="utf-8", newline="") as handle:
            summary = {row["verification_type"]: row for row in csv.DictReader(handle)}
        expected = {
            "core_eight_layer_manual_validation": (150, 10),
            "core_double_review": (25, 0),
            "targeted_accela_manual_audit": (75, 0),
            "initial_longitudinal_change_audit": (30, 0),
        }
        for study, (count, evaluated) in expected.items():
            self.assertEqual(int(summary[study]["eligible_records"]), count)
            self.assertEqual(int(summary[study]["evaluated_records"]), evaluated)
        external = summary["expanded_external_outcome_verification"]
        self.assertEqual(external["eligible_records"], "")
        self.assertEqual(external["coverage_percentage"], "")
        self.assertNotIn("composite", " ".join(summary))

    def test_documentation_separates_validity_concepts(self):
        verification = (ROOT / "verification" / "README.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for phrase in ("Source fidelity", "Transformation validity", "Real-world / outcome validity"):
            self.assertIn(phrase, verification)
        self.assertIn("selected before the Accela expansion", readme)
        self.assertIn("No composite verification score", readme)


if __name__ == "__main__":
    unittest.main()
