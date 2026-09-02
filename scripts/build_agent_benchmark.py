#!/usr/bin/env python3
"""Build the bounded Phase 35 agent-evidence benchmark.

This script only selects cases and creates structured investigation requests.
It does not retrieve evidence, run an agent, or make validation judgments.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed" / "manual_validation_sample.csv"
OUTPUT = ROOT / "data" / "agentic_validation" / "benchmark_v1.json"

BENCHMARK_VERSION = "1.0.0"
SELECTION_ALGORITHM = "sha256-category-rank-without-replacement"
SELECTION_ALGORITHM_VERSION = "1.0.0"
DEFAULT_SEED = 20260902

# The quotas are deliberately small. Categories are evaluated in this order and
# selection is without replacement, so each case has one auditable primary
# stratum even when it carries several investigation signals.
CATEGORY_QUOTAS: tuple[tuple[str, int], ...] = (
    ("potential_conflicting_evidence", 2),
    ("multiple_candidate_records", 3),
    ("missing_source_evidence", 3),
    ("ambiguous_spatial_identity", 3),
    ("inspection_related", 3),
    ("easy_identifier_lookup", 4),
)

PLACEHOLDER_IDENTIFIERS = {"", "0", "0000000", "unknown", "n/a", "na"}
REQUIRED_COLUMNS = {
    "audit_sample_id",
    "sample_phase",
    "sampling_stratum",
    "activity_id",
    "source_record_id",
    "source_memberships",
    "activity_class",
    "activity_stage",
    "status",
    "physical_work_started_dataset",
    "realization_evidence_grade",
    "parcel_match_confidence",
    "match_methods",
    "match_distances_m",
    "address",
    "record_type",
    "project_name",
    "description",
    "source_url",
    "source_identity_result",
    "activity_classification_result",
    "cross_source_linkage_result",
    "status_interpretation_result",
    "building_footprint_match_result",
    "manual_evidence_confirmed",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_sample(path: Path) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    csv.field_size_limit(sys.maxsize)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS.difference(columns))
        if missing:
            raise ValueError(f"Frozen sample is missing required columns: {', '.join(missing)}")
        rows = list(reader)
    sample_ids = [row["audit_sample_id"] for row in rows]
    if not rows:
        raise ValueError("Frozen sample contains no rows")
    if any(not value for value in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("Frozen sample must contain unique, nonblank audit_sample_id values")
    return rows, columns


def source_types(row: dict[str, str]) -> list[str]:
    return sorted({value.strip() for value in row["source_memberships"].split(";") if value.strip()})


def usable_identifier(value: str) -> bool:
    return value.strip().lower() not in PLACEHOLDER_IDENTIFIERS


def duplicate_identifiers(rows: list[dict[str, str]]) -> set[str]:
    counts = Counter(
        row["source_record_id"].strip().lower()
        for row in rows
        if usable_identifier(row["source_record_id"])
    )
    return {value for value, count in counts.items() if count > 1}


def category_predicates(
    repeated_identifiers: set[str],
) -> dict[str, Callable[[dict[str, str]], bool]]:
    def potential_conflict(row: dict[str, str]) -> bool:
        return (
            row["physical_work_started_dataset"].strip().lower() == "yes"
            and row["status"].strip().lower() in {"cancelled", "canceled", "inactive"}
        ) or row["realization_evidence_grade"].strip().upper() == "X"

    def multiple_candidates(row: dict[str, str]) -> bool:
        return row["source_record_id"].strip().lower() in repeated_identifiers

    def missing_evidence(row: dict[str, str]) -> bool:
        return not row["source_url"].strip() or not usable_identifier(row["source_record_id"])

    def ambiguous_spatial(row: dict[str, str]) -> bool:
        return row["parcel_match_confidence"].strip().lower() == "medium" or (
            row["match_distances_m"].strip()
            and row["match_methods"].strip().lower() != "point_in_building_footprint"
        )

    def inspection(row: dict[str, str]) -> bool:
        return "construction_inspections" in source_types(row)

    def easy_identifier(row: dict[str, str]) -> bool:
        return (
            usable_identifier(row["source_record_id"])
            and bool(row["source_url"].strip())
            and not multiple_candidates(row)
            and not ambiguous_spatial(row)
        )

    return {
        "potential_conflicting_evidence": potential_conflict,
        "multiple_candidate_records": multiple_candidates,
        "missing_source_evidence": missing_evidence,
        "ambiguous_spatial_identity": ambiguous_spatial,
        "inspection_related": inspection,
        "easy_identifier_lookup": easy_identifier,
    }


def selection_hash(seed: int, category: str, sample_id: str) -> str:
    token = "|".join(
        (
            str(seed),
            SELECTION_ALGORITHM_VERSION,
            category,
            sample_id,
        )
    )
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def unresolved_claims(row: dict[str, str]) -> list[dict[str, str]]:
    mappings = (
        ("source_identity", "source_identity_result"),
        ("activity_classification", "activity_classification_result"),
        ("status_interpretation", "status_interpretation_result"),
    )
    claims = [
        {
            "claim_id": claim_id,
            "basis_field": result_field,
            "basis_value": row[result_field],
            "reason": "frozen manual-review result is blank",
        }
        for claim_id, result_field in mappings
        if not row[result_field].strip()
    ]
    if len(source_types(row)) > 1 and not row["cross_source_linkage_result"].strip():
        claims.append(
            {
                "claim_id": "cross_source_linkage",
                "basis_field": "cross_source_linkage_result",
                "basis_value": row["cross_source_linkage_result"],
                "reason": "multiple source memberships are explicit and the review result is blank",
            }
        )
    if (
        row["parcel_match_confidence"].strip() or row["match_methods"].strip()
    ) and not row["building_footprint_match_result"].strip():
        claims.append(
            {
                "claim_id": "building_footprint_match",
                "basis_field": "building_footprint_match_result",
                "basis_value": row["building_footprint_match_result"],
                "reason": "spatial-match context is explicit and the review result is blank",
            }
        )
    if (
        row["physical_work_started_dataset"].strip().lower() == "unknown"
        and not row["manual_evidence_confirmed"].strip()
    ):
        claims.append(
            {
                "claim_id": "physical_work_started",
                "basis_field": "physical_work_started_dataset",
                "basis_value": row["physical_work_started_dataset"],
                "reason": "frozen dataset value is explicitly unknown and manual evidence is blank",
            }
        )
    return claims


def known_evidence(row: dict[str, str]) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = [
        {
            "evidence_type": "frozen_dataset_context",
            "evidentiary_status": "unreviewed_context_not_ground_truth",
            "fields": {
                "source_record_id": row["source_record_id"],
                "source_memberships": row["source_memberships"],
                "source_url": row["source_url"],
                "activity_stage": row["activity_stage"],
                "status": row["status"],
                "physical_work_started_dataset": row["physical_work_started_dataset"],
                "realization_evidence_grade": row["realization_evidence_grade"],
            },
        }
    ]
    if row["parcel_match_confidence"].strip() or row["match_methods"].strip():
        evidence.append(
            {
                "evidence_type": "frozen_spatial_match_context",
                "evidentiary_status": "unreviewed_context_not_ground_truth",
                "fields": {
                    "parcel_match_confidence": row["parcel_match_confidence"],
                    "match_methods": row["match_methods"],
                    "match_distances_m": row["match_distances_m"],
                },
            }
        )
    return evidence


def build_case(
    row: dict[str, str],
    *,
    primary_category: str,
    matched_categories: list[str],
    rank_hash: str,
) -> dict[str, object]:
    sample_id = row["audit_sample_id"]
    return {
        "benchmark_case_id": f"agent-benchmark-v1-{sample_id}",
        "selection": {
            "primary_category": primary_category,
            "matched_categories": matched_categories,
            "sha256_rank": rank_hash,
        },
        "source_types": source_types(row),
        "investigation_request": {
            "schema_version": "1.0.0",
            "study": "core",
            "sample_id": sample_id,
            "activity_id": row["activity_id"],
            "record_number": row["source_record_id"],
            "record_type": row["record_type"],
            "address": row["address"],
            "project_name": row["project_name"],
            "description": row["description"],
            "known_dates": {},
            "known_evidence": known_evidence(row),
            "unresolved_claims": unresolved_claims(row),
            "dataset_context": {
                "sample_phase": row["sample_phase"],
                "sampling_stratum": row["sampling_stratum"],
                "activity_class": row["activity_class"],
                "latitude": row.get("latitude", ""),
                "longitude": row.get("longitude", ""),
            },
        },
        "comparison_baseline": {
            "status": "not_run",
            "deterministic_only": "not_run",
            "deterministic_plus_agentic": "not_run",
            "evidence_availability": "not_assessed",
            "unresolved_case": "not_assessed",
            "false_association": "not_assessed",
            "conflicts_detected": "not_assessed",
            "human_review_required": "not_assessed",
            "execution_time_seconds": None,
            "cost": None,
        },
    }


def build_benchmark(
    rows: list[dict[str, str]],
    *,
    input_path: str,
    input_sha256: str,
    seed: int = DEFAULT_SEED,
) -> dict[str, object]:
    repeated = duplicate_identifiers(rows)
    predicates = category_predicates(repeated)
    selected_ids: set[str] = set()
    selections: list[tuple[dict[str, str], str, str]] = []

    for category, quota in CATEGORY_QUOTAS:
        ranked = sorted(
            (
                (selection_hash(seed, category, row["audit_sample_id"]), row["audit_sample_id"], row)
                for row in rows
                if row["audit_sample_id"] not in selected_ids and predicates[category](row)
            ),
            key=lambda item: (item[0], item[1]),
        )
        if len(ranked) < quota:
            raise ValueError(
                f"Category {category!r} has {len(ranked)} unselected candidates; quota is {quota}"
            )
        for rank_hash, sample_id, row in ranked[:quota]:
            selected_ids.add(sample_id)
            selections.append((row, category, rank_hash))

    category_order = {category: index for index, (category, _) in enumerate(CATEGORY_QUOTAS)}
    cases = [
        build_case(
            row,
            primary_category=category,
            matched_categories=sorted(
                (name for name, predicate in predicates.items() if predicate(row)),
                key=lambda name: category_order[name],
            ),
            rank_hash=rank_hash,
        )
        for row, category, rank_hash in selections
    ]

    primary_counts = Counter(case["selection"]["primary_category"] for case in cases)  # type: ignore[index]
    source_counts = Counter(
        source_type for case in cases for source_type in case["source_types"]  # type: ignore[union-attr]
    )
    phase_counts = Counter(
        case["investigation_request"]["dataset_context"]["sample_phase"]  # type: ignore[index]
        for case in cases
    )
    stratum_counts = Counter(
        case["investigation_request"]["dataset_context"]["sampling_stratum"]  # type: ignore[index]
        for case in cases
    )
    return {
        "benchmark_id": "tdr-agent-evidence-benchmark-v1",
        "benchmark_version": BENCHMARK_VERSION,
        "purpose": "evaluation subset for deterministic-only versus deterministic-plus-agentic evidence retrieval",
        "scope_boundaries": [
            "This is an evaluation subset, not a replacement probability sample.",
            "No agent investigation or external evidence retrieval was run by this builder.",
            "Selection signals are not validation conclusions or ground-truth labels.",
            "Agent results may not bypass deterministic re-evaluation or human review.",
        ],
        "input": {
            "path": input_path,
            "sha256": input_sha256,
            "row_count": len(rows),
            "frozen_sample_modified": False,
        },
        "selection_protocol": {
            "seed": seed,
            "algorithm": SELECTION_ALGORITHM,
            "algorithm_version": SELECTION_ALGORITHM_VERSION,
            "ranking_token": "seed|algorithm_version|category|audit_sample_id",
            "without_replacement": True,
            "category_order": [category for category, _ in CATEGORY_QUOTAS],
            "category_quotas": {category: quota for category, quota in CATEGORY_QUOTAS},
            "category_definitions": {
                "potential_conflicting_evidence": (
                    "a conflict-detection probe: realization_evidence_grade is X, or "
                    "physical_work_started_dataset is yes while status is cancelled/canceled/inactive; "
                    "the category does not assert that conflicting evidence has been found"
                ),
                "multiple_candidate_records": (
                    "a non-placeholder source_record_id occurs in more than one frozen sample row; "
                    "this is a candidate-review signal, not a finding that records should be merged"
                ),
                "missing_source_evidence": (
                    "source_url is blank or source_record_id is blank/a documented placeholder"
                ),
                "ambiguous_spatial_identity": (
                    "parcel_match_confidence is medium or a non-footprint match distance is present"
                ),
                "inspection_related": (
                    "source_memberships explicitly includes construction_inspections"
                ),
                "easy_identifier_lookup": (
                    "a non-placeholder source_record_id and source_url are present, without a repeated "
                    "identifier or ambiguous spatial signal"
                ),
            },
            "target_size": sum(quota for _, quota in CATEGORY_QUOTAS),
        },
        "counts": {
            "selected_cases": len(cases),
            "primary_categories": dict(sorted(primary_counts.items())),
            "source_types": dict(sorted(source_counts.items())),
            "sample_phases": dict(sorted(phase_counts.items())),
            "original_sampling_strata": dict(sorted(stratum_counts.items())),
        },
        "cases": cases,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if output is absent or differs instead of writing it",
    )
    args = parser.parse_args()

    before_sha = sha256_file(args.input)
    rows, _ = read_sample(args.input)
    try:
        relative_input = args.input.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        relative_input = str(args.input.resolve())
    payload = build_benchmark(
        rows,
        input_path=relative_input,
        input_sha256=before_sha,
        seed=args.seed,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if sha256_file(args.input) != before_sha:
        raise RuntimeError("Frozen input changed while building the benchmark")

    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Agent benchmark is missing or out of date")
    else:
        write_json(args.output, payload)

    print(
        json.dumps(
            {
                "benchmark_id": payload["benchmark_id"],
                "selected_cases": payload["counts"]["selected_cases"],  # type: ignore[index]
                "input_sha256": before_sha,
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
