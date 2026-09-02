#!/usr/bin/env python3
"""Run reproducible monthly Tampa Accela backfills through the public CSV export."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "scripts" / "collect_accela.py"
FINALIZER = ROOT / "scripts" / "finalize_accela_record_backfill.py"
OUTPUT_DIR = ROOT / "data" / "processed"
DATASET_START_MONTH = dt.date(2020, 1, 1)


def month(value: str) -> dt.date:
    try:
        parsed = dt.date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM") from exc
    return parsed


def windows(start: dt.date, end: dt.date):
    cursor = start
    while cursor <= end:
        following = dt.date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        yield cursor, following - dt.timedelta(days=1)
        cursor = following


def checkpoint_complete(module: str, run_id: str) -> bool:
    path = OUTPUT_DIR / "accela_checkpoints" / f"{module.lower()}-{run_id}.json"
    snapshot_base = OUTPUT_DIR / "accela_snapshots" / f"{run_id}-{module.lower()}"
    required_outputs = (
        snapshot_base.with_suffix(".csv"),
        Path(f"{snapshot_base}-gaps.json"),
        Path(f"{snapshot_base}-summary.json"),
    )
    if not path.exists() or not all(output.exists() for output in required_outputs):
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8"))["complete"])
    except (KeyError, json.JSONDecodeError, OSError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-month", required=True, type=month)
    parser.add_argument("--to-month", required=True, type=month)
    parser.add_argument("--modules", nargs="+", default=["Building", "Planning"], choices=["Building", "Planning"])
    parser.add_argument("--force", action="store_true", help="Rerun checkpoints already marked complete")
    parser.add_argument(
        "--month-attempts", type=int, default=4,
        help="Attempts per monthly partition after request-level retries are exhausted",
    )
    parser.add_argument(
        "--month-retry-delay", type=float, default=15.0,
        help="Seconds to wait between monthly partition attempts",
    )
    args = parser.parse_args(argv)
    if args.from_month > args.to_month:
        parser.error("--from-month must be on or before --to-month")
    if args.from_month < DATASET_START_MONTH:
        parser.error(
            f"--from-month cannot be before the dataset boundary "
            f"({DATASET_START_MONTH:%Y-%m})"
        )
    if args.month_attempts < 1:
        parser.error("--month-attempts must be positive")
    if args.month_retry_delay < 0:
        parser.error("--month-retry-delay cannot be negative")

    completed = skipped = 0
    for module in args.modules:
        for start, end in windows(args.from_month, args.to_month):
            run_id = f"backfill-{start:%Y-%m}"
            if not args.force and checkpoint_complete(module, run_id):
                skipped += 1
                print(json.dumps({"module": module, "month": f"{start:%Y-%m}", "status": "skipped_complete"}), flush=True)
                continue
            command = [
                sys.executable, str(COLLECTOR), "--module", module,
                "--from-date", start.isoformat(), "--to-date", end.isoformat(),
                "--run-id", run_id, "--resume", "--use-export",
                "--snapshot-only",
            ]
            result = None
            for attempt in range(1, args.month_attempts + 1):
                print(json.dumps({
                    "module": module,
                    "month": f"{start:%Y-%m}",
                    "status": "starting",
                    "attempt": attempt,
                    "max_attempts": args.month_attempts,
                }), flush=True)
                result = subprocess.run(command, cwd=ROOT, check=False)
                if result.returncode == 0:
                    break
                if attempt < args.month_attempts:
                    print(json.dumps({
                        "module": module,
                        "month": f"{start:%Y-%m}",
                        "status": "retrying_month",
                        "exit_code": result.returncode,
                        "delay_seconds": args.month_retry_delay,
                    }), flush=True)
                    time.sleep(args.month_retry_delay)
            if result is None or result.returncode:
                print(json.dumps({
                    "module": module, "month": f"{start:%Y-%m}",
                    "status": "failed", "exit_code": result.returncode if result else None,
                    "attempts": args.month_attempts,
                }), flush=True)
                return result.returncode if result else 1
            completed += 1
            print(json.dumps({"module": module, "month": f"{start:%Y-%m}", "status": "complete"}), flush=True)
    finalizer = [
        sys.executable, str(FINALIZER),
        "--from-month", f"{args.from_month:%Y-%m}",
        "--to-month", f"{args.to_month:%Y-%m}",
        "--modules", *args.modules,
    ]
    print(json.dumps({"status": "finalizing_aggregate"}), flush=True)
    result = subprocess.run(finalizer, cwd=ROOT, check=False)
    if result.returncode:
        print(json.dumps({"status": "aggregate_failed", "exit_code": result.returncode}), flush=True)
        return result.returncode
    print(json.dumps({
        "completed_runs": completed,
        "skipped_complete_runs": skipped,
        "aggregate_finalized": True,
    }), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
