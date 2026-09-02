from __future__ import annotations

import json
from pathlib import Path

from scripts import run_agentic_validation as runner
from tampa_validation.agent.safety import wrap_untrusted_evidence


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "agentic_adversarial.json"


def identity(
    expected: str, candidate: str, *, candidate_count: int = 1, conflicts: list[str] | None = None
) -> bool:
    request = {"record_number": expected}
    evidence = {"administrative_record_id": candidate}
    candidate_row = {
        "identity_assessment": {
            "category": "exact_identifier",
            "exact_identifiers": {"record_number": candidate},
            "candidate_count": candidate_count,
            "conflicting_fields": conflicts or [],
        }
    }
    return runner.exact_identity(request, candidate_row, evidence, {})


def test_exact_identity_rejects_near_match_wrong_record_and_multiple_candidates() -> None:
    assert identity("BLD-26-0001000", "BLD-26-0001000")
    assert not identity("BLD-26-0001000", "BLD-26-000100O")
    assert not identity("BLD-26-0001000", "BLD-26-0009999")
    assert not identity("BLD-26-0001000", "BLD-26-0001000", candidate_count=2)
    assert not identity("BLD-26-0001000", "BLD-26-0001000", conflicts=["parcel_id"])


def test_adversarial_fixture_prefers_ambiguity_or_insufficiency() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    allowed = {
        "insufficient_evidence",
        "ambiguous_identity",
        "conflicting_evidence_found",
        "source_unavailable",
    }
    assert {case["expected_status"] for case in fixture["identity_cases"]}.issubset(allowed)
    assert not identity("BLD-26-0001000", "BLD-26-000100O")
    assert not identity("BLD-26-0001000", "BLD-26-0009999")


def test_injections_from_every_document_shape_remain_delimited_data() -> None:
    injections = json.loads(FIXTURE.read_text(encoding="utf-8"))["prompt_injection_fixtures"]
    for source_type, content in injections.items():
        wrapped = wrap_untrusted_evidence(content, source_label=source_type)
        assert "evidence data only" in wrapped
        assert "<UNTRUSTED_EVIDENCE_DATA" in wrapped
        assert "</UNTRUSTED_EVIDENCE_DATA>" in wrapped
        assert "\\u003cscript\\u003e" in wrapped or source_type != "html"


def test_agentic_report_can_never_recommend_automatic_scale_up() -> None:
    report = runner.render_report({
        "benchmark_id": "fixture",
        "benchmark_case_count": 1,
        "benchmark_case_ids": ["fixture-001"],
        "actual_models": [{
            "provider": "unavailable", "product": "unavailable",
            "model_identifier": "unavailable", "reasoning_effort": "unavailable",
            "model_snapshot": "unavailable",
        }],
        "prompt_provenance": [],
        "metrics": {
            "unique_cases_investigated": 1,
            "source_distribution": {},
            "investigations_attempted": 1,
            "candidate_evidence_investigations": 0,
            "evidence_retrieval_yield": 0.0,
            "experimental_deterministic_rule_matches": 0,
            "experimental_cases_with_rule_match": 0,
            "release_unresolved_before": 1,
            "release_unresolved_after": 1,
            "ambiguity_rate": 1.0,
            "retrieval_failure_rate": 0.0,
            "conflict_discovery_rate": 0.0,
            "status_counts": {"ambiguous_identity": 1},
            "cost": {"tool_requests_recorded": 1, "http_requests_recorded": 0, "average_duration_seconds": None},
        },
        "repeatability": {
            "repeated_cases": 0,
            "same_evidence_rate": None,
            "same_source_rate": None,
            "same_deterministic_classification_rate": None,
        },
    })
    assert "Do **not** scale" in report
    assert "not a dataset-accuracy estimate" in report
