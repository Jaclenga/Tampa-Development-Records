#!/usr/bin/env python3
"""Build deterministic active subsets for manual-validation plan v2."""

from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
PLAN_VERSION = "2.0.0"
SEED = 20260903

CORE_SOURCE = PROCESSED / "manual_validation_second_review.csv"
CORE_OUTPUT = PROCESSED / "manual_validation_core_reliability.csv"
ACCELA_OUTPUT = PROCESSED / "manual_validation_accela_audit_plan.csv"
LONGITUDINAL_OUTPUT = PROCESSED / "manual_validation_longitudinal_initial_plan.csv"

CORE_QUOTAS = {
    "capital_project": 9,
    "cross_source_merge": 3,
    "historic_preservation": 2,
    "permit": 8,
    "planning": 3,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def stable_rank(scope: str, identifier: str) -> str:
    return hashlib.sha256(f"{SEED}|{PLAN_VERSION}|{scope}|{identifier}".encode()).hexdigest()


def ranked(rows: list[dict[str, str]], scope: str, id_field: str) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: (stable_rank(scope, row[id_field]), row[id_field]))


def write_new(path: Path, rows: list[dict[str, str]], columns: list[str], force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite active validation plan file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def build_core_reliability() -> tuple[list[dict[str, str]], list[str]]:
    rows = read_csv(CORE_SOURCE)
    columns = list(rows[0])
    by_stratum: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_stratum[row["sampling_stratum"]].append(row)
    selected = []
    for stratum, quota in CORE_QUOTAS.items():
        group = ranked(by_stratum[stratum], f"core|{stratum}", "audit_sample_id")
        if len(group) < quota:
            raise ValueError(f"Not enough frozen second-review candidates in {stratum}")
        selected.extend(group[:quota])
    selected = ranked(selected, "core|order", "audit_sample_id")
    return selected, columns


def portfolio_rows(
    rows: list[dict[str, str]], *, component: str, source_file: str,
    difficult_count: int, control_count: int,
) -> list[dict[str, str]]:
    difficult = [
        row for row in rows
        if "relatively_rare_type" in row["sampling_stratum"] or "|prospective|" in row["sampling_stratum"]
    ]
    difficult_ids = {
        row["validation_sample_id"]
        for row in ranked(difficult, f"{component}|difficult", "validation_sample_id")[:difficult_count]
    }
    controls = [row for row in rows if row["validation_sample_id"] not in difficult_ids]
    control_ids = {
        row["validation_sample_id"]
        for row in ranked(controls, f"{component}|control", "validation_sample_id")[:control_count]
    }
    selected = []
    for row in rows:
        identifier = row["validation_sample_id"]
        if identifier in difficult_ids:
            tier, reason = "elevated", "prospective observation or relatively rare record type"
        elif identifier in control_ids:
            tier, reason = "control", "deterministic comparison case"
        else:
            continue
        selected.append({
            "portfolio_case_id": f"laa-{len(selected) + 1:03d}",
            "plan_version": PLAN_VERSION,
            "selection_seed": str(SEED),
            "audit_component": component,
            "source_assignment_file": source_file,
            "source_validation_sample_id": identifier,
            "risk_tier": tier,
            "risk_reason": reason,
            "sampling_stratum": row["sampling_stratum"],
        })
    return selected


def build_accela_portfolio() -> list[dict[str, str]]:
    source_name = "manual_validation_accela_source_fidelity.csv"
    normalization_name = "manual_validation_accela_normalization.csv"
    linkage_name = "manual_validation_integration_links.csv"
    selected = portfolio_rows(
        read_csv(PROCESSED / source_name), component="source_fidelity_spot_check",
        source_file=f"data/processed/{source_name}", difficult_count=8, control_count=7,
    )
    selected.extend(portfolio_rows(
        read_csv(PROCESSED / normalization_name), component="normalization_and_semantics",
        source_file=f"data/processed/{normalization_name}", difficult_count=18, control_count=12,
    ))
    linkage = read_csv(PROCESSED / linkage_name)
    for stratum in ("matched_gis_accela", "retained_unmatched_accela"):
        group = [row for row in linkage if row["sampling_stratum"] == stratum]
        for row in ranked(group, f"linkage|{stratum}", "validation_sample_id")[:15]:
            selected.append({
                "portfolio_case_id": "",
                "plan_version": PLAN_VERSION,
                "selection_seed": str(SEED),
                "audit_component": "linkage_and_deduplication",
                "source_assignment_file": f"data/processed/{linkage_name}",
                "source_validation_sample_id": row["validation_sample_id"],
                "risk_tier": "elevated",
                "risk_reason": "matched-link false-positive risk" if stratum == "matched_gis_accela" else "unmatched-link false-negative risk",
                "sampling_stratum": stratum,
            })
    selected = sorted(
        selected,
        key=lambda row: (row["audit_component"], stable_rank("accela|order", row["source_validation_sample_id"])),
    )
    for index, row in enumerate(selected, 1):
        row["portfolio_case_id"] = f"laa-{index:03d}"
    if len(selected) != 75:
        raise AssertionError(f"Expected 75 Accela audit cases, got {len(selected)}")
    return selected


def build_longitudinal_subset() -> list[dict[str, str]]:
    rows = read_csv(PROCESSED / "manual_validation_change_events.csv")
    high_impact_types = {
        "capital_project_phase_changed", "planned_date_changed", "status_changed",
        "new_record", "record_disappeared", "reported_actual_cost_changed", "estimated_cost_changed",
    }
    high = [row for row in rows if row["detected_change_type"] in high_impact_types]
    controls = [row for row in rows if row["detected_change_type"] not in high_impact_types]
    chosen = [
        (row, "high_impact", "substantively important or alert-relevant change type")
        for row in ranked(high, "longitudinal|high", "validation_sample_id")[:20]
    ]
    chosen.extend(
        (row, "control", "deterministic control from other detected changes")
        for row in ranked(controls, "longitudinal|control", "validation_sample_id")[:10]
    )
    chosen.sort(key=lambda item: stable_rank("longitudinal|order", item[0]["validation_sample_id"]))
    output = []
    for index, (row, tier, reason) in enumerate(chosen, 1):
        output.append({
            "audit_case_id": f"lli-{index:03d}",
            "plan_version": PLAN_VERSION,
            "selection_seed": str(SEED),
            "source_assignment_file": "data/processed/manual_validation_change_events.csv",
            "source_validation_sample_id": row["validation_sample_id"],
            "risk_tier": tier,
            "risk_reason": reason,
            "detected_change_type": row["detected_change_type"],
        })
    if len(output) != 30:
        raise AssertionError(f"Expected 30 longitudinal audit cases, got {len(output)}")
    return output


def build(*, force: bool = False) -> dict[str, int]:
    core, core_columns = build_core_reliability()
    accela = build_accela_portfolio()
    longitudinal = build_longitudinal_subset()
    plan_columns = [
        "portfolio_case_id", "plan_version", "selection_seed", "audit_component",
        "source_assignment_file", "source_validation_sample_id", "risk_tier", "risk_reason",
        "sampling_stratum",
    ]
    longitudinal_columns = [
        "audit_case_id", "plan_version", "selection_seed", "source_assignment_file",
        "source_validation_sample_id", "risk_tier", "risk_reason", "detected_change_type",
    ]
    write_new(CORE_OUTPUT, core, core_columns, force)
    write_new(ACCELA_OUTPUT, accela, plan_columns, force)
    write_new(LONGITUDINAL_OUTPUT, longitudinal, longitudinal_columns, force)
    return {"core_reliability": len(core), "targeted_accela": len(accela), "initial_longitudinal": len(longitudinal)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace existing v2 plan files before review begins")
    args = parser.parse_args()
    print(build(force=args.force))


if __name__ == "__main__":
    main()
