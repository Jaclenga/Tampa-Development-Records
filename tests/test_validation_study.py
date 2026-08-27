from __future__ import annotations

import unittest
from collections import Counter

from scripts import review_metrics, validation_study


class ValidationStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.activities = validation_study.read_csv(
            validation_study.PROCESSED / "tampa_development_activity.csv"
        )
        cls.matches = validation_study.read_csv(
            validation_study.PROCESSED / "parcel_building_matches.csv"
        )

    def test_draw_is_reproducible_and_disjoint(self) -> None:
        first_a, second_a = validation_study.draw_sample(self.activities, self.matches)
        first_b, second_b = validation_study.draw_sample(self.activities, self.matches)
        self.assertEqual(
            [row["activity_id"] for row in first_a],
            [row["activity_id"] for row in first_b],
        )
        self.assertEqual(
            [row["audit_sample_id"] for row in second_a],
            [row["audit_sample_id"] for row in second_b],
        )
        development = {row["activity_id"] for row in first_a if row["sample_phase"] == "development"}
        holdout = {row["activity_id"] for row in first_a if row["sample_phase"] == "holdout"}
        self.assertTrue(development.isdisjoint(holdout))
        self.assertEqual((len(development), len(holdout)), (100, 50))

    def test_frozen_phase_stratum_quotas(self) -> None:
        first, second = validation_study.draw_sample(self.activities, self.matches)
        first_counts = Counter((row["sample_phase"], row["sampling_stratum"]) for row in first)
        second_counts = Counter((row["sample_phase"], row["sampling_stratum"]) for row in second)
        for phase, quotas in validation_study.PHASE_QUOTAS.items():
            for stratum, quota in quotas.items():
                self.assertEqual(first_counts[(phase, stratum)], quota)
        for phase, quotas in validation_study.SECOND_REVIEW_QUOTAS.items():
            for stratum, quota in quotas.items():
                self.assertEqual(second_counts[(phase, stratum)], quota)

    def test_second_review_is_blinded(self) -> None:
        first, second = validation_study.draw_sample(self.activities, self.matches)
        first_ids = {row["audit_sample_id"] for row in first}
        self.assertTrue(all(row["audit_sample_id"] in first_ids for row in second))
        self.assertTrue(
            all(not any(row[field] for field in validation_study.REVIEW_FIELDS) for row in second)
        )

    def test_rebuild_preserves_reviews_when_context_is_unchanged(self) -> None:
        first, _ = validation_study.draw_sample(self.activities, self.matches)
        old = dict(first[0])
        old["review_status"] = "in_progress"
        old["reviewer_id"] = "reviewer-a"
        validation_study.merge_reviews(first, [[old]], "test")
        self.assertEqual(first[0]["review_status"], "in_progress")
        self.assertEqual(first[0]["reviewer_id"], "reviewer-a")

    def test_wilson_and_kappa(self) -> None:
        interval = review_metrics.wilson(94, 100)
        self.assertIsNotNone(interval)
        self.assertLess(interval["lower"], 0.94)
        self.assertGreater(interval["upper"], 0.94)
        agreement = review_metrics.kappa([("yes", "yes"), ("yes", "no"), ("no", "no")])
        self.assertAlmostEqual(agreement["percent_agreement"], 2 / 3)
        self.assertIsNotNone(agreement["cohens_kappa"])


if __name__ == "__main__":
    unittest.main()
