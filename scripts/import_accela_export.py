#!/usr/bin/env python3
"""Stage a City-provided Accela CSV/JSON/NDJSON export without guessing fields."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALIASES = {
    "permit_id": ["permit_id", "record_id", "recordid", "alt_id", "cap_id"],
    "record_type": ["record_type", "type", "permit_type"],
    "status": ["status", "record_status", "cap_status"],
    "parcel_folio": ["parcel_folio", "folio", "parcel_number"],
    "site_address": ["site_address", "address", "full_address"],
    "declared_valuation": ["declared_valuation", "valuation", "job_value", "estimated_cost"],
    "parent_record_id": ["parent_record_id", "parent_id", "parent_cap_id"],
    "related_record_id": ["related_record_id", "related_id", "child_record_id"],
    "application_date": ["application_date", "opened_date", "filed_date"],
    "issued_date": ["issued_date", "issue_date", "permit_issued_date"],
    "expiration_date": ["expiration_date", "expired_date", "permit_expiration_date"],
    "closed_date": ["closed_date", "close_date", "permit_closed_date"],
    "finaled_date": ["finaled_date", "final_date", "permit_finaled_date"],
    "temporary_co_date": ["temporary_co_date", "tco_date", "temporary_certificate_date"],
    "certificate_of_occupancy_date": ["certificate_of_occupancy_date", "co_date", "occupancy_date"],
    "inspection_id": ["inspection_id", "inspection_number"],
    "inspection_type": ["inspection_type", "inspection_name"],
    "inspection_date": ["inspection_date", "inspection_completed_date"],
    "inspection_result": ["inspection_result", "inspection_status", "result"],
    "final_inspection_indicator": ["final_inspection_indicator", "is_final_inspection", "final_indicator"],
}

EVENT_COLUMNS = [
    "staged_event_id", "source_record_id", "related_record_id", "event_type",
    "event_date_raw", "event_source_field", "event_value", "evidence_strength",
    "is_inferred", "interpretation_warning",
]


def event_id(record_id: str, event_type: str, event_date: str, value: str) -> str:
    seed = "|".join((record_id, event_type, event_date, value))
    return "stg-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def staged_events(rows: list[dict]) -> list[dict]:
    """Create lifecycle candidates only from explicit delivered fields."""
    out = []
    specs = (
        ("application_filed", "application_date", "Administrative filing date; not approval or construction."),
        ("permit_issued", "issued_date", "Permit issuance does not establish physical work."),
        ("permit_expired", "expiration_date", "Expiration date does not establish whether work occurred."),
        ("permit_closed", "closed_date", "Administrative closure is not necessarily physical completion."),
        ("construction_completion_reported", "finaled_date", "Finaled date is source-reported and requires field-definition review."),
        ("temporary_co_issued", "temporary_co_date", "Temporary occupancy is not permanent certificate of occupancy."),
        ("certificate_of_occupancy_issued", "certificate_of_occupancy_date", "Explicit certificate date; retain source certificate identifiers when supplied."),
    )
    for row in rows:
        record_id = str(row.get("permit_id") or "").strip()
        related = str(row.get("related_record_id") or "").strip()
        for event_type, field, warning in specs:
            value = str(row.get(field) or "").strip()
            if not value:
                continue
            out.append({
                "staged_event_id": event_id(record_id, event_type, value, value),
                "source_record_id": record_id, "related_record_id": related,
                "event_type": event_type, "event_date_raw": value,
                "event_source_field": field, "event_value": value,
                "evidence_strength": "official_lifecycle_record", "is_inferred": "no",
                "interpretation_warning": warning,
            })
        inspection_date = str(row.get("inspection_date") or "").strip()
        inspection_result = str(row.get("inspection_result") or "").strip()
        inspection_type = str(row.get("inspection_type") or "").strip()
        final_indicator = str(row.get("final_inspection_indicator") or "").strip().lower()
        if inspection_date and inspection_result:
            passed = any(token in inspection_result.lower() for token in ("pass", "approved", "complete"))
            event_type = "inspection_passed" if passed else "inspection_failed"
            if passed and (final_indicator in {"yes", "y", "true", "1"} or "final" in inspection_type.lower()):
                event_type = "final_inspection_passed"
            out.append({
                "staged_event_id": event_id(record_id, event_type, inspection_date, inspection_result),
                "source_record_id": record_id, "related_record_id": related,
                "event_type": event_type, "event_date_raw": inspection_date,
                "event_source_field": "inspection_type;inspection_date;inspection_result;final_inspection_indicator",
                "event_value": "; ".join(value for value in (inspection_type, inspection_result) if value),
                "evidence_strength": "official_lifecycle_record", "is_inferred": "no",
                "interpretation_warning": "Inspection result is staged from explicit fields and must be linked to the correct permit before release.",
            })
    return out


def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix.lower() in {".ndjson", ".jsonl"}:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("records", data.get("features", []))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/staging/accela_records.csv")
    args = parser.parse_args()
    rows = read_rows(args.export)
    if not rows:
        raise SystemExit("Export is empty")
    lowered = {str(k).lower(): k for k in rows[0]}
    mapping = {target: next((lowered[a] for a in aliases if a in lowered), "") for target, aliases in ALIASES.items()}
    if not mapping["permit_id"]:
        raise SystemExit("No permit/record identifier found; supply a machine-readable export with a stable ID")
    normalized = []
    for row in rows:
        normalized.append({target: row.get(source, "") if source else "" for target, source in mapping.items()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ALIASES))
        writer.writeheader(); writer.writerows(normalized)
    events = staged_events(normalized)
    events_path = args.output.with_name(args.output.stem + "_lifecycle_events.csv")
    with events_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_COLUMNS, lineterminator="\n")
        writer.writeheader(); writer.writerows(events)
    report = {"input_rows": len(rows), "staged_lifecycle_events": len(events),
              "field_mapping": mapping, "lifecycle_events_output": str(events_path),
              "warning": "Only explicit delivered lifecycle fields are staged. Absent inspections, certificates, relationships, or dates are never inferred."}
    args.output.with_suffix(".report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
