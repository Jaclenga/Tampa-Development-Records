#!/usr/bin/env python3
"""Collect all public inspection observations for monthly Accela cohorts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "scripts" / "collect_accela.py"
OUTPUT_DIR = ROOT / "data" / "processed"
DATASET_START_MONTH = dt.date(2020, 1, 1)


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


def checkpoint_path(module: str, run_id: str) -> Path:
    return OUTPUT_DIR / "accela_checkpoints" / f"{module.lower()}-{run_id}.json"


def checkpoint_complete(module: str, run_id: str) -> bool:
    path = checkpoint_path(module, run_id)
    if not path.exists():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8"))["complete"])
    except (KeyError, json.JSONDecodeError, OSError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-month", required=True, type=month)
    parser.add_argument("--to-month", required=True, type=month)
    parser.add_argument(
        "--modules", nargs="+", default=["Planning", "Building"],
        choices=["Planning", "Building"],
    )
    parser.add_argument("--requests-per-second", type=float, default=1.0)
    parser.add_argument(
        "--run-retries", type=int, default=3,
        help="Retry an incomplete monthly checkpoint this many times",
    )
    parser.add_argument("--force", action="store_true", help="Rerun checkpoints already marked complete")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.from_month > args.to_month:
        parser.error("--from-month must be on or before --to-month")
    if args.from_month < DATASET_START_MONTH:
        parser.error(
            f"--from-month cannot be before the dataset boundary "
            f"({DATASET_START_MONTH:%Y-%m})"
        )
    if not 0 < args.requests_per_second <= 1:
        parser.error("--requests-per-second must be greater than zero and no more than one")
    if args.run_retries < 1:
        parser.error("--run-retries must be positive")

    completed = skipped = 0
    for module in args.modules:
        for start, end in windows(args.from_month, args.to_month):
            run_id = f"inspection-backfill-{start:%Y-%m}"
            if not args.force and checkpoint_complete(module, run_id):
                skipped += 1
                print(json.dumps({"module": module, "month": f"{start:%Y-%m}", "status": "skipped_complete"}), flush=True)
                continue
            command = [
                sys.executable, str(COLLECTOR), "--module", module,
                "--from-date", start.isoformat(), "--to-date", end.isoformat(),
                "--run-id", run_id, "--resume", "--include-inspections", "--compress-raw",
                "--requests-per-second", str(args.requests_per_second),
                "--checkpoint-every", "25",
            ]
            print(json.dumps({"module": module, "month": f"{start:%Y-%m}", "status": "starting"}), flush=True)
            if args.dry_run:
                print(json.dumps({"command": command}), flush=True)
                continue
            result = None
            for attempt in range(1, args.run_retries + 1):
                result = subprocess.run(command, cwd=ROOT, check=False)
                if result.returncode == 0 and checkpoint_complete(module, run_id):
                    break
                print(json.dumps({
                    "module": module, "month": f"{start:%Y-%m}",
                    "status": "retrying_incomplete", "attempt": attempt,
                    "max_attempts": args.run_retries,
                }), flush=True)
            assert result is not None
            if result.returncode or not checkpoint_complete(module, run_id):
                print(json.dumps({
                    "module": module, "month": f"{start:%Y-%m}", "status": "incomplete",
                    "exit_code": result.returncode,
                    "checkpoint": str(checkpoint_path(module, run_id)),
                }), flush=True)
                return result.returncode or 2
            completed += 1
            print(json.dumps({"module": module, "month": f"{start:%Y-%m}", "status": "complete"}), flush=True)
    print(json.dumps({"completed_runs": completed, "skipped_complete_runs": skipped}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
