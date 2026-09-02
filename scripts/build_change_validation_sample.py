#!/usr/bin/env python3
"""Create the frozen longitudinal change-event validation sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from . import validation_sampling as sampling
except ImportError:
    import validation_sampling as sampling


INDEX = sampling.ROOT / "data" / "monthly_changes" / "index.json"
OUTPUT = sampling.ROOT / "data" / "processed" / "manual_validation_change_events.csv"
SECOND_OUTPUT = sampling.ROOT / "data" / "processed" / "manual_validation_change_events_second_review.csv"
STUDY_ID = "longitudinal_change_events"
PROTOCOL_VERSION = "1.0.0"
DEFAULT_SEED = 20260914
DEFAULT_TARGET = 75

CONTEXT_FIELDS = (
    "change_id", "previous_snapshot", "current_snapshot", "source", "record_identity",
    "source_record_id", "detected_change_type", "changed_fields", "old_value",
    "new_value", "source_url", "machine_interpretation",
)
REVIEW_FIELDS = (
    "review_status", "source_change_confirmed", "semantic_change_interpretation",
    "likely_publication_artifact", "change_validation_outcome", "evidence_reference",
    "review_notes", "reviewer_code", "reviewed_at",
)


def load_change_universe(index_path: Path = INDEX) -> tuple[list[dict[str, str]], list[str]]:
    index = json.loads(index_path.read_text(encoding="utf-8"))
    records = []
    sources = []
    for comparison in index.get("comparisons", []):
        csv_path = sampling.ROOT / comparison["csv"]
        sources.append(comparison["csv"])
        records.extend(sampling.read_csv(csv_path))
    return records, sources


def candidates(changes: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for change in changes:
        result.append({
            "sampling_stratum": change.get("change_type", "") or "unknown_change_type",
            "change_id": change.get("change_id", ""),
            "previous_snapshot": change.get("before_snapshot_date", ""),
            "current_snapshot": change.get("after_snapshot_date", ""),
            "source": change.get("source_name", ""),
            "record_identity": change.get("record_identity", ""),
            "source_record_id": change.get("source_record_id", ""),
            "detected_change_type": change.get("change_type", ""),
            "changed_fields": change.get("changed_fields", ""),
            "old_value": change.get("old_value", ""),
            "new_value": change.get("new_value", ""),
            "source_url": change.get("source_url", ""),
            "machine_interpretation": change.get("interpretation_note", ""),
        })
    return result


def build(
    changes: list[dict[str, str]],
    *,
    generated_from: str,
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    universe = candidates(changes)
    primary = sampling.build_primary_rows(
        universe,
        identity_field="change_id",
        context_fields=CONTEXT_FIELDS,
        review_fields=REVIEW_FIELDS,
        target=min(target, len(universe)),
        seed=seed,
        study_id=STUDY_ID,
        protocol_version=PROTOCOL_VERSION,
        generated_from=generated_from,
        sample_prefix="lce",
        minimum_per_stratum=3,
    )
    second = sampling.build_second_review_rows(
        primary,
        context_fields=CONTEXT_FIELDS,
        target=max(1, round(len(primary) * 0.25)),
        seed=seed,
        study_id=STUDY_ID,
    )
    return primary, second


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--second-output", type=Path, default=SECOND_OUTPUT)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    changes, sources = load_change_universe(args.index)
    primary, second = build(
        changes,
        generated_from=";".join(sources),
        target=args.target,
        seed=args.seed,
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
        "comparisons_in_frame": len(sources),
        "sampling_universe_rows": primary[0]["sampling_universe_size"],
        "sampling_universe_sha256": primary[0]["sampling_universe_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
