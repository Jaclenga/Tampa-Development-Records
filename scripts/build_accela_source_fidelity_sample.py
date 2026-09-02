#!/usr/bin/env python3
"""Create the frozen Accela source-fidelity probability sample."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

try:
    from . import validation_sampling as sampling
except ImportError:
    import validation_sampling as sampling


INPUT = sampling.ROOT / "data" / "processed" / "accela_records.csv"
OUTPUT = sampling.ROOT / "data" / "processed" / "manual_validation_accela_source_fidelity.csv"
SECOND_OUTPUT = sampling.ROOT / "data" / "processed" / "manual_validation_accela_source_fidelity_second_review.csv"
STUDY_ID = "accela_source_fidelity"
PROTOCOL_VERSION = "1.0.0"
DEFAULT_SEED = 20260911
DEFAULT_TARGET = 200

CONTEXT_FIELDS = (
    "record_id", "record_number", "source_module", "record_type", "record_status",
    "opened_date", "filed_date", "issued_date", "event_date", "event_date_type",
    "temporal_evidence", "snapshot_date", "source_url",
)
REVIEW_FIELDS = (
    "review_status", "source_record_found", "record_number_matches", "module_matches",
    "record_type_matches", "status_matches", "primary_date_matches", "identity_matches",
    "source_fidelity_outcome", "evidence_reference", "review_notes", "reviewer_code", "reviewed_at",
)


def observation_type(row: dict[str, str]) -> str:
    return "prospective" if row.get("temporal_evidence") == "prospective_snapshot" else "retrospective"


def time_period(row: dict[str, str]) -> str:
    year_text = (row.get("event_date") or row.get("opened_date") or "")[:4]
    if not year_text.isdigit():
        return "unknown_period"
    year = int(year_text)
    if year <= 2022:
        return "2020_2022"
    if year <= 2024:
        return "2023_2024"
    return "2025_2026"


def candidates(records: list[dict[str, str]]) -> list[dict[str, str]]:
    type_counts = Counter((row.get("source_module", ""), row.get("record_type", "")) for row in records)
    result = []
    for record in records:
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
    records: list[dict[str, str]], *, target: int = DEFAULT_TARGET, seed: int = DEFAULT_SEED
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    universe = candidates(records)
    primary = sampling.build_primary_rows(
        universe,
        identity_field="record_id",
        context_fields=CONTEXT_FIELDS,
        review_fields=REVIEW_FIELDS,
        target=target,
        seed=seed,
        study_id=STUDY_ID,
        protocol_version=PROTOCOL_VERSION,
        generated_from="data/processed/accela_records.csv",
        sample_prefix="asf",
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
        "sampling_universe_rows": primary[0]["sampling_universe_size"],
        "sampling_universe_sha256": primary[0]["sampling_universe_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
