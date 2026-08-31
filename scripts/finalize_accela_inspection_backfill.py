#!/usr/bin/env python3
"""Wait for the inspection collector, then validate and rebuild linked outputs."""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
STATUS = PROCESSED / "accela_inspection_backfill_status.json"


def months(start: dt.date, end: dt.date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor = dt.date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)


def expected_checkpoints(start: dt.date, end: dt.date) -> list[Path]:
    return [
        PROCESSED / "accela_checkpoints" / f"{module}-inspection-backfill-{month:%Y-%m}.json"
        for module in ("planning", "building")
        for month in months(start, end)
    ]


def is_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("complete"))
    except (OSError, json.JSONDecodeError):
        return False


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_status(status: str, paths: list[Path], **extra: object) -> None:
    complete = [path.name for path in paths if is_complete(path)]
    value = {
        "status": status,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "complete_checkpoint_runs": len(complete),
        "expected_checkpoint_runs": len(paths),
        "complete_checkpoints": complete,
        **extra,
    }
    STATUS.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(value, sort_keys=True), flush=True)


def run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed with exit {result.returncode}: {command}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collector-pid", required=True, type=int)
    parser.add_argument("--from-month", default="2025-08")
    parser.add_argument("--to-month", default="2026-08")
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    start = dt.date.fromisoformat(args.from_month + "-01")
    end = dt.date.fromisoformat(args.to_month + "-01")
    paths = expected_checkpoints(start, end)

    write_status("collecting", paths, collector_pid=args.collector_pid)
    while not all(is_complete(path) for path in paths):
        if not process_exists(args.collector_pid):
            write_status(
                "incomplete",
                paths,
                collector_pid=args.collector_pid,
                message="Collector exited before every expected checkpoint was complete.",
            )
            return 2
        time.sleep(args.poll_seconds)
        write_status("collecting", paths, collector_pid=args.collector_pid)

    try:
        run([sys.executable, str(ROOT / "scripts" / "validate_accela_inspections.py"), "--require-complete"])
        run([sys.executable, str(ROOT / "scripts" / "integrate_accela.py")])
        run([
            sys.executable,
            str(ROOT / "scripts" / "import_accela_export.py"),
            str(PROCESSED / "accela_inspections.csv"),
            "--output",
            str(ROOT / "data" / "staging" / "accela_inspections.csv"),
        ])
    except RuntimeError as exc:
        write_status("finalization_failed", paths, collector_pid=args.collector_pid, message=str(exc))
        return 2
    write_status("complete", paths, collector_pid=args.collector_pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
