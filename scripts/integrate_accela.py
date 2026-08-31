#!/usr/bin/env python3
"""Build a duplicate-safe activity dataset combining the core release and Accela.

The eight-layer ArcGIS bounded census remains unchanged. This script writes a
separate integrated edition: exact public record-number matches enrich one
existing activity, while unmatched Accela records become new deterministic
activities. Ambiguous matches are retained in the audit but never auto-merged.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import sys
from typing import Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tampa_accela.csv_safety import restore_csv_row, safe_csv_row

CORE_ACTIVITY = ROOT / "data" / "processed" / "tampa_development_activity.csv"
CORE_SOURCES = ROOT / "data" / "processed" / "source_records.csv"
ACCELA_RECORDS = ROOT / "data" / "processed" / "accela_records.csv"
OUTPUT_DIR = ROOT / "data" / "integrated"
OUTPUT = OUTPUT_DIR / "tampa_development_activity_with_accela.csv"
AUDIT = OUTPUT_DIR / "accela_integration_audit.csv"
REPORT = OUTPUT_DIR / "accela_integration_report.json"

AUDIT_FIELDS = [
    "accela_record_id", "record_number", "source_module", "disposition",
    "match_method", "matched_activity_id", "integrated_activity_id",
    "duplicate_key", "review_required",
]
TEMPORAL_FIELDS = [
    "event_date", "event_date_type", "first_observed_date", "snapshot_date",
    "last_observed_date", "historical_reconstruction", "temporal_evidence",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(2**31 - 1)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [restore_csv_row(row) for row in csv.DictReader(handle)]


def atomic_write(path: Path, render) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            render(handle)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.1 * (2**attempt))
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def write_csv(path: Path, rows: Iterable[Mapping[str, object]], fields: list[str]) -> None:
    materialized = list(rows)

    def render(handle) -> None:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(safe_csv_row({field: row.get(field, "") for field in fields}) for row in materialized)

    atomic_write(path, render)


def write_json(path: Path, value: object) -> None:
    atomic_write(path, lambda handle: handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n"))


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def public_number(value: object) -> str:
    """Canonical exact-match key tolerant only of punctuation/spacing changes."""
    return re.sub(r"[^A-Z0-9]", "", clean(value).upper())


def hash_activity(seed: str) -> str:
    return "tpa-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]


def activity_id_for(record: Mapping[str, str]) -> str:
    native = clean(record.get("record_number")).upper()
    if clean(record.get("source_module")).lower() == "building":
        # Matches build_release.activity_key() for future ArcGIS permit rows.
        return hash_activity(f"permit|{native}")
    return hash_activity(f"accela_{clean(record.get('source_module')).lower()}|{native}")


def merge_nonblank(rows: list[dict[str, str]]) -> dict[str, str]:
    """Merge repeated observations, preferring later and more complete rows."""
    ranked = sorted(
        rows,
        key=lambda row: (
            clean(row.get("retrieved_at")),
            sum(bool(clean(value)) for value in row.values()),
            clean(row.get("record_id")),
        ),
    )
    result: dict[str, str] = {}
    for row in ranked:
        for key, value in row.items():
            if clean(value):
                result[key] = value
            elif key not in result:
                result[key] = ""
    first_observed = [clean(row.get("first_observed_date")) for row in rows if clean(row.get("first_observed_date"))]
    last_observed = [clean(row.get("last_observed_date")) for row in rows if clean(row.get("last_observed_date"))]
    snapshot_dates = [clean(row.get("snapshot_date")) for row in rows if clean(row.get("snapshot_date"))]
    if first_observed:
        result["first_observed_date"] = min(first_observed)
    if last_observed:
        result["last_observed_date"] = max(last_observed)
    if snapshot_dates:
        result["snapshot_date"] = max(snapshot_dates)
    return result


def deduplicate_accela(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    """Deduplicate stable IDs first, then canonical public record numbers."""
    by_stable: dict[str, list[dict[str, str]]] = {}
    missing_stable: list[dict[str, str]] = []
    for row in rows:
        stable = clean(row.get("record_id"))
        if not stable:
            missing_stable.append(row)
            continue
        by_stable.setdefault(stable, []).append(row)
    stable_rows = [merge_nonblank(group) for _, group in sorted(by_stable.items())]

    by_number: dict[str, list[dict[str, str]]] = {}
    missing_number: list[dict[str, str]] = []
    for row in stable_rows:
        key = public_number(row.get("record_number"))
        if not key:
            missing_number.append(row)
            continue
        by_number.setdefault(key, []).append(row)

    unique: list[dict[str, str]] = []
    audit: list[dict[str, str]] = []
    for key, group in sorted(by_number.items()):
        winner = merge_nonblank(group)
        unique.append(winner)
        for duplicate in group[1:]:
            audit.append({
                "accela_record_id": duplicate.get("record_id", ""),
                "record_number": duplicate.get("record_number", ""),
                "source_module": duplicate.get("source_module", ""),
                "disposition": "deduplicated_accela_record_number",
                "match_method": "canonical_public_record_number",
                "matched_activity_id": "", "integrated_activity_id": "",
                "duplicate_key": key, "review_required": "false",
            })
    for row in missing_stable + missing_number:
        audit.append({
            "accela_record_id": row.get("record_id", ""),
            "record_number": row.get("record_number", ""),
            "source_module": row.get("source_module", ""),
            "disposition": "excluded_missing_stable_identity",
            "match_method": "none", "matched_activity_id": "", "integrated_activity_id": "",
            "duplicate_key": "", "review_required": "true",
        })
    return unique, audit, {
        "duplicate_stable_id_rows_removed": len(rows) - len(stable_rows) - len(missing_stable),
        "duplicate_record_number_rows_removed": len(stable_rows) - len(unique) - len(missing_number),
        "missing_stable_id_rows": len(missing_stable),
        "missing_record_number_rows": len(missing_number),
    }


def activity_class(record: Mapping[str, str]) -> tuple[str, str]:
    module = clean(record.get("source_module")).lower()
    record_type = clean(record.get("record_type")).lower()
    if module == "planning":
        return "planning_application", "0"
    if re.search(r"\b(demo|demolition|demolish)\b", record_type):
        return "demolition", "1"
    if any(term in record_type for term in ("license", "plan revision", "revision", "extension of time")):
        return "permit_administration", "0"
    if any(term in record_type for term in ("new construction", "new building", "addition", "alteration", "renovation")):
        return "building_construction", "1"
    return "other_permitted_work", "0"


def activity_stage(record: Mapping[str, str]) -> str:
    status = clean(record.get("record_status")).lower()
    module = clean(record.get("source_module")).lower()
    if any(term in status for term in ("withdraw", "cancel", "denied", "expired", "administrative close")):
        return "inactive"
    if any(term in status for term in ("issued", "approved")):
        return "permit_or_funding_approved"
    if module == "planning":
        return "planning_review"
    # ACA "Complete" is retained as status text but is not promoted to proof
    # of physical completion without an inspection/certificate event.
    return "preconstruction_or_unknown"


def new_activity(record: Mapping[str, str], fields: list[str]) -> dict[str, object]:
    row: dict[str, object] = {field: "" for field in fields}
    classification, candidate = activity_class(record)
    module = clean(record.get("source_module"))
    opened = clean(record.get("opened_date") or record.get("filed_date"))
    row.update({
        "source_memberships": f"accela_{module.lower()}",
        "source_record_id": clean(record.get("record_number")),
        "activity_stage": activity_stage(record),
        "status": clean(record.get("record_status")),
        "source_endpoint": f"https://aca-prod.accela.com/TAMPA/Cap/CapHome.aspx?module={module}&TabName={module}",
        "retrieved_at_utc": clean(record.get("retrieved_at")),
        "project_name": clean(record.get("record_type")),
        "description": clean(record.get("description") or record.get("work_description")),
        "activity_class": classification,
        "record_type": clean(record.get("record_type")),
        "address": clean(record.get("address")),
        "zip": clean(record.get("postal_code")),
        "last_updated": clean(record.get("updated_date")),
        "estimated_cost_usd": clean(record.get("valuation") or record.get("estimated_cost")),
        "physical_development_candidate": candidate,
        "source_url": clean(record.get("source_url")),
        "activity_id": activity_id_for(record),
        "record_created_date": opened,
        "application_or_opened_date": opened,
        "raw_component_rows": "1",
        "location_count": "0",
        "realization_evidence_grade": "U",
        "likely_realized": "",
        "realization_basis": "accela_administrative_record_only",
        **{field: clean(record.get(field)) for field in TEMPORAL_FIELDS},
    })
    return row


def enrich_existing(activity: dict[str, str], record: Mapping[str, str]) -> dict[str, str]:
    output = dict(activity)
    module = clean(record.get("source_module")).lower()
    memberships = {part for part in clean(output.get("source_memberships")).split(";") if part}
    memberships.add(f"accela_{module}")
    output["source_memberships"] = ";".join(sorted(memberships))
    try:
        output["raw_component_rows"] = str(int(output.get("raw_component_rows") or 0) + 1)
    except ValueError:
        output["raw_component_rows"] = output.get("raw_component_rows") or "1"
    candidates = {
        "record_type": record.get("record_type"),
        "project_name": record.get("record_type"),
        "description": record.get("description") or record.get("work_description"),
        "status": record.get("record_status"),
        "address": record.get("address"),
        "zip": record.get("postal_code"),
        "record_created_date": record.get("opened_date"),
        "application_or_opened_date": record.get("filed_date") or record.get("opened_date"),
        "last_updated": record.get("updated_date"),
        "estimated_cost_usd": record.get("valuation") or record.get("estimated_cost"),
        "source_url": record.get("source_url"),
        **{field: record.get(field) for field in TEMPORAL_FIELDS},
    }
    for field, value in candidates.items():
        if not clean(output.get(field)) and clean(value):
            output[field] = clean(value)
    return output


def integrate(
    core: list[dict[str, str]], source_rows: list[dict[str, str]], accela: list[dict[str, str]]
) -> tuple[list[dict[str, object]], list[dict[str, str]], dict[str, object]]:
    fields = list(core[0]) + [field for field in TEMPORAL_FIELDS if field not in core[0]]
    unique_accela, audit, dedup = deduplicate_accela(accela)
    activity_by_id = {row["activity_id"]: dict(row) for row in core}
    number_to_activities: dict[str, set[str]] = {}
    for row in source_rows:
        key = public_number(row.get("source_record_id"))
        if key:
            number_to_activities.setdefault(key, set()).add(row["activity_id"])
    for row in core:
        key = public_number(row.get("source_record_id"))
        if key:
            number_to_activities.setdefault(key, set()).add(row["activity_id"])

    exact_matches = appended = ambiguous = derived_collisions = 0
    for record in unique_accela:
        key = public_number(record.get("record_number"))
        matches = sorted(number_to_activities.get(key, set()))
        base_audit = {
            "accela_record_id": record.get("record_id", ""),
            "record_number": record.get("record_number", ""),
            "source_module": record.get("source_module", ""),
            "duplicate_key": key,
        }
        if len(matches) == 1:
            activity_id = matches[0]
            activity_by_id[activity_id] = enrich_existing(activity_by_id[activity_id], record)
            exact_matches += 1
            audit.append({
                **base_audit, "disposition": "merged_existing_activity",
                "match_method": "exact_public_record_number", "matched_activity_id": activity_id,
                "integrated_activity_id": activity_id, "review_required": "false",
            })
            continue
        if len(matches) > 1:
            ambiguous += 1
            audit.append({
                **base_audit, "disposition": "held_ambiguous_existing_match",
                "match_method": "ambiguous_exact_public_record_number",
                "matched_activity_id": ";".join(matches), "integrated_activity_id": "",
                "review_required": "true",
            })
            continue
        candidate = new_activity(record, fields)
        activity_id = str(candidate["activity_id"])
        if activity_id in activity_by_id:
            activity_by_id[activity_id] = enrich_existing(activity_by_id[activity_id], record)
            derived_collisions += 1
            audit.append({
                **base_audit, "disposition": "merged_existing_activity",
                "match_method": "deterministic_activity_id_collision",
                "matched_activity_id": activity_id, "integrated_activity_id": activity_id,
                "review_required": "false",
            })
            continue
        activity_by_id[activity_id] = candidate
        number_to_activities.setdefault(key, set()).add(activity_id)
        appended += 1
        audit.append({
            **base_audit, "disposition": "appended_new_activity", "match_method": "no_exact_core_match",
            "matched_activity_id": "", "integrated_activity_id": activity_id, "review_required": "false",
        })

    integrated = sorted(
        activity_by_id.values(),
        key=lambda row: (clean(row.get("activity_class")), clean(row.get("source_record_id")), clean(row.get("activity_id"))),
    )
    if len(integrated) != len({str(row["activity_id"]) for row in integrated}):
        raise RuntimeError("Integrated output contains duplicate activity_id values")
    integrated_accela_numbers = [
        public_number(row.get("source_record_id"))
        for row in integrated
        if any(part.startswith("accela_") for part in clean(row.get("source_memberships")).split(";"))
    ]
    if len(integrated_accela_numbers) != len(set(integrated_accela_numbers)):
        raise RuntimeError("Integrated output contains duplicate Accela public record numbers")
    primary_id_counts: dict[str, int] = {}
    for row in integrated:
        key = clean(row.get("source_record_id")).upper()
        if key:
            primary_id_counts[key] = primary_id_counts.get(key, 0) + 1
    reused_primary_ids = {key: count for key, count in primary_id_counts.items() if count > 1}
    report: dict[str, object] = {
        "format_version": "1.0.0",
        "core_activity_rows": len(core),
        "accela_input_rows": len(accela),
        "accela_unique_rows_after_deduplication": len(unique_accela),
        "exact_core_record_number_matches": exact_matches,
        "deterministic_activity_id_collisions_merged": derived_collisions,
        "ambiguous_exact_matches_held_for_review": ambiguous,
        "new_accela_activities_appended": appended,
        "integrated_activity_rows": len(integrated),
        "integrated_activity_ids_unique": True,
        "integrated_accela_record_numbers_unique": True,
        "inherited_cross_namespace_primary_id_reuse_groups": len(reused_primary_ids),
        "deduplication": dedup,
        "temporal_evidence_counts": {
            label: sum(clean(row.get("temporal_evidence")) == label for row in unique_accela)
            for label in ("prospective_snapshot", "retrospective_source_record", "retrospective_event_history", "unknown")
        },
        "temporal_boundary": "2026-08-01",
        "policy": [
            "Deduplicate Accela stable IDs, then canonical public record numbers.",
            "Merge only a single exact public record-number match into a core activity.",
            "Hold ambiguous exact matches for review; never fuzzy-auto-merge.",
            "Assign deterministic activity IDs to unmatched records and fail on final duplicate IDs/numbers.",
        ],
        "scope_note": "Local integrated edition; the eight-layer ArcGIS bounded-census files and claims are unchanged.",
        "identity_note": (
            "activity_id is the row key. Existing core source_record_id values can repeat across source namespaces "
            "or placeholder IDs and are not auto-merged without stronger identity evidence."
        ),
    }
    return integrated, sorted(audit, key=lambda row: (row.get("record_number", ""), row.get("accela_record_id", ""))), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-activity", type=Path, default=CORE_ACTIVITY)
    parser.add_argument("--core-sources", type=Path, default=CORE_SOURCES)
    parser.add_argument("--accela", type=Path, default=ACCELA_RECORDS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    core = read_csv(args.core_activity)
    sources = read_csv(args.core_sources)
    accela = read_csv(args.accela)
    if not core or not accela:
        parser.error("core activity and Accela inputs must both contain rows")
    integrated, audit, report = integrate(core, sources, accela)
    output_fields = list(core[0]) + [field for field in TEMPORAL_FIELDS if field not in core[0]]
    write_csv(args.output, integrated, output_fields)
    write_csv(args.audit, audit, AUDIT_FIELDS)
    write_json(args.report, report)
    print(json.dumps({**report, "output": str(args.output), "audit": str(args.audit), "report": str(args.report)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
