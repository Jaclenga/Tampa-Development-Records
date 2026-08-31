#!/usr/bin/env python3
"""Run reproducible monthly Tampa Accela backfills through the public CSV export."""

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
    parser.add_argument("--modules", nargs="+", default=["Building", "Planning"], choices=["Building", "Planning"])
    parser.add_argument("--force", action="store_true", help="Rerun checkpoints already marked complete")
    args = parser.parse_args(argv)
    if args.from_month > args.to_month:
        parser.error("--from-month must be on or before --to-month")

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
            ]
            print(json.dumps({"module": module, "month": f"{start:%Y-%m}", "status": "starting"}), flush=True)
            result = subprocess.run(command, cwd=ROOT, check=False)
            if result.returncode:
                print(json.dumps({
                    "module": module, "month": f"{start:%Y-%m}",
                    "status": "failed", "exit_code": result.returncode,
                }), flush=True)
                return result.returncode
            completed += 1
            print(json.dumps({"module": module, "month": f"{start:%Y-%m}", "status": "complete"}), flush=True)
    print(json.dumps({"completed_runs": completed, "skipped_complete_runs": skipped}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
