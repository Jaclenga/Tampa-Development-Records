from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import unittest

from scripts import build_agent_benchmark as benchmark
from scripts.verify_agent_benchmark_freeze import DEFAULT_FREEZE, verify_freeze


ROOT = Path(__file__).resolve().parents[1]
FROZEN_SAMPLE = ROOT / "data" / "processed" / "manual_validation_sample.csv"
PUBLISHED_BENCHMARK = ROOT / "data" / "agentic_validation" / "benchmark_v1.json"
EXPECTED_FROZEN_SHA256 = "2855ccef25e39b59cfb5eb48a3d7201a5fc6b6acfdd6b856e7c24cf8b653c4ce"


class AgentBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.columns = benchmark.read_sample(FROZEN_SAMPLE)
        cls.payload = benchmark.build_benchmark(
            cls.rows,
            input_path="data/processed/manual_validation_sample.csv",
            input_sha256=benchmark.sha256_file(FROZEN_SAMPLE),
        )

    def test_frozen_input_has_expected_hash_and_is_not_modified(self) -> None:
        before = benchmark.sha256_file(FROZEN_SAMPLE)
        benchmark.build_benchmark(
            self.rows,
            input_path="data/processed/manual_validation_sample.csv",
            input_sha256=before,
        )
        after = benchmark.sha256_file(FROZEN_SAMPLE)
        self.assertEqual(before, EXPECTED_FROZEN_SHA256)
        self.assertEqual(after, before)
        self.assertFalse(self.payload["input"]["frozen_sample_modified"])

    def test_selection_is_hash_ranked_stratified_and_repeatable(self) -> None:
        reordered = list(reversed(self.rows))
        second = benchmark.build_benchmark(
            reordered,
            input_path="data/processed/manual_validation_sample.csv",
            input_sha256=EXPECTED_FROZEN_SHA256,
        )
        first_ids = [case["benchmark_case_id"] for case in self.payload["cases"]]
        second_ids = [case["benchmark_case_id"] for case in second["cases"]]
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), 18)
        self.assertEqual(len(first_ids), len(set(first_ids)))
        expected_quotas = dict(benchmark.CATEGORY_QUOTAS)
        observed = Counter(case["selection"]["primary_category"] for case in self.payload["cases"])
        self.assertEqual(dict(observed), expected_quotas)
        self.assertTrue(all(len(case["selection"]["sha256_rank"]) == 64 for case in self.payload["cases"]))
        for case in self.payload["cases"]:
            category = case["selection"]["primary_category"]
            sample_id = case["investigation_request"]["sample_id"]
            self.assertEqual(
                case["selection"]["sha256_rank"],
                benchmark.selection_hash(benchmark.DEFAULT_SEED, category, sample_id),
            )

    def test_requests_only_copy_explicit_context_and_leave_claims_unresolved(self) -> None:
        by_id = {row["audit_sample_id"]: row for row in self.rows}
        for case in self.payload["cases"]:
            request = case["investigation_request"]
            row = by_id[request["sample_id"]]
            self.assertEqual(request["activity_id"], row["activity_id"])
            self.assertEqual(request["record_number"], row["source_record_id"])
            self.assertEqual(request["record_type"], row["record_type"])
            self.assertEqual(request["address"], row["address"])
            self.assertEqual(request["known_dates"], {})
            self.assertTrue(request["unresolved_claims"])
            for claim in request["unresolved_claims"]:
                self.assertIn(claim["basis_field"], self.columns)
                self.assertEqual(claim["basis_value"], row[claim["basis_field"]])
            baseline = case["comparison_baseline"]
            self.assertEqual(baseline["status"], "not_run")
            self.assertEqual(baseline["deterministic_only"], "not_run")
            self.assertEqual(baseline["deterministic_plus_agentic"], "not_run")
            self.assertNotIn("verified", json.dumps(case).lower())

    def test_explicit_edge_signals_and_source_types_are_represented(self) -> None:
        cases = self.payload["cases"]
        categories = {case["selection"]["primary_category"] for case in cases}
        self.assertEqual(categories, {category for category, _ in benchmark.CATEGORY_QUOTAS})
        source_types = set(self.payload["counts"]["source_types"])
        self.assertGreaterEqual(len(source_types), 3)
        self.assertIn("construction_inspections", source_types)
        selected_conflicts = [
            case for case in cases
            if case["selection"]["primary_category"] == "potential_conflicting_evidence"
        ]
        self.assertEqual(len(selected_conflicts), 2)
        for case in selected_conflicts:
            row = next(
                row for row in self.rows
                if row["audit_sample_id"] == case["investigation_request"]["sample_id"]
            )
            self.assertEqual(row["realization_evidence_grade"], "X")
            self.assertIn(row["status"].lower(), {"cancelled", "canceled", "inactive"})

    def test_published_json_matches_builder_exactly(self) -> None:
        published = json.loads(PUBLISHED_BENCHMARK.read_text(encoding="utf-8"))
        self.assertEqual(published, self.payload)

    def test_pre_human_audit_agent_freeze_is_intact(self) -> None:
        result = verify_freeze(DEFAULT_FREEZE)
        manifest = json.loads(DEFAULT_FREEZE.read_text(encoding="utf-8"))
        self.assertEqual(result["freeze_id"], "tdr-agent-benchmark-pre-human-audit-v1")
        self.assertEqual(manifest["active_agent_runs"], ["run_a", "run_b", "run_c"])
        self.assertEqual(manifest["excluded_exploratory_runs"], ["run_d", "run_e", "run_f"])
        self.assertFalse(manifest["human_audit_completed_at_freeze"])


if __name__ == "__main__":
    unittest.main()
