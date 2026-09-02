#!/usr/bin/env python3
"""Create the frozen Accela normalization and semantic-validity sample."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

try:
    from . import validation_sampling as sampling
    from .build_accela_source_fidelity_sample import observation_type, time_period
except ImportError:
    import validation_sampling as sampling
    from build_accela_source_fidelity_sample import observation_type, time_period


INPUT = sampling.ROOT / "data" / "processed" / "accela_records.csv"
SOURCE_FIDELITY_SAMPLE = sampling.ROOT / "data" / "processed" / "manual_validation_accela_source_fidelity.csv"
OUTPUT = sampling.ROOT / "data" / "processed" / "manual_validation_accela_normalization.csv"
SECOND_OUTPUT = sampling.ROOT / "data" / "processed" / "manual_validation_accela_normalization_second_review.csv"
STUDY_ID = "accela_normalization"
PROTOCOL_VERSION = "1.0.0"
DEFAULT_SEED = 20260912
DEFAULT_TARGET = 125

CONTEXT_FIELDS = (
    "record_id", "record_number", "source_module", "record_type", "record_status",
    "opened_date", "filed_date", "issued_date", "expiration_date", "completed_date",
    "closed_date", "updated_date", "event_date", "event_date_type", "historical_reconstruction",
    "temporal_evidence", "snapshot_date", "parent_record_number", "source_url",
)
REVIEW_FIELDS = (
    "review_status", "event_type_correct", "event_date_source_field_correct",
    "event_date_value_correct", "status_normalization_correct", "retrospective_flag_correct",
    "planned_date_flag_correct", "activity_mapping_correct", "record_identity_correct",
    "normalization_outcome", "review_notes", "reviewer_code", "reviewed_at",
)


def candidates(
    records: list[dict[str, str]], excluded_record_ids: set[str] | None = None
) -> list[dict[str, str]]:
    excluded_record_ids = excluded_record_ids or set()
    eligible = [row for row in records if row.get("record_id") not in excluded_record_ids]
    type_counts = Counter((row.get("source_module", ""), row.get("record_type", "")) for row in eligible)
    result = []
    for record in eligible:
        row = {field: record.get(field, "") for field in CONTEXT_FIELDS}
        rarity = "relatively_rare_type" if type_counts[(row["source_module"], row["record_type"])] < 500 else "common_type"
        row["sampling_stratum"] = "|".join((
            row["source_module"] or "unknown_module",
            observation_type(record),
            time_period(record),
            rarity,
        ))
        result.append(row)
    return result


def build(
    records: list[dict[str, str]],
    *,
    excluded_record_ids: set[str] | None = None,
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    universe = candidates(records, excluded_record_ids)
    primary = sampling.build_primary_rows(
        universe,
        identity_field="record_id",
        context_fields=CONTEXT_FIELDS,
        review_fields=REVIEW_FIELDS,
        target=target,
        seed=seed,
        study_id=STUDY_ID,
        protocol_version=PROTOCOL_VERSION,
        generated_from="data/processed/accela_records.csv; excludes source-fidelity assignments",
        sample_prefix="anm",
        minimum_per_stratum=2,
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
    parser.add_argument("--source-fidelity-sample", type=Path, default=SOURCE_FIDELITY_SAMPLE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--second-output", type=Path, default=SECOND_OUTPUT)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    excluded = set()
    if args.source_fidelity_sample.exists():
        excluded = {row["record_id"] for row in sampling.read_csv(args.source_fidelity_sample)}
    primary, second = build(
        sampling.read_csv(args.input), excluded_record_ids=excluded, target=args.target, seed=args.seed
    )
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
        "excluded_source_fidelity_assignments": len(excluded),
        "sampling_universe_rows": primary[0]["sampling_universe_size"],
        "sampling_universe_sha256": primary[0]["sampling_universe_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
