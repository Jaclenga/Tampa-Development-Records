#!/usr/bin/env python3
"""Validate list-only monthly partitions and merge them into Accela aggregates."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tampa_accela.output import merge_snapshot_records


SNAPSHOTS = ROOT / "data" / "processed" / "accela_snapshots"


def month(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM") from exc


def months(start: dt.date, end: dt.date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor = dt.date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-month", required=True, type=month)
    parser.add_argument("--to-month", required=True, type=month)
    parser.add_argument("--modules", nargs="+", default=["Building", "Planning"])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "processed")
    args = parser.parse_args(argv)
    if args.from_month > args.to_month:
        parser.error("--from-month must be on or before --to-month")

    snapshot_paths: list[Path] = []
    errors: list[str] = []
    for module in args.modules:
        for cursor in months(args.from_month, args.to_month):
            stem = SNAPSHOTS / f"backfill-{cursor:%Y-%m}-{module.lower()}"
            snapshot = stem.with_suffix(".csv")
            gaps = Path(f"{stem}-gaps.json")
            summary = Path(f"{stem}-summary.json")
            missing = [str(path) for path in (snapshot, gaps, summary) if not path.exists()]
            if missing:
                errors.append(f"missing outputs for {module} {cursor:%Y-%m}: {', '.join(missing)}")
                continue
            try:
                gap_rows = json.loads(gaps.read_text(encoding="utf-8"))
                summary_value = json.loads(summary.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"invalid metadata for {module} {cursor:%Y-%m}: {exc}")
                continue
            if gap_rows or summary_value.get("truncated"):
                errors.append(f"incomplete outputs for {module} {cursor:%Y-%m}")
                continue
            snapshot_paths.append(snapshot)

    if errors:
        print(json.dumps({"merged": False, "errors": errors}, indent=2))
        return 1
    report = merge_snapshot_records(args.output_dir, snapshot_paths)
    report.update({
        "merged": True,
        "from_month": f"{args.from_month:%Y-%m}",
        "to_month": f"{args.to_month:%Y-%m}",
        "modules_requested": args.modules,
    })
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
