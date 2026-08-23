#!/usr/bin/env python3
"""Build the reproducible, stratified manual-validation study files.

The development and holdout draws use separate deterministic pseudo-random
rankings. Reviewer-entered columns are intentionally blank. This module does
not inspect external evidence or make validation judgments.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"
PROTOCOL_VERSION = "1.0.0"
RANDOM_SEED = 20260823

# Disjoint strata make each activity's inclusion probability explicit. The
# cross-source stratum takes precedence over source-family strata.
PHASE_QUOTAS = {
    "development": {
        "cross_source_merge": 13,
        "permit": 33,
        "planning": 13,
        "historic_preservation": 7,
        "capital_project": 34,
    },
    "holdout": {
        "cross_source_merge": 7,
        "permit": 17,
        "planning": 7,
        "historic_preservation": 3,
        "capital_project": 16,
    },
}

SECOND_REVIEW_QUOTAS = {
    "development": {
        "cross_source_merge": 4,
        "permit": 11,
        "planning": 4,
        "historic_preservation": 2,
        "capital_project": 13,
    },
    "holdout": {
        "cross_source_merge": 2,
        "permit": 5,
        "planning": 2,
        "historic_preservation": 1,
        "capital_project": 6,
    },
}

CLAIM_RESULT_FIELDS = (
    "source_identity_result",
    "activity_classification_result",
    "cross_source_linkage_result",
    "status_interpretation_result",
    "building_footprint_match_result",
)

REVIEW_FIELDS = (
    "review_status",
    *CLAIM_RESULT_FIELDS,
    "reviewed_activity_class",
    "reviewed_activity_stage",
    "physical_work_evidence",
    "evidence_source_types",
    "primary_evidence_url",
    "secondary_evidence_url",
    "evidence_document_reference",
    "evidence_accessed_at_utc",
    "ai_assistance_used",
    "manual_evidence_confirmed",
    "reviewer_id",
    "reviewed_at_utc",
    "review_notes",
)

CONTEXT_FIELDS = (
    "audit_sample_id",
    "protocol_version",
    "random_seed",
    "sample_phase",
    "sampling_stratum",
    "stratum_population",
    "phase_sample_size",
    "selection_probability",
    "sampling_weight",
    "sample_order",
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
    "neighborhood",
    "council_district",
    "latitude",
    "longitude",
    "record_type",
    "project_name",
    "description",
    "source_url",
)


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def read_csv(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def random_rank(activity_id: str, phase: str, stratum: str, purpose: str) -> str:
    token = f"{RANDOM_SEED}|{PROTOCOL_VERSION}|{purpose}|{phase}|{stratum}|{activity_id}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sampling_stratum(activity: dict) -> str:
    memberships = {x for x in clean(activity.get("source_memberships")).split(";") if x}
    if len(memberships) > 1:
        return "cross_source_merge"
    if "historic_preservation" in memberships:
        return "historic_preservation"
    if "development_coordination" in memberships:
        return "planning"
    if any(source.startswith("capital_") for source in memberships):
        return "capital_project"
    if memberships & {"construction_inspections", "single_family_permits"}:
        return "permit"
    raise ValueError(f"Activity {activity.get('activity_id')} has no validation stratum: {sorted(memberships)}")


def _ensure_capacity(populations: dict[str, list[dict]]) -> None:
    required = {
        stratum: sum(PHASE_QUOTAS[phase][stratum] for phase in PHASE_QUOTAS)
        for stratum in PHASE_QUOTAS["development"]
    }
    shortages = {
        stratum: {"available": len(populations.get(stratum, [])), "required": quota}
        for stratum, quota in required.items()
        if len(populations.get(stratum, [])) < quota
    }
    if shortages:
        raise ValueError(f"Validation strata are too small: {json.dumps(shortages, sort_keys=True)}")


def draw_sample(activities: list[dict], matches: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return the 150 first-review rows and 50 blinded second-review rows."""
    by_match: dict[str, list[dict]] = defaultdict(list)
    for match in matches:
        by_match[match["activity_id"]].append(match)

    populations: dict[str, list[dict]] = defaultdict(list)
    for activity in activities:
        populations[sampling_stratum(activity)].append(activity)
    _ensure_capacity(populations)

    selected: list[tuple[str, str, dict]] = []
    already_selected: set[str] = set()
    for phase in ("development", "holdout"):
        for stratum, quota in PHASE_QUOTAS[phase].items():
            eligible = [row for row in populations[stratum] if row["activity_id"] not in already_selected]
            ranked = sorted(
                eligible,
                key=lambda row: random_rank(row["activity_id"], phase, stratum, "first-review"),
            )
            chosen = ranked[:quota]
            selected.extend((phase, stratum, row) for row in chosen)
            already_selected.update(row["activity_id"] for row in chosen)

    # Derive the dataset's pre-review physical-work claim from the same build
    # rules used for activity_truth_status.csv; do not depend on a stale file.
    import ground_truth

    truth_by_id = {row["activity_id"]: row for row in ground_truth.build_truth(activities)}

    first_rows: list[dict] = []
    phase_counters: dict[str, int] = defaultdict(int)
    for phase, stratum, activity in selected:
        phase_counters[phase] += 1
        phase_n = PHASE_QUOTAS[phase][stratum]
        population_n = len(populations[stratum])
        activity_matches = by_match.get(activity["activity_id"], [])
        truth = truth_by_id.get(activity["activity_id"], {})
        row = {
            "audit_sample_id": f"{phase[:3]}-{phase_counters[phase]:03d}",
            "protocol_version": PROTOCOL_VERSION,
            "random_seed": RANDOM_SEED,
            "sample_phase": phase,
            "sampling_stratum": stratum,
            "stratum_population": population_n,
            "phase_sample_size": phase_n,
            "selection_probability": f"{phase_n / population_n:.10f}",
            "sampling_weight": f"{population_n / phase_n:.10f}",
            "sample_order": phase_counters[phase],
            "activity_id": activity["activity_id"],
            "source_record_id": activity.get("source_record_id", ""),
            "source_memberships": activity.get("source_memberships", ""),
            "activity_class": activity.get("activity_class", ""),
            "activity_stage": activity.get("activity_stage", ""),
            "status": activity.get("status", ""),
            "physical_work_started_dataset": truth.get("physical_work_started", "unknown"),
            "realization_evidence_grade": activity.get("realization_evidence_grade", ""),
            "parcel_match_confidence": activity.get("parcel_match_confidence", ""),
            "match_methods": ";".join(sorted({clean(m.get("match_method")) for m in activity_matches})),
            "match_distances_m": ";".join(clean(m.get("match_distance_m")) for m in activity_matches),
            "address": activity.get("address", ""),
            "neighborhood": activity.get("neighborhood", ""),
            "council_district": activity.get("council_district", ""),
            "latitude": activity.get("latitude", ""),
            "longitude": activity.get("longitude", ""),
            "record_type": activity.get("record_type", ""),
            "project_name": activity.get("project_name", ""),
            "description": activity.get("description", ""),
            "source_url": activity.get("source_url", ""),
        }
        row.update({field: "" for field in REVIEW_FIELDS})
        first_rows.append(row)

    first_by_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in first_rows:
        first_by_group[(row["sample_phase"], row["sampling_stratum"])].append(row)
    second_rows: list[dict] = []
    for phase in ("development", "holdout"):
        for stratum, quota in SECOND_REVIEW_QUOTAS[phase].items():
            ranked = sorted(
                first_by_group[(phase, stratum)],
                key=lambda row: random_rank(row["activity_id"], phase, stratum, "second-review"),
            )
            for first in ranked[:quota]:
                # Context is copied, but no first-review answer is exposed.
                second = {field: first[field] for field in CONTEXT_FIELDS}
                second.update({field: "" for field in REVIEW_FIELDS})
                second_rows.append(second)

    if len(first_rows) != 150 or len(second_rows) != 50:
        raise AssertionError(f"Unexpected study sizes: first={len(first_rows)}, second={len(second_rows)}")
    if len({row["activity_id"] for row in first_rows}) != 150:
        raise AssertionError("First-review sample contains duplicate activities")
    return first_rows, second_rows


def merge_reviews(fresh: list[dict], existing_sets: list[list[dict]], label: str) -> None:
    """Copy reviewer fields when the frozen sampling context is unchanged."""
    fresh_by_id = {row["audit_sample_id"]: row for row in fresh}
    for existing in existing_sets:
        for old in existing:
            if not any(clean(old.get(field)) for field in REVIEW_FIELDS):
                continue
            new = fresh_by_id.get(old.get("audit_sample_id", ""))
            if new is None:
                raise RuntimeError(f"Refusing to remap populated {label} review {old.get('audit_sample_id')}")
            changed_context = [
                field for field in CONTEXT_FIELDS
                if clean(old.get(field)) != clean(new.get(field))
            ]
            if changed_context:
                raise RuntimeError(
                    f"Refusing to attach populated {label} review {old['audit_sample_id']} to changed context: "
                    + ", ".join(changed_context)
                )
            for field in REVIEW_FIELDS:
                value = old.get(field, "")
                if value and new.get(field) and value != new[field]:
                    raise RuntimeError(
                        f"Conflicting populated {label} values for {old['audit_sample_id']} field {field}"
                    )
                if value:
                    new[field] = value


def write_study_files(
    activities: list[dict], matches: list[dict], *, protect_completed: bool = True
) -> tuple[list[dict], list[dict]]:
    outputs = (
        PROCESSED / "manual_validation_sample.csv",
        PROCESSED / "manual_validation_development_sample.csv",
        PROCESSED / "manual_validation_holdout_sample.csv",
        PROCESSED / "manual_validation_second_review.csv",
    )
    first, second = draw_sample(activities, matches)
    if protect_completed:
        first_sources = [read_csv(path) for path in outputs[:3] if path.exists()]
        second_sources = [read_csv(outputs[3])] if outputs[3].exists() else []
        merge_reviews(first, first_sources, "first-review")
        merge_reviews(second, second_sources, "second-review")
    columns = CONTEXT_FIELDS + REVIEW_FIELDS
    write_csv(outputs[0], first, columns)
    write_csv(outputs[1], [row for row in first if row["sample_phase"] == "development"], columns)
    write_csv(outputs[2], [row for row in first if row["sample_phase"] == "holdout"], columns)
    write_csv(outputs[3], second, columns)
    return first, second


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Discard populated reviewer fields. Use only when deliberately starting a new versioned study.",
    )
    args = parser.parse_args()
    activities = read_csv(PROCESSED / "tampa_development_activity.csv")
    matches = read_csv(PROCESSED / "parcel_building_matches.csv")
    first, second = write_study_files(activities, matches, protect_completed=not args.force)
    summary = {
        "protocol_version": PROTOCOL_VERSION,
        "random_seed": RANDOM_SEED,
        "first_review_rows": len(first),
        "development_rows": sum(row["sample_phase"] == "development" for row in first),
        "holdout_rows": sum(row["sample_phase"] == "holdout" for row in first),
        "second_review_rows": len(second),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
