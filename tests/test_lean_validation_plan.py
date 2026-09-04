from __future__ import annotations

import csv
import unittest
from collections import Counter

from scripts import build_lean_validation_plan as lean


def read(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class LeanValidationPlanTests(unittest.TestCase):
    def test_active_plan_has_expected_burden_and_allocations(self):
        core = read(lean.CORE_OUTPUT)
        accela = read(lean.ACCELA_OUTPUT)
        longitudinal = read(lean.LONGITUDINAL_OUTPUT)
        self.assertEqual((len(core), len(accela), len(longitudinal)), (25, 75, 30))
        self.assertEqual(Counter(row["sampling_stratum"] for row in core), Counter(lean.CORE_QUOTAS))
        self.assertEqual(
            Counter(row["audit_component"] for row in accela),
            Counter({"source_fidelity_spot_check": 15, "normalization_and_semantics": 30, "linkage_and_deduplication": 30}),
        )
        self.assertEqual(Counter(row["risk_tier"] for row in longitudinal), Counter({"high_impact": 20, "control": 10}))

    def test_published_plan_matches_deterministic_selection(self):
        expected_core, _ = lean.build_core_reliability()
        self.assertEqual(read(lean.CORE_OUTPUT), expected_core)
        self.assertEqual(read(lean.ACCELA_OUTPUT), lean.build_accela_portfolio())
        self.assertEqual(read(lean.LONGITUDINAL_OUTPUT), lean.build_longitudinal_subset())


if __name__ == "__main__":
    unittest.main()
