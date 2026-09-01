#!/usr/bin/env python3
"""Collect one completed Accela day and freeze it with the core source snapshot."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
COLLECTOR = ROOT / "scripts" / "collect_accela.py"
TRACKER = ROOT / "scripts" / "snapshot_tracker.py"
MODULES = ("Building", "Planning")


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from exc


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def repository_relative_text(value: str) -> str:
    """Remove this checkout's absolute root from serialized provenance paths."""
    result = value
    for root in {str(ROOT), ROOT.as_posix()}:
        result = result.replace(root + "\\", "").replace(root + "/", "")
        if result == root:
            result = "."
    return result.replace("\\", "/") if result != value else result


def sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return repository_relative_text(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_value(item) for key, item in value.items()}
    return value


def sanitize_csv(path: Path) -> None:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [
            {field: repository_relative_text(row.get(field, "")) for field in fields}
            for row in reader
        ]
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def sanitize_freeze_files(directory: Path) -> None:
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() == ".csv":
            sanitize_csv(path)
        elif path.suffix.lower() == ".json" and path.name not in {"manifest.json", "status.json"}:
            value = json.loads(path.read_text(encoding="utf-8"))
            atomic_json(path, sanitize_value(value))


def verify_existing_freeze(directory: Path, manifest: dict[str, object]) -> None:
    for item in manifest.get("files", []):
        relative_path = str(item["path"])
        path = directory / relative_path
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise RuntimeError(f"Frozen file is missing or changed: {relative_path}")


def run(command: list[str], log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8", newline="\n") as log:
        log.write(json.dumps({"command": command}) + "\n")
        log.flush()
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"Command failed with exit {result.returncode}: {command}")


def run_with_retries(command: list[str], log_path: Path, attempts: int = 3) -> None:
    for attempt in range(1, attempts + 1):
        try:
            run(command, log_path)
            return
        except RuntimeError:
            if attempt == attempts:
                raise
            with log_path.open("a", encoding="utf-8", newline="\n") as log:
                log.write(json.dumps({
                    "status": "retrying_command",
                    "attempt": attempt + 1,
                    "max_attempts": attempts,
                }) + "\n")
            time.sleep(10 * attempt)


def checkpoint_complete(output_dir: Path, module: str, run_id: str) -> bool:
    path = output_dir / "accela_checkpoints" / f"{module.lower()}-{run_id}.json"
    if not path.exists():
        return False
    value = json.loads(path.read_text(encoding="utf-8"))
    return bool(value.get("complete")) and not value.get("gaps")


def latest_core_snapshot() -> dict[str, object]:
    index_path = DATA / "monthly_changes" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    snapshots = index.get("snapshots", [])
    if not snapshots:
        raise RuntimeError("The core snapshot tracker did not publish a snapshot")
    return snapshots[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=parse_date)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    target: dt.date = args.date
    freeze_dir = DATA / "frozen" / "accela" / target.isoformat()
    output_dir = freeze_dir / "processed"
    raw_root = DATA / "raw" / "accela" / "month-end-freezes"
    log_path = freeze_dir / "collection.log"
    status_path = freeze_dir / "status.json"
    manifest_path = freeze_dir / "manifest.json"
    run_id = f"day-freeze-{target.isoformat()}"

    commands = [
        [
            sys.executable,
            str(COLLECTOR),
            "--module",
            module,
            "--from-date",
            target.isoformat(),
            "--to-date",
            target.isoformat(),
            "--run-id",
            run_id,
            "--resume",
            "--use-export",
            "--output-dir",
            str(output_dir),
            "--raw-root",
            str(raw_root),
        ]
        for module in MODULES
    ]
    commands.append([sys.executable, str(TRACKER), "collect-live"])

    if args.dry_run:
        print(json.dumps({
            "target_date": target.isoformat(),
            "freeze_directory": str(freeze_dir),
            "commands": commands,
        }, indent=2))
        return 0

    freeze_dir.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_existing_freeze(freeze_dir, manifest)
        atomic_json(status_path, {
            "status": "already_frozen",
            "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "manifest": str(manifest_path),
        })
        return 0

    atomic_json(status_path, {
        "status": "collecting",
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_date": target.isoformat(),
    })
    try:
        for module, command in zip(MODULES, commands[:len(MODULES)], strict=True):
            if checkpoint_complete(output_dir, module, run_id):
                continue
            run(command, log_path)
            if not checkpoint_complete(output_dir, module, run_id):
                raise RuntimeError(f"{module} checkpoint is incomplete or contains collection gaps")

        sanitize_freeze_files(freeze_dir)

        atomic_json(status_path, {
            "status": "freezing_core_snapshot",
            "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "target_date": target.isoformat(),
        })
        run_with_retries(commands[-1], log_path)

        excluded = {manifest_path.resolve(), status_path.resolve(), log_path.resolve()}
        files = [
            {
                "path": path.relative_to(freeze_dir).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(freeze_dir.rglob("*"))
            if path.is_file() and path.resolve() not in excluded
        ]
        if not files:
            raise RuntimeError("No Accela files were available to freeze")
        manifest = {
            "format_version": "1.0.0",
            "frozen_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "accela_query": {
                "from_date": target.isoformat(),
                "to_date": target.isoformat(),
                "modules": list(MODULES),
                "mode": "public_download_results_export",
            },
            "core_snapshot": latest_core_snapshot(),
            "immutability_rule": "A completed manifest is never overwritten; every listed file must retain its recorded SHA-256 hash.",
            "files": files,
        }
        atomic_json(manifest_path, manifest)
        atomic_json(status_path, {
            "status": "complete",
            "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "manifest": manifest_path.name,
            "frozen_file_count": len(files),
            "core_snapshot_date": manifest["core_snapshot"]["snapshot_date"],
        })
    except Exception as exc:
        atomic_json(status_path, {
            "status": "failed",
            "failed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "error": str(exc),
        })
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
