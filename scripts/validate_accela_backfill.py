#!/usr/bin/env python3
"""Validate monthly Accela backfill snapshots and publish a compact audit report."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "data" / "processed" / "accela_snapshots"
AGGREGATE = ROOT / "data" / "processed" / "accela_records.csv"
REPORT = ROOT / "data" / "integrated" / "accela_backfill_report.json"
TEMPORAL_BOUNDARY = dt.date(2026, 8, 1)
REQUIRED_TEMPORAL_FIELDS = {
    "event_date", "event_date_type", "first_observed_date", "snapshot_date",
    "last_observed_date", "historical_reconstruction", "temporal_evidence",
}


def month(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM") from exc


def windows(start: dt.date, end: dt.date):
    cursor = start
    while cursor <= end:
        following = dt.date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        yield cursor, following - dt.timedelta(days=1)
        cursor = following


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def canonical_number(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-month", type=month, default=month("2025-08"))
    parser.add_argument("--to-month", type=month, default=month("2026-07"))
    parser.add_argument("--modules", nargs="+", default=["Building", "Planning"])
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    errors: list[str] = []
    month_rows: list[dict[str, object]] = []
    snapshot_total = 0

    for module in args.modules:
        for start, end in windows(args.from_month, args.to_month):
            run_id = f"backfill-{start:%Y-%m}-{module.lower()}"
            csv_path = SNAPSHOTS / f"{run_id}.csv"
            summary_path = SNAPSHOTS / f"{run_id}-summary.json"
            gaps_path = SNAPSHOTS / f"{run_id}-gaps.json"
            if not all(path.exists() for path in (csv_path, summary_path, gaps_path)):
                errors.append(f"missing output for {module} {start:%Y-%m}")
                continue
            rows = read_csv(csv_path)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
            if rows and not REQUIRED_TEMPORAL_FIELDS.issubset(rows[0]):
                errors.append(f"missing temporal fields for {module} {start:%Y-%m}")
            if len(rows) != int(summary["records"]):
                errors.append(f"summary count mismatch for {module} {start:%Y-%m}")
            if gaps or summary.get("truncated"):
                errors.append(f"incomplete collection for {module} {start:%Y-%m}")
            numbers = [canonical_number(row.get("record_number", "")) for row in rows]
            if not all(numbers) or len(numbers) != len(set(numbers)):
                errors.append(f"missing or duplicate record number for {module} {start:%Y-%m}")
            for row in rows:
                try:
                    event = dt.date.fromisoformat(row["event_date"])
                except (KeyError, ValueError):
                    errors.append(f"invalid event date for {module} {start:%Y-%m}")
                    continue
                if not start <= event <= end:
                    errors.append(f"event outside query window for {module} {start:%Y-%m}")
                expected = "retrospective_source_record" if event < TEMPORAL_BOUNDARY else "prospective_snapshot"
                if row.get("temporal_evidence") != expected:
                    errors.append(f"temporal classification mismatch for {module} {start:%Y-%m}")
            snapshot_total += len(rows)
            month_rows.append({
                "module": module, "month": f"{start:%Y-%m}", "records": len(rows),
                "gap_count": len(gaps), "truncated": bool(summary.get("truncated")),
            })

    aggregate = read_csv(AGGREGATE)
    stable_ids = [row.get("record_id", "") for row in aggregate]
    public_numbers = [canonical_number(row.get("record_number", "")) for row in aggregate]
    if not all(stable_ids) or len(stable_ids) != len(set(stable_ids)):
        errors.append("aggregate has missing or duplicate stable IDs")
    if not all(public_numbers) or len(public_numbers) != len(set(public_numbers)):
        errors.append("aggregate has missing or duplicate canonical public record numbers")
    end_date = next(windows(args.to_month, args.to_month))[1]
    cohort = [
        row for row in aggregate
        if row.get("source_module") in args.modules
        and row.get("event_date")
        and args.from_month <= dt.date.fromisoformat(row["event_date"]) <= end_date
    ]
    if len(cohort) != snapshot_total:
        errors.append(f"aggregate cohort count {len(cohort)} does not equal snapshot total {snapshot_total}")

    evidence_counts = {
        label: sum(row.get("temporal_evidence") == label for row in aggregate)
        for label in ("prospective_snapshot", "retrospective_source_record", "retrospective_event_history", "unknown")
    }
    report = {
        "format_version": "1.0.0",
        "passed": not errors,
        "errors": errors,
        "backfill_window": {"from": args.from_month.isoformat(), "to": end_date.isoformat()},
        "modules": args.modules,
        "monthly_runs": len(month_rows),
        "backfill_records": snapshot_total,
        "backfill_records_by_module": {
            module: sum(int(row["records"]) for row in month_rows if row["module"] == module)
            for module in args.modules
        },
        "month_counts": month_rows,
        "gap_runs": sum(bool(row["gap_count"]) for row in month_rows),
        "truncated_runs": sum(bool(row["truncated"]) for row in month_rows),
        "aggregate_records": len(aggregate),
        "aggregate_stable_ids_unique": len(stable_ids) == len(set(stable_ids)),
        "aggregate_public_record_numbers_unique": len(public_numbers) == len(set(public_numbers)),
        "temporal_boundary": TEMPORAL_BOUNDARY.isoformat(),
        "temporal_evidence_counts": evidence_counts,
        "interpretation": (
            "Pre-boundary rows are retrospective source records retrieved during current collection, "
            "not contemporaneous historical snapshots."
        ),
    }
    atomic_json(args.report, report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
