#!/usr/bin/env python3
"""Audit recorded agent investigations and run deterministic evidence handoff.

This command never calls a model and never edits a frozen validation sample.
Agent invocations occur in a separately authorized environment and are ingested
as immutable, structured research observations.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from tampa_validation.agent.prompts import prompt_manifest, verify_prompt_hashes  # noqa: E402
from tampa_validation.agent.safety import (  # noqa: E402
    ALLOWED_INVESTIGATION_STATUSES,
    assert_safe_agent_output,
)
from tampa_validation.agent.sources import SourceTier, assess_source  # noqa: E402
from verify_agent_benchmark_freeze import DEFAULT_FREEZE, verify_freeze  # noqa: E402


BENCHMARK = ROOT / "data" / "agentic_validation" / "benchmark_v1.json"
RESPONSES = ROOT / "data" / "agentic_validation" / "recorded_responses"
RULES = ROOT / "config" / "agent_evidence_rules.json"
CONFIG = ROOT / "config" / "agentic_validation.json"
FROZEN_SAMPLE = ROOT / "data" / "processed" / "manual_validation_sample.csv"
RUNS = ROOT / "reports" / "agentic_runs"
REPORT = ROOT / "reports" / "AGENTIC_VALIDATION_REPORT.md"
RUNNER_VERSION = "1.0.0"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_evidence_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    evidence_root = (ROOT / "data" / "agentic_validation" / "evidence").resolve()
    if evidence_root not in path.parents:
        raise ValueError(f"evidence path escapes archive root: {value}")
    return path


def evidence_path(candidate: dict[str, Any]) -> str:
    return str(candidate.get("archived_path") or candidate.get("evidence_path") or "")


def evidence_hash(candidate: dict[str, Any]) -> str:
    return str(candidate.get("content_sha256") or candidate.get("sha256") or "").lower()


def candidate_identity(candidate: dict[str, Any], investigation: dict[str, Any]) -> dict[str, Any]:
    identity = candidate.get("identity_assessment") or candidate.get("identity") or {}
    if not identity:
        identity = investigation.get("identity_assessment") or {}
    return identity if isinstance(identity, dict) else {}


def source_tier(candidate: dict[str, Any], evidence: dict[str, Any]) -> str:
    raw = str(candidate.get("source_tier") or evidence.get("source_tier") or "")
    aliases = {
        "archived_primary": SourceTier.ARCHIVED_PRIMARY.value,
        "live_primary": SourceTier.LIVE_PRIMARY.value,
        "primary_archived": SourceTier.ARCHIVED_PRIMARY.value,
        "primary_live": SourceTier.LIVE_PRIMARY.value,
    }
    return aliases.get(raw, raw)


def claims_for(investigation: dict[str, Any]) -> list[str]:
    claims = investigation.get("investigated_claims")
    if claims is None:
        claim = investigation.get("claim")
        claims = [claim] if claim else []
    return [str(claim) for claim in claims]


def validate_model_metadata(metadata: dict[str, Any]) -> None:
    if "product" not in metadata and metadata.get("product_api"):
        metadata["product"] = metadata["product_api"]
    if "model_snapshot" not in metadata and metadata.get("model_snapshot_version"):
        metadata["model_snapshot"] = metadata["model_snapshot_version"]
    required = ("provider", "product", "model_identifier", "reasoning_effort")
    for field in required:
        if not str(metadata.get(field, "")).strip():
            raise ValueError(f"actual model metadata is missing {field}")
    for field in ("model_snapshot", "temperature", "seed"):
        if metadata.get(field) in {None, ""}:
            raise ValueError(f"unknown model metadata must say unavailable: {field}")


def normalized_model_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    validate_model_metadata(metadata)
    return {
        "provider": metadata["provider"],
        "product": metadata["product"],
        "model_identifier": metadata["model_identifier"],
        "reasoning_effort": metadata["reasoning_effort"],
        "model_snapshot": metadata["model_snapshot"],
        "temperature": metadata["temperature"],
        "seed": metadata["seed"],
        "generation_parameters": metadata.get("generation_parameters", "unavailable"),
    }


def validate_prompt_provenance(records: Any, expected: list[dict[str, str]]) -> None:
    if isinstance(records, dict):
        normalized = [
            {"name": name, **value} if isinstance(value, dict) else {"name": name}
            for name, value in records.items()
        ]
    else:
        normalized = list(records or [])
    observed = {
        (str(item.get("name")), str(item.get("version")), str(item.get("prompt_hash") or item.get("sha256")))
        for item in normalized
    }
    required = {(item["name"], item["version"], item["prompt_hash"]) for item in expected}
    if observed != required:
        raise ValueError("recorded prompt provenance does not match the committed prompt manifest")


def validate_budget(investigation: dict[str, Any], config: dict[str, Any]) -> None:
    budget = config["investigation_budget"]
    actions = investigation.get("tool_actions") or []
    if len(actions) > budget["max_tool_calls"]:
        raise ValueError("recorded investigation exceeded max_tool_calls")
    allowed_tools = set(config["tool_policy"]["allowed_tools"])
    names = [str(action.get("tool") or action.get("action") or "") for action in actions]
    if any(name not in allowed_tools for name in names):
        raise ValueError("recorded investigation used a tool outside the allowlist")
    query_actions = [
        action
        for action in actions
        if str(action.get("tool") or action.get("action") or "").startswith("search_")
    ]
    if len(query_actions) > budget["max_source_queries"]:
        raise ValueError("recorded investigation exceeded max_source_queries")
    fingerprints = Counter(
        canonical_hash([
            action.get("tool") or action.get("action"),
            action.get("query") or action.get("parameters"),
        ])
        for action in query_actions
    )
    if any(count - 1 > budget["max_repeated_queries"] for count in fingerprints.values()):
        raise ValueError("recorded investigation exceeded max_repeated_queries")
    numeric_limits = (
        ("input_tokens", "max_input_tokens"),
        ("output_tokens", "max_output_tokens"),
        ("model_cost_usd", "max_cost_usd"),
        ("wall_clock_seconds", "max_duration_seconds"),
    )
    usage = investigation.get("cost_usage") or {}
    for usage_key, limit_key in numeric_limits:
        value = usage.get(usage_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > budget[limit_key]:
            raise ValueError(f"recorded investigation exceeded {limit_key}")


def _source_url(payload: dict[str, Any], candidate: dict[str, Any]) -> str:
    return str(
        payload.get("url")
        or payload.get("url_or_endpoint")
        or payload.get("source_url")
        or payload.get("source_endpoint")
        or candidate.get("url")
        or ""
    )


def _validate_content_hash(candidate: dict[str, Any], payload: dict[str, Any], evidence_file_hash: str) -> str:
    """Validate either an evidence-file hash or an explicitly scoped source hash."""

    claimed_hash = evidence_hash(candidate)
    if claimed_hash == evidence_file_hash:
        return claimed_hash
    if claimed_hash != str(payload.get("content_sha256") or "").lower():
        raise ValueError("candidate content hash matches neither evidence file nor scoped source content")
    scope = str(payload.get("hash_scope") or "")
    if scope == "archived_source_file":
        original = str(payload.get("archived_source_path") or payload.get("original_archive_path") or "")
        if not original:
            raise ValueError("archived source hash has no source path")
        original_path = (ROOT / original).resolve()
        if ROOT.resolve() not in original_path.parents or not original_path.is_file():
            raise ValueError(f"archived source path is unavailable or out of scope: {original}")
        if sha256_file(original_path) != claimed_hash:
            raise ValueError(f"archived source hash mismatch: {original}")
    elif scope == "canonical_extracted_explicit_fields":
        fields = payload.get("extracted_explicit_fields")
        if not isinstance(fields, dict) or canonical_hash(fields) != claimed_hash:
            raise ValueError("canonical extracted-field hash mismatch")
    else:
        raise ValueError("non-file content hash is missing a recognized hash_scope")
    return claimed_hash


def _selected_evidence(payload: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Select and authenticate one record from an aggregate evidence envelope."""

    embedded = payload.get("evidence")
    if not isinstance(embedded, list):
        return payload
    evidence_id = str(candidate.get("evidence_id") or candidate.get("candidate_evidence_id") or "")
    matches = [item for item in embedded if isinstance(item, dict) and str(item.get("evidence_id")) == evidence_id]
    if len(matches) != 1:
        raise ValueError(f"aggregate evidence does not contain exactly one candidate {evidence_id}")
    selected = matches[0]
    claimed = str(selected.get("content_sha256") or selected.get("sha256") or "").lower()
    scope = str(selected.get("hash_scope") or "").lower()
    if "source_archived_path" in scope or "source_archived_path" in selected:
        original = str(selected.get("source_archived_path") or "")
        original_path = (ROOT / original).resolve()
        if ROOT.resolve() not in original_path.parents or not original_path.is_file():
            raise ValueError(f"embedded archived source is unavailable or out of scope: {original}")
        if sha256_file(original_path) != claimed:
            raise ValueError(f"embedded archived source hash mismatch: {original}")
    elif "observed_fields" in scope:
        if canonical_hash(selected.get("observed_fields") or {}) != claimed:
            raise ValueError("embedded observed-field hash mismatch")
    else:
        raise ValueError("embedded evidence has an unrecognized hash scope")
    return selected


def validate_evidence(candidate: dict[str, Any], *, allow_live: bool) -> tuple[dict[str, Any], str, str]:
    relative = evidence_path(candidate)
    if not relative:
        raise ValueError("candidate evidence is missing archived_path")
    path = relative_evidence_path(relative)
    if not path.is_file():
        raise FileNotFoundError(f"archived evidence is missing: {relative}")
    observed_hash = sha256_file(path)
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"structured evidence must be a JSON object: {relative}")
    content_hash = _validate_content_hash(candidate, payload, observed_hash)
    selected = _selected_evidence(payload, candidate)
    tier = source_tier(candidate, selected)
    state = str(selected.get("source_state") or candidate.get("source_state") or "")
    if not state:
        state = "live" if tier == SourceTier.LIVE_PRIMARY.value else "archived"
    if state == "live" and not allow_live:
        raise ValueError("recorded live evidence requires --allow-recorded-live")
    url = _source_url(selected, candidate)
    decision = assess_source(url or None, archived=state == "archived")
    if not decision.allowed:
        raise ValueError(f"evidence source is not allowlisted ({decision.reason}): {relative}")
    if tier != (decision.tier.value if decision.tier else ""):
        raise ValueError(f"recorded source tier disagrees with deterministic policy: {relative}")
    return selected, observed_hash, content_hash


def exact_identity(
    request: dict[str, Any], candidate: dict[str, Any], evidence: dict[str, Any], investigation: dict[str, Any]
) -> bool:
    expected = str(request.get("record_number") or "").strip()
    if not expected:
        return False
    identity = candidate_identity(candidate, investigation)
    category = str(identity.get("identity_category") or identity.get("category") or identity.get("confidence") or "")
    candidate_count = identity.get("candidate_count")
    conflicts = identity.get("conflicting_fields") or []
    exact = identity.get("exact_identifiers") or {}
    if isinstance(exact, dict):
        exact_values = {str(value).strip() for value in exact.values()}
    elif isinstance(exact, list):
        exact_values = {str(value).strip() for value in exact}
    else:
        exact_values = set()
    fields = (
        evidence.get("extracted_fields")
        or evidence.get("extracted_explicit_fields")
        or evidence.get("observed_fields")
        or {}
    )
    archived_identifier = str(
        evidence.get("administrative_record_id")
        or evidence.get("record_number")
        or fields.get("record_number")
        or fields.get("project_id")
        or ""
    ).strip()
    return (
        category == "exact_identifier"
        and candidate_count == 1
        and not conflicts
        and expected in exact_values
        and archived_identifier == expected
    )


def deterministic_evaluation(
    investigation: dict[str, Any], request: dict[str, Any], evidence_rows: list[tuple[dict[str, Any], dict[str, Any], str]], rules: dict[str, Any]
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    by_claim = {rule.get("claim"): rule for rule in rules.get("rules", []) if rule.get("claim")}
    for claim in claims_for(investigation):
        rule = by_claim.get(claim)
        passed_evidence: list[str] = []
        if rule:
            for candidate, evidence, observed_hash in evidence_rows:
                tier = source_tier(candidate, evidence)
                if tier not in {SourceTier.ARCHIVED_PRIMARY.value, SourceTier.LIVE_PRIMARY.value}:
                    continue
                if not exact_identity(request, candidate, evidence, investigation):
                    continue
                fields = (
                    evidence.get("extracted_fields")
                    or evidence.get("extracted_explicit_fields")
                    or evidence.get("observed_fields")
                    or candidate.get("extracted_fields")
                    or {}
                )
                passed = claim == "source_identity"
                if claim == "final_inspection_passed":
                    inspection_type = str(fields.get("inspection_type") or "").lower()
                    result = str(fields.get("inspection_result") or "").lower()
                    passed = "final" in inspection_type and result in rule.get("allowed_passed_values", []) and bool(fields.get("inspection_date"))
                elif claim == "certificate_of_occupancy_issued":
                    passed = bool(fields.get("certificate_of_occupancy_date") or fields.get("certificate_of_occupancy_id")) and not bool(fields.get("temporary_only"))
                if passed:
                    passed_evidence.append(observed_hash)
        experimental_supported = bool(rule and passed_evidence)
        evaluations.append({
            "claim": claim,
            "before": "unresolved",
            "after": "automatically_supported" if experimental_supported else "unresolved_requires_human_review",
            "discovered_by": "agent" if evidence_rows else None,
            "evaluated_by": "deterministic_rule" if rule else "no_approved_rule_available",
            "rule_id": rule.get("rule_id") if rule else None,
            "rule_set_version": rules["rule_set_version"],
            "evidence_sha256": sorted(passed_evidence),
            "experimental_only": True,
            "release_write_enabled": False,
            "requires_human_review": True,
        })
    return evaluations


def numeric(values: list[Any]) -> list[float]:
    result = []
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            result.append(float(value))
    return result


def aggregate(
    investigations: list[dict[str, Any]], evaluations: list[dict[str, Any]], evidence_index: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    attempts = len(investigations)
    evidence_attempts = sum(bool(item.get("candidate_evidence")) for item in investigations)
    statuses = Counter(str(item["status"]) for item in investigations)
    sources = Counter()
    for evidence in evidence_index.values():
        url = _source_url(evidence, {})
        sources[urlsplit(url).hostname or "archived_without_host"] += 1
    supported = sum(
        row["after"] == "automatically_supported"
        for group in evaluations
        for row in group["evaluations"]
    )
    supported_cases = {
        group["sample_id"]
        for group in evaluations
        if any(row["after"] == "automatically_supported" for row in group["evaluations"])
    }
    costs = numeric([(item.get("cost_usage") or {}).get("model_cost_usd") for item in investigations])
    durations = numeric([(item.get("cost_usage") or {}).get("wall_clock_seconds") for item in investigations])
    tool_requests = numeric([(item.get("cost_usage") or {}).get("tool_requests") for item in investigations])
    http_requests = numeric([(item.get("cost_usage") or {}).get("http_requests") for item in investigations])
    conflicts = statuses.get("conflicting_evidence_found", 0)
    return {
        "investigations_attempted": attempts,
        "unique_cases_investigated": len({item["sample_id"] for item in investigations}),
        "candidate_evidence_investigations": evidence_attempts,
        "evidence_retrieval_yield": evidence_attempts / attempts if attempts else None,
        "experimental_deterministic_rule_matches": supported,
        "experimental_cases_with_rule_match": len(supported_cases),
        "experimental_deterministic_resolution_yield": supported / attempts if attempts else None,
        "release_deterministic_resolution_yield": 0.0 if attempts else None,
        "release_unresolved_before": len({item["sample_id"] for item in investigations}),
        "release_unresolved_after": len({item["sample_id"] for item in investigations}),
        "human_review_reduction": 0.0 if attempts else None,
        "evidence_precision_from_human_audit": None,
        "false_positive_association_rate_from_human_audit": None,
        "ambiguity_rate": statuses.get("ambiguous_identity", 0) / attempts if attempts else None,
        "retrieval_failure_rate": (statuses.get("retrieval_error", 0) + statuses.get("source_unavailable", 0)) / attempts if attempts else None,
        "conflict_discovery_rate": conflicts / attempts if attempts else None,
        "status_counts": dict(sorted(statuses.items())),
        "source_distribution": dict(sorted(sources.items())),
        "cost": {
            "total_model_cost_usd": sum(costs) if len(costs) == attempts else None,
            "cost_per_investigation": sum(costs) / attempts if len(costs) == attempts and attempts else None,
            "cost_per_evidence_found": sum(costs) / evidence_attempts if len(costs) == attempts and evidence_attempts else None,
            "cost_per_ambiguity_resolved": None,
            "average_duration_seconds": sum(durations) / len(durations) if durations else None,
            "tool_requests_recorded": int(sum(tool_requests)),
            "http_requests_recorded": int(sum(http_requests)) if http_requests else None,
            "token_usage_status": "unavailable" if any((item.get("cost_usage") or {}).get("input_tokens") == "unavailable" for item in investigations) else "recorded",
        },
    }


def repeatability(investigations: list[dict[str, Any]], evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evaluation_by_id = {row["investigation_id"]: row["evaluations"] for row in evaluations}
    for item in investigations:
        groups[item["sample_id"]].append(item)
    rows = []
    for sample_id, repeats in sorted(groups.items()):
        if len(repeats) < 2:
            continue
        evidence_sets = []
        source_sets = []
        classifications = []
        for item in sorted(repeats, key=lambda row: str(row.get("repeat_id", ""))):
            evidence_sets.append(sorted(str(value.get("evidence_fingerprint") or evidence_hash(value)) for value in item.get("candidate_evidence", [])))
            source_sets.append(sorted(str(value.get("source_reference") or "") for value in item.get("candidate_evidence", [])))
            classifications.append(sorted(
                (value["claim"], value["after"], value.get("rule_id"))
                for value in evaluation_by_id.get(item["investigation_id"], [])
            ))
        rows.append({
            "sample_id": sample_id,
            "repeat_count": len(repeats),
            "same_evidence_discovered": all(value == evidence_sets[0] for value in evidence_sets[1:]),
            "same_source_selected": all(value == source_sets[0] for value in source_sets[1:]),
            "same_final_deterministic_classification": all(value == classifications[0] for value in classifications[1:]),
            "evidence_sets": evidence_sets,
        })
    return {
        "repeated_cases": len(rows),
        "cases": rows,
        "same_evidence_rate": sum(row["same_evidence_discovered"] for row in rows) / len(rows) if rows else None,
        "same_source_rate": sum(row["same_source_selected"] for row in rows) / len(rows) if rows else None,
        "same_deterministic_classification_rate": sum(row["same_final_deterministic_classification"] for row in rows) / len(rows) if rows else None,
    }


def human_template(path: Path, investigations: list[dict[str, Any]]) -> None:
    fields = [
        "evaluation_id", "sample_id", "investigation_id", "evidence_id", "evidence_path", "evidence_sha256",
        "evidence_relevant", "correct_record", "source_authoritative", "extraction_accurate",
        "agent_overstated", "contradiction_ignored", "reviewer_code", "reviewed_at_utc", "notes",
    ]
    candidates = []
    for item in investigations:
        for candidate in item.get("candidate_evidence", []):
            candidates.append((canonical_hash([item["sample_id"], evidence_hash(candidate)]), item, candidate))
    rows = []
    for index, (_, item, candidate) in enumerate(
        sorted(candidates, key=lambda value: (value[0], value[1]["investigation_id"]))[
            : min(8, len(candidates))
        ],
        start=1,
    ):
        row = {field: "" for field in fields}
        row.update({
            "evaluation_id": f"agent-eval-{index:03d}",
            "sample_id": item["sample_id"],
            "investigation_id": item["investigation_id"],
            "evidence_id": candidate.get("evidence_id") or candidate.get("candidate_evidence_id"),
            "evidence_path": evidence_path(candidate),
            "evidence_sha256": evidence_hash(candidate),
        })
        rows.append(row)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def display_rate(value: Any) -> str:
    return "unavailable" if value is None else f"{float(value):.1%}"


def render_report(run: dict[str, Any]) -> str:
    metrics = run["metrics"]
    repeat = run["repeatability"]
    model_rows = "\n".join(
        f"- {model['provider']} {model['product']} `{model['model_identifier']}`; reasoning `{model['reasoning_effort']}`; snapshot `{model['model_snapshot']}`"
        for model in run["actual_models"]
    )
    prompts = "\n".join(
        f"- `{item['path']}` ({item['version']}): `{item['prompt_hash']}`"
        for item in run["prompt_provenance"]
    )
    sources = "\n".join(f"- `{source}`: {count}" for source, count in metrics["source_distribution"].items()) or "- No candidate evidence source was accepted."
    cases = ", ".join(f"`{sample_id}`" for sample_id in run["benchmark_case_ids"])
    return f"""# Agentic validation report

## Architecture

This report evaluates a separate evidence-retrieval assistant. Frozen sample -> deterministic baseline -> bounded agent investigation -> archived candidate evidence -> deterministic experimental rule evaluation -> human review. Agent output never writes dataset validation or human-review fields.

## Model

{model_rows}

Unknown runtime fields are recorded as `unavailable`; requested configuration is not treated as proof of use.

## Prompt provenance

{prompts}

## Evaluation dataset

Benchmark `{run['benchmark_id']}` contains {run['benchmark_case_count']} reproducibly selected cases from the unchanged 150-row frozen core sample. {metrics['unique_cases_investigated']} unique cases were investigated: {cases}. This is an agent-system study, not a replacement sample and not a dataset-accuracy estimate.

## Sources

{sources}

## Results

- Investigations attempted: {metrics['investigations_attempted']}
- Investigations with archived candidate evidence: {metrics['candidate_evidence_investigations']}
- Evidence retrieval yield: {display_rate(metrics['evidence_retrieval_yield'])}
- Experimental deterministic rule matches: {metrics['experimental_deterministic_rule_matches']}
- Unique cases with an experimental rule match: {metrics['experimental_cases_with_rule_match']}
- Release-authorized deterministic resolutions: 0
- Release unresolved cases, before / after: {metrics['release_unresolved_before']} / {metrics['release_unresolved_after']}
- Human-review reduction: 0 (experimental rules cannot write release results)
- Ambiguity rate: {display_rate(metrics['ambiguity_rate'])}
- Retrieval failure rate: {display_rate(metrics['retrieval_failure_rate'])}
- Conflict discovery rate: {display_rate(metrics['conflict_discovery_rate'])}

These are agent-performance measures, not TDR validity estimates.

## Errors

Statuses: `{json.dumps(metrics['status_counts'], sort_keys=True)}`. False-association precision remains unmeasured until the blinded human evaluation template is completed. The adversarial suite checks wrong identifiers, near matches, conflicting sources, irrelevant records, missing primary evidence, and prompt injection, but passing fixtures is not a substitute for human precision measurement. No automated agreement is counted as independent review.

## Costs

Model token counts and model cost were not exposed by the agent runtime and remain unavailable. Recorded tool requests: {metrics['cost']['tool_requests_recorded']}; HTTP requests: {metrics['cost']['http_requests_recorded'] if metrics['cost']['http_requests_recorded'] is not None else 'unavailable'}. Average duration: {metrics['cost']['average_duration_seconds'] if metrics['cost']['average_duration_seconds'] is not None else 'unavailable'}.

## Repeatability

Repeated cases: {repeat['repeated_cases']}. Same evidence rate: {display_rate(repeat['same_evidence_rate'])}; same source rate: {display_rate(repeat['same_source_rate'])}; same deterministic-classification rate: {display_rate(repeat['same_deterministic_classification_rate'])}.

## Human audit

The run includes a blinded `agent_evidence_retrieval_evaluation` template. It evaluates relevance, identity, source authority, extraction, overstatement, and ignored contradictions separately from dataset validation. No human agent audit was completed in this run, so evidence precision and false-positive association rate are not yet estimable.

## Protocol deviation

On 2026-09-02, evidence retrieval was prematurely expanded to the remaining 132 frozen-sample cases before the benchmark human audit. Runs D/E/F are excluded exploratory runs. Their outputs were removed from the active experimental workspace before project-owner case-level review and were not used to tune prompts, rules, protocol, or human decisions; the hashes-only audit record is `reproducibility/deviations/2026-09-02-premature-agent-expansion.json`.

## Limitations

Agentic discovery is nondeterministic. Live sources and search indexes change; model backends can change; official portals may be unavailable; absence of evidence is not evidence of absence. "Candidate evidence" means the agent archived an association for evaluation; human review has not established that every association is correct or that every underlying fact was newly discovered. Narrative interpretation remains human-review work. Experimental rule matches have `release_write_enabled=false`. The source attachment for this phase ended mid-bullet at `* Live`; no missing instruction text was reconstructed.

## Scaling recommendation

Do **not** scale to all 150 frozen cases yet. Human-audited evidence precision is unavailable, the rule registry remains experimental, and no agent result is authorized to modify release validation. Complete the blinded agent-evidence audit, review false associations and contradictions, and explicitly approve any release rule before reconsidering scale-up.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", choices=("core",), required=True)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--responses-dir", type=Path, default=RESPONSES)
    parser.add_argument("--allow-recorded-live", action="store_true")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")

    if DEFAULT_FREEZE.exists():
        verify_freeze(DEFAULT_FREEZE)

    sample_before = sha256_file(FROZEN_SAMPLE)
    benchmark = load_json(BENCHMARK)
    expected_sample_hash = benchmark["input"]["sha256"]
    if sample_before != expected_sample_hash:
        raise RuntimeError("frozen sample hash differs from benchmark input")
    rules = load_json(RULES)
    config = load_json(CONFIG)
    if rules.get("may_modify_dataset_validation") is not False or rules.get("may_modify_human_review") is not False:
        raise RuntimeError("agent rule registry has unsafe write authority")
    verify_prompt_hashes()
    prompts = prompt_manifest()
    cases = {case["investigation_request"]["sample_id"]: case for case in benchmark["cases"]}

    response_paths = sorted(args.responses_dir.glob("*.json"))
    if not response_paths:
        raise FileNotFoundError(f"no recorded agent responses in {args.responses_dir}")
    investigations: list[dict[str, Any]] = []
    models: dict[str, dict[str, Any]] = {}
    evidence_index: dict[str, dict[str, Any]] = {}
    evaluations: list[dict[str, Any]] = []
    response_manifest = []
    for path in response_paths:
        response = load_json(path)
        model = response.get("actual_model") or response.get("model_metadata") or {}
        model = normalized_model_metadata(model)
        models[canonical_hash(model)] = model
        validate_prompt_provenance(response.get("prompt_provenance"), prompts)
        response_manifest.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)})
        for investigation in response.get("investigations", []):
            assert_safe_agent_output(investigation)
            if investigation.get("status") not in ALLOWED_INVESTIGATION_STATUSES:
                raise ValueError("invalid investigation status")
            validate_budget(investigation, config)
            sample_id = str(investigation.get("sample_id") or "")
            if sample_id not in cases:
                raise ValueError(f"response references a non-benchmark sample: {sample_id}")
            request = cases[sample_id]["investigation_request"]
            allowed_claims = {item["claim_id"] for item in request["unresolved_claims"]}
            if not set(claims_for(investigation)).issubset(allowed_claims):
                raise ValueError(f"agent investigated a resolved or out-of-scope claim: {sample_id}")
            if investigation.get("requires_human_review") is not True:
                raise ValueError("benchmark agent results must remain queued for human review")
            rows = []
            for candidate in investigation.get("candidate_evidence", []):
                evidence, observed_hash, content_hash = validate_evidence(candidate, allow_live=args.allow_recorded_live)
                candidate = dict(candidate)
                candidate["evidence_file_sha256"] = observed_hash
                candidate["source_content_sha256"] = content_hash
                candidate["source_reference"] = _source_url(evidence, candidate) or str(evidence.get("source") or "")
                candidate["evidence_fingerprint"] = canonical_hash({
                    "source_reference": candidate["source_reference"],
                    "administrative_record_id": evidence.get("administrative_record_id"),
                    "observed_fields": (
                        evidence.get("observed_fields")
                        or evidence.get("extracted_explicit_fields")
                        or evidence.get("extracted_fields")
                    ),
                    "source_state": evidence.get("source_state"),
                })
                evidence_key = canonical_hash([
                    observed_hash,
                    candidate.get("evidence_id") or candidate.get("candidate_evidence_id"),
                ])
                evidence_index[evidence_key] = evidence
                rows.append((candidate, evidence, observed_hash))
            item = dict(investigation)
            item["candidate_evidence"] = [row[0] for row in rows]
            item["recorded_response_path"] = path.relative_to(ROOT).as_posix()
            investigations.append(item)
            evaluations.append({
                "investigation_id": item["investigation_id"],
                "sample_id": sample_id,
                "repeat_id": item.get("repeat_id"),
                "evaluations": deterministic_evaluation(item, request, rows, rules),
            })

    counts = Counter(item["sample_id"] for item in investigations)
    if any(count > args.repeat for count in counts.values()):
        raise ValueError("recorded investigations exceed --repeat")
    missing_cases = sorted(set(cases) - set(counts))
    if missing_cases:
        raise RuntimeError("benchmark was not fully investigated: " + ", ".join(missing_cases))
    if args.repeat > 1 and sum(count == args.repeat for count in counts.values()) < 2:
        raise RuntimeError("repeatability design requires two cases investigated at the requested repeat count")
    if sha256_file(FROZEN_SAMPLE) != sample_before:
        raise RuntimeError("frozen sample changed during agentic validation")

    metrics = aggregate(investigations, evaluations, evidence_index)
    repeat = repeatability(investigations, evaluations)
    started = now_utc()
    run_id = started.replace("-", "").replace(":", "").replace("T", "T").replace("Z", "Z")
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    human_template(run_dir / "agent_evidence_retrieval_evaluation.csv", investigations)
    run = {
        "format_version": "1.0.0",
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "created_at_utc": started,
        "study": args.study,
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_version": benchmark["benchmark_version"],
        "benchmark_sha256": sha256_file(BENCHMARK),
        "benchmark_case_count": len(cases),
        "benchmark_case_ids": sorted(cases),
        "frozen_sample_sha256_before": sample_before,
        "frozen_sample_sha256_after": sha256_file(FROZEN_SAMPLE),
        "frozen_sample_unchanged": True,
        "actual_models": [models[key] for key in sorted(models)],
        "prompt_provenance": prompts,
        "rule_registry": {
            "path": RULES.relative_to(ROOT).as_posix(),
            "version": rules["rule_set_version"],
            "sha256": sha256_file(RULES),
            "release_write_enabled": False,
        },
        "recorded_responses": response_manifest,
        "network": {
            "live_evidence_ingested": any(
                source_tier({}, value) == SourceTier.LIVE_PRIMARY.value for value in evidence_index.values()
            ),
            "runner_http_requests": 0,
            "note": "The runner made no network request; agent action logs preserve recorded retrieval provenance.",
        },
        "metrics": metrics,
        "repeatability": repeat,
        "investigations": investigations,
        "deterministic_re_evaluations": evaluations,
        "human_audit_completed": False,
        "dataset_validation_changed": False,
        "human_decisions_changed": False,
        "scale_to_full_sample_recommended": False,
        "limitations": [
            "Agent discovery and mutable live sources are not computationally deterministic.",
            "Token counts and model cost are unavailable unless exposed in recorded agent metadata.",
            "Evidence precision and false-association rates require blinded human audit.",
            "Experimental rule matches cannot write release validation results.",
        ],
    }
    write_json(run_dir / "run_manifest.json", run)
    write_json(run_dir / "agent_performance.json", metrics)
    write_json(run_dir / "repeatability.json", repeat)
    write_json(run_dir / "deterministic_re_evaluation.json", evaluations)
    REPORT.write_text(render_report(run), encoding="utf-8")
    print(json.dumps({
        "run_id": run_id,
        "investigations": len(investigations),
        "unique_cases": metrics["unique_cases_investigated"],
        "evidence_retrieval_yield": metrics["evidence_retrieval_yield"],
        "repeatability_cases": repeat["repeated_cases"],
        "frozen_sample_unchanged": True,
        "scale_to_full_sample_recommended": False,
        "run_manifest": (run_dir / "run_manifest.json").relative_to(ROOT).as_posix(),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
