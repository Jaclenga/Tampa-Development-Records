#!/usr/bin/env python3
"""Validate identity, provenance, and cohort linkage for Accela inspections."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tampa_accela.models import INSPECTION_FIELDS


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspections", type=Path, default=ROOT / "data" / "processed" / "accela_inspections.csv")
    parser.add_argument("--records", type=Path, default=ROOT / "data" / "processed" / "accela_records.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "processed" / "accela_inspection_validation.json")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)

    errors: list[str] = []
    inspection_rows = rows(args.inspections) if args.inspections.exists() else []
    record_rows = rows(args.records)
    if inspection_rows and list(inspection_rows[0]) != INSPECTION_FIELDS:
        errors.append("inspection CSV schema/order does not match INSPECTION_FIELDS")
    ids = [row.get("inspection_id", "") for row in inspection_rows]
    record_ids = {row.get("record_id", "") for row in record_rows}
    if any(not value for value in ids):
        errors.append("blank inspection_id")
    if len(ids) != len(set(ids)):
        errors.append("duplicate inspection_id")
    if any(not row.get("record_id") for row in inspection_rows):
        errors.append("blank record_id")
    if unknown := sorted({row.get("record_id", "") for row in inspection_rows} - record_ids):
        errors.append(f"inspection rows link to {len(unknown)} unknown record IDs")
    if any(not row.get("source_inspection_id") and not row.get("inspection_type") for row in inspection_rows):
        errors.append("layout-like inspection row without source ID or type")
    allowed = {"retrospective_event_history", "prospective_snapshot", "unknown"}
    if invalid := sorted({row.get("temporal_evidence", "") for row in inspection_rows} - allowed):
        errors.append(f"invalid temporal_evidence values: {invalid}")

    checkpoints = sorted((ROOT / "data" / "processed" / "accela_checkpoints").glob("*-inspection-backfill-*.json"))
    complete = 0
    incomplete = []
    attempted_records: set[str] = set()
    for path in checkpoints:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            incomplete.append(path.name)
            continue
        attempted_records.update(value.get("completed_record_ids", []))
        if value.get("complete"):
            complete += 1
        else:
            incomplete.append(path.name)
    if args.require_complete and incomplete:
        errors.append(f"{len(incomplete)} inspection checkpoints are incomplete")

    report = {
        "inspection_rows": len(inspection_rows),
        "unique_inspection_ids": len(set(ids)),
        "records_with_inspections": len({row.get("record_id") for row in inspection_rows}),
        "records_attempted_for_inspections": len(attempted_records),
        "complete_checkpoint_runs": complete,
        "incomplete_checkpoint_runs": incomplete,
        "duplicate_inspection_ids": len(ids) - len(set(ids)),
        "errors": errors,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
