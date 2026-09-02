#!/usr/bin/env python3
"""Create the frozen GIS-Accela linkage and deduplication audit sample."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

try:
    from . import validation_sampling as sampling
except ImportError:
    import validation_sampling as sampling


INPUT = sampling.ROOT / "data" / "integrated" / "accela_integration_audit.csv"
OUTPUT = sampling.ROOT / "data" / "processed" / "manual_validation_integration_links.csv"
SECOND_OUTPUT = sampling.ROOT / "data" / "processed" / "manual_validation_integration_links_second_review.csv"
STUDY_ID = "gis_accela_linkage"
PROTOCOL_VERSION = "1.0.0"
DEFAULT_SEED = 20260913
DEFAULT_TARGET = 100

CONTEXT_FIELDS = (
    "accela_record_id", "record_number", "source_module", "gis_activity_id",
    "integrated_activity_id", "automated_linkage_decision", "linkage_rule_used",
    "candidate_count", "duplicate_key", "automated_review_required",
)
REVIEW_FIELDS = (
    "review_status", "human_linkage_assessment", "duplicate_assessment",
    "false_positive_link", "false_negative_link", "ambiguous", "linkage_outcome",
    "evidence_reference", "review_notes", "reviewer_code", "reviewed_at",
)


def linkage_stratum(row: dict[str, str]) -> str:
    disposition = row.get("disposition", "").lower()
    if row.get("review_required", "").lower() == "true" or "ambiguous" in disposition:
        return "ambiguous_or_multi_candidate"
    if "deduplic" in disposition or "duplicate" in disposition:
        return "duplicate_suppression"
    if disposition == "merged_existing_activity":
        return "matched_gis_accela"
    return "retained_unmatched_accela"


def candidates(audit: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for item in audit:
        stratum = linkage_stratum(item)
        row = {
            "sampling_stratum": stratum,
            "accela_record_id": item.get("accela_record_id", ""),
            "record_number": item.get("record_number", ""),
            "source_module": item.get("source_module", ""),
            "gis_activity_id": item.get("matched_activity_id", ""),
            "integrated_activity_id": item.get("integrated_activity_id", ""),
            "automated_linkage_decision": item.get("disposition", ""),
            "linkage_rule_used": item.get("match_method", ""),
            "candidate_count": "1" if item.get("matched_activity_id") else "0",
            "duplicate_key": item.get("duplicate_key", ""),
            "automated_review_required": item.get("review_required", ""),
        }
        result.append(row)
    return result


def quotas_for(universe: list[dict[str, str]], target: int) -> dict[str, int] | None:
    populations = Counter(row["sampling_stratum"] for row in universe)
    if set(populations) == {"matched_gis_accela", "retained_unmatched_accela"}:
        matched = min(populations["matched_gis_accela"], target // 2)
        return {
            "matched_gis_accela": matched,
            "retained_unmatched_accela": target - matched,
        }
    return None


def build(
    audit: list[dict[str, str]], *, target: int = DEFAULT_TARGET, seed: int = DEFAULT_SEED
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    universe = candidates(audit)
    fixed_quotas = quotas_for(universe, target)
    primary = sampling.build_primary_rows(
        universe,
        identity_field="accela_record_id",
        context_fields=CONTEXT_FIELDS,
        review_fields=REVIEW_FIELDS,
        target=target,
        seed=seed,
        study_id=STUDY_ID,
        protocol_version=PROTOCOL_VERSION,
        generated_from="data/integrated/accela_integration_audit.csv",
        sample_prefix="gil",
        minimum_per_stratum=max(1, min(10, target // max(1, len(set(row['sampling_stratum'] for row in universe))))),
        fixed_quotas=fixed_quotas,
    )
    second = sampling.build_second_review_rows(
        primary,
        context_fields=CONTEXT_FIELDS,
        target=max(1, round(target * 0.25)),
        seed=seed,
        study_id=STUDY_ID,
    )
    return primary, second


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--second-output", type=Path, default=SECOND_OUTPUT)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    primary, second = build(sampling.read_csv(args.input), target=args.target, seed=args.seed)
    sampling.write_frozen_study(
        primary_path=args.output,
        second_path=args.second_output,
        primary_rows=primary,
        second_rows=second,
        context_fields=CONTEXT_FIELDS,
        review_fields=REVIEW_FIELDS,
        force=args.force,
    )
    print(json.dumps({
        "study_id": STUDY_ID,
        "sample_rows": len(primary),
        "second_review_rows": len(second),
        "strata": dict(Counter(row["sampling_stratum"] for row in primary)),
        "sampling_universe_rows": primary[0]["sampling_universe_size"],
        "sampling_universe_sha256": primary[0]["sampling_universe_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
