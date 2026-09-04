#!/usr/bin/env python3
"""Shared deterministic sampling primitives for additive validation studies."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
VALID_REVIEW_STATUSES = {"", "pending", "in_progress", "complete", "excluded"}
FOUR_WAY_OUTCOMES = {"", "yes", "no", "unknown", "not_applicable"}

DESIGN_FIELDS = (
    "validation_sample_id",
    "study_id",
    "protocol_version",
    "random_seed",
    "sampling_universe_sha256",
    "sampling_universe_size",
    "target_sample_size",
    "sampling_stratum",
    "stratum_population",
    "stratum_sample_size",
    "inclusion_probability",
    "sampling_weight",
    "sample_order",
    "generated_from",
)

SECOND_REVIEW_FIELDS = (
    "second_review_status",
    "second_reviewer_code",
    "second_reviewed_at",
    "second_outcome",
    "first_reviewer_code",
    "first_outcome",
    "agreement",
    "adjudication_status",
    "adjudicated_outcome",
    "adjudication_notes",
)


@dataclass(frozen=True)
class DrawnRow:
    row: dict[str, str]
    stratum: str
    population: int
    sample_size: int
    rank: str


def read_csv(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(2**31 - 1)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def atomic_write_csv(path: Path, rows: Iterable[dict], columns: Iterable[str]) -> None:
    rows = list(rows)
    columns = tuple(columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def canonical_universe_hash(
    rows: list[dict[str, str]], identity_field: str, stratum_field: str
) -> str:
    payload = [
        [row.get(identity_field, ""), row.get(stratum_field, "")]
        for row in sorted(rows, key=lambda item: item.get(identity_field, ""))
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def deterministic_rank(seed: int, study_id: str, purpose: str, stratum: str, identity: str) -> str:
    token = f"{seed}|{study_id}|{purpose}|{stratum}|{identity}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def proportional_allocation(
    populations: dict[str, int], target: int, minimum_per_stratum: int
) -> dict[str, int]:
    if target <= 0:
        raise ValueError("target must be positive")
    if target > sum(populations.values()):
        raise ValueError("target exceeds the sampling universe")
    nonempty = {key: value for key, value in populations.items() if value > 0}
    quotas = {key: min(minimum_per_stratum, value) for key, value in nonempty.items()}
    if sum(quotas.values()) > target:
        raise ValueError("target is too small for the requested stratum minimum")
    while sum(quotas.values()) < target:
        remaining = target - sum(quotas.values())
        available = {key: nonempty[key] - quotas[key] for key in nonempty if quotas[key] < nonempty[key]}
        total_population = sum(nonempty[key] for key in available)
        if not available:
            raise AssertionError("allocation exhausted before reaching target")
        ideals = {
            key: remaining * nonempty[key] / total_population
            for key in available
        }
        additions = {
            key: min(available[key], int(ideals[key]))
            for key in available
        }
        if sum(additions.values()) == 0:
            key = max(available, key=lambda item: (ideals[item], nonempty[item], item))
            additions[key] = 1
        for key, addition in additions.items():
            quotas[key] += min(addition, target - sum(quotas.values()))
            if sum(quotas.values()) == target:
                break
    return quotas


def deterministic_stratified_draw(
    rows: list[dict[str, str]],
    *,
    identity_field: str,
    stratum_field: str,
    target: int,
    seed: int,
    study_id: str,
    purpose: str = "first_review",
    minimum_per_stratum: int = 1,
    fixed_quotas: dict[str, int] | None = None,
) -> list[DrawnRow]:
    identities = [row.get(identity_field, "").strip() for row in rows]
    if any(not identity for identity in identities):
        raise ValueError(f"sampling universe contains blank {identity_field}")
    if len(identities) != len(set(identities)):
        raise ValueError(f"sampling universe contains duplicate {identity_field}")
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        stratum = row.get(stratum_field, "").strip()
        if not stratum:
            raise ValueError("sampling universe contains a blank stratum")
        groups[stratum].append(row)
    populations = {key: len(value) for key, value in groups.items()}
    quotas = fixed_quotas or proportional_allocation(populations, target, minimum_per_stratum)
    if sum(quotas.values()) != target:
        raise ValueError(f"stratum quotas sum to {sum(quotas.values())}, expected {target}")
    unknown = sorted(set(quotas) - set(groups))
    if unknown:
        raise ValueError(f"quotas reference absent strata: {unknown}")
    drawn: list[DrawnRow] = []
    for stratum in sorted(quotas):
        quota = quotas[stratum]
        population = groups[stratum]
        if quota > len(population):
            raise ValueError(f"stratum {stratum} has {len(population)} rows but quota {quota}")
        ranked = sorted(
            population,
            key=lambda row: deterministic_rank(
                seed, study_id, purpose, stratum, row[identity_field]
            ),
        )
        for row in ranked[:quota]:
            drawn.append(DrawnRow(
                row=row,
                stratum=stratum,
                population=len(population),
                sample_size=quota,
                rank=deterministic_rank(seed, study_id, purpose, stratum, row[identity_field]),
            ))
    return sorted(drawn, key=lambda item: (item.stratum, item.rank, item.row[identity_field]))


def build_primary_rows(
    candidates: list[dict[str, str]],
    *,
    identity_field: str,
    context_fields: tuple[str, ...],
    review_fields: tuple[str, ...],
    target: int,
    seed: int,
    study_id: str,
    protocol_version: str,
    generated_from: str,
    sample_prefix: str,
    minimum_per_stratum: int = 1,
    fixed_quotas: dict[str, int] | None = None,
) -> list[dict[str, str]]:
    universe_hash = canonical_universe_hash(candidates, identity_field, "sampling_stratum")
    drawn = deterministic_stratified_draw(
        candidates,
        identity_field=identity_field,
        stratum_field="sampling_stratum",
        target=target,
        seed=seed,
        study_id=study_id,
        minimum_per_stratum=minimum_per_stratum,
        fixed_quotas=fixed_quotas,
    )
    result = []
    for order, item in enumerate(drawn, start=1):
        row = {
            "validation_sample_id": f"{sample_prefix}-{order:03d}",
            "study_id": study_id,
            "protocol_version": protocol_version,
            "random_seed": str(seed),
            "sampling_universe_sha256": universe_hash,
            "sampling_universe_size": str(len(candidates)),
            "target_sample_size": str(target),
            "sampling_stratum": item.stratum,
            "stratum_population": str(item.population),
            "stratum_sample_size": str(item.sample_size),
            "inclusion_probability": f"{item.sample_size / item.population:.12f}",
            "sampling_weight": f"{item.population / item.sample_size:.12f}",
            "sample_order": str(order),
            "generated_from": generated_from,
        }
        row.update({field: item.row.get(field, "") for field in context_fields})
        row.update({field: "" for field in review_fields})
        result.append(row)
    return result


def build_second_review_rows(
    primary: list[dict[str, str]],
    *,
    context_fields: tuple[str, ...],
    target: int,
    seed: int,
    study_id: str,
) -> list[dict[str, str]]:
    drawn = deterministic_stratified_draw(
        primary,
        identity_field="validation_sample_id",
        stratum_field="sampling_stratum",
        target=target,
        seed=seed,
        study_id=study_id,
        purpose="blinded_second_review",
        minimum_per_stratum=1,
    )
    rows = []
    for order, item in enumerate(drawn, start=1):
        source = item.row
        row = {field: source.get(field, "") for field in (*DESIGN_FIELDS, *context_fields)}
        row.update({
            "second_review_assignment_id": f"{source['validation_sample_id']}-r2",
            "second_review_selection_probability": f"{item.sample_size / item.population:.12f}",
            "second_review_sampling_weight": f"{item.population / item.sample_size:.12f}",
            "second_review_order": str(order),
        })
        row.update({field: "" for field in SECOND_REVIEW_FIELDS})
        rows.append(row)
    return rows


def write_frozen_study(
    *,
    primary_path: Path,
    second_path: Path,
    primary_rows: list[dict[str, str]],
    second_rows: list[dict[str, str]],
    context_fields: tuple[str, ...],
    review_fields: tuple[str, ...],
    force: bool,
) -> None:
    existing = [path for path in (primary_path, second_path) if path.exists()]
    if existing and not force:
        names = []
        for path in existing:
            try:
                names.append(path.relative_to(ROOT).as_posix())
            except ValueError:
                names.append(path.name)
        raise FileExistsError(
            f"Refusing to overwrite frozen validation assignments: {', '.join(names)}. Use --force deliberately."
        )
    primary_columns = (*DESIGN_FIELDS, *context_fields, *review_fields)
    second_columns = (
        *DESIGN_FIELDS,
        *context_fields,
        "second_review_assignment_id",
        "second_review_selection_probability",
        "second_review_sampling_weight",
        "second_review_order",
        *SECOND_REVIEW_FIELDS,
    )
    atomic_write_csv(primary_path, primary_rows, primary_columns)
    atomic_write_csv(second_path, second_rows, second_columns)


def validate_enums(rows: list[dict[str, str]], fields: dict[str, set[str]]) -> None:
    for field, allowed in fields.items():
        invalid = sorted({row.get(field, "") for row in rows} - allowed)
        if invalid:
            raise ValueError(f"Invalid values for {field}: {invalid}")


def metadata_for(field: str) -> tuple[str, str, str, str, str, str, str, str]:
    """Return data-dictionary metadata for expanded validation columns."""
    design = {
        "validation_sample_id": ("Stable identifier for one validation assignment.", "text", "", "Never blank.", "validation design", "Deterministic ID after the seeded draw.", "Study prefix plus integer.", "Identifies a review unit, not a development entity."),
        "study_id": ("Validation study governing the assignment.", "categorical text", "", "Never blank.", "validation design", "Fixed by the study builder.", "Registered study ID.", "Do not combine unlike validation layers."),
        "protocol_version": ("Version of the study protocol.", "text", "", "Never blank.", "validation design", "Fixed by the study builder.", "Semantic version.", "Version changes can alter inference scope."),
        "random_seed": ("Seed for deterministic pseudo-random ranking.", "integer", "", "Never blank.", "validation design", "Explicit builder seed.", "Positive integer.", "Changing the seed changes assignments."),
        "sampling_universe_sha256": ("SHA-256 of sorted eligible identities and strata.", "text", "", "Never blank.", "sampling frame", "canonical_universe_hash().", "64 lowercase hexadecimal characters.", "Changes when the eligible frame or strata change."),
        "sampling_universe_size": ("Eligible review units in the frozen frame.", "integer", "records/events", "Never blank.", "sampling frame", "Count before selection.", "Positive integer.", "Interpret together with the universe hash."),
        "target_sample_size": ("Requested first-review sample size.", "integer", "assignments", "Never blank.", "validation design", "Explicit builder target.", "Positive integer.", "Not the number already reviewed."),
        "sampling_stratum": ("Mutually exclusive design stratum.", "categorical text", "", "Never blank.", "sampling design", "Study-specific stratum function.", "Study-defined.", "Use stratum weights for aggregate inference."),
        "stratum_population": ("Eligible units in this stratum.", "integer", "records/events", "Never blank.", "sampling frame", "Count by sampling_stratum.", "Positive integer.", "Applies only to the frozen frame."),
        "stratum_sample_size": ("First-review assignments drawn from this stratum.", "integer", "assignments", "Never blank.", "sampling design", "Deterministic proportional/minimum allocation.", "Positive integer.", "Small strata can be oversampled deliberately."),
        "inclusion_probability": ("Probability of selection within the stratum.", "decimal", "proportion", "Never blank.", "sampling design", "stratum_sample_size / stratum_population.", "Greater than 0 and at most 1.", "Required for probability-based estimates."),
        "sampling_weight": ("Inverse first-review inclusion probability.", "decimal", "eligible units represented", "Never blank.", "sampling design", "stratum_population / stratum_sample_size.", "At least 1.", "Unweighted totals are descriptive under disproportionate allocation."),
        "sample_order": ("Deterministic display order.", "integer", "", "Never blank.", "validation workflow", "Sequential order after seeded selection.", "Positive integer.", "Not an analysis weight."),
        "generated_from": ("Repository-relative source frame used by the builder.", "text", "", "Never blank.", "validation provenance", "Recorded by the builder.", "Repository-relative path list or note.", "Does not itself establish source correctness."),
    }
    if field in design:
        return design[field]
    if field in SECOND_REVIEW_FIELDS or field.startswith("second_review_") or field in {
        "second_review_assignment_id", "first_reviewer_code", "first_outcome", "agreement",
        "adjudication_status", "adjudicated_outcome", "adjudication_notes",
    }:
        return ("Independent second-review or adjudication field.", "text", "", "Blank means the blinded workflow has not reached this step.", "reviewer/adjudicator", "See docs/guides/MANUAL_VALIDATION_GUIDE.md.", "Study-defined explicit vocabulary.", "Never overwrite either original reviewer judgment.")
    if field == "review_status":
        return ("First-review workflow state.", "categorical text", "", "Blank means not started.", "reviewer", "Entered under the study guide.", "pending; in_progress; complete; excluded", "Complete does not imply a yes outcome.")
    outcome_fields = {
        "source_fidelity_outcome", "normalization_outcome", "linkage_outcome",
        "change_validation_outcome", "source_record_found", "record_number_matches",
        "module_matches", "record_type_matches", "status_matches", "primary_date_matches",
        "identity_matches", "event_type_correct", "event_date_source_field_correct",
        "event_date_value_correct", "status_normalization_correct", "retrospective_flag_correct",
        "planned_date_flag_correct", "activity_mapping_correct", "record_identity_correct",
        "false_positive_link", "false_negative_link", "ambiguous", "source_change_confirmed",
        "likely_publication_artifact",
    }
    if field in outcome_fields:
        return ("Claim-specific human-review outcome.", "categorical text", "", "Blank means not reviewed.", "reviewer", "Evidence-based decision under the study guide.", "yes; no; unknown; not_applicable", "Applies only to the named validation claim.")
    if field in {"reviewer_code", "reviewed_at", "review_notes", "evidence_reference"}:
        return ("Human-review provenance or evidence field.", "text", "", "Blank means not reviewed or unavailable.", "reviewer", "Entered under docs/guides/MANUAL_VALIDATION_GUIDE.md.", "Non-personal code, ISO timestamp, citation, or concise notes.", "Do not enter personal contact data; AI output is not evidence.")
    if field in {"human_linkage_assessment", "duplicate_assessment", "semantic_change_interpretation"}:
        return ("Study-specific human interpretation.", "categorical text", "", "Blank means not reviewed.", "reviewer", "Decision rules in docs/guides/MANUAL_VALIDATION_GUIDE.md.", "Study-defined vocabulary including unknown and not_applicable.", "Not a generic record-level accuracy score.")
    return ("Source, transformation, linkage, or change context frozen with the validation assignment.", "text", "", "Blank when the source or decision does not supply the field.", "source or deterministic transformation", "Copied without personal contact fields by the study builder.", "Source- or study-defined.", "Context is not a human validation judgment.")
