#!/usr/bin/env python3
"""Durable, resumable acquisition, independent of report generation and tests.

Recovery branches contain only scrubbed source records and integrity receipts.
They are append-only application checkpoints, not validated dataset releases.
"""
from __future__ import annotations

import argparse
import calendar
from collections import Counter
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from zoneinfo import ZoneInfo

try:
    from . import build_release, snapshot_tracker as tracker
except ImportError:
    import build_release
    import snapshot_tracker as tracker

ROOT = Path(__file__).resolve().parents[1]
TAMPA = ZoneInfo("America/New_York")


def endpoints() -> dict[str, str]:
    legacy = build_release.load_legacy_module()
    return {
        **{name: cfg["url"] for name, cfg in legacy.SOURCES.items()},
        **{name: url for name, (url, _) in build_release.EXTRA_CIP.items()},
    }


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def date_value(value: str) -> str:
    if dt.date.fromisoformat(value).isoformat() != value:
        raise ValueError("Observation date must be YYYY-MM-DD")
    return value


def plan(event: str, requested: str = "", now: dt.datetime | None = None,
         first_required: str = "") -> dict:
    today = (now or utcnow()).astimezone(TAMPA).date()
    if requested:
        target = dt.date.fromisoformat(date_value(requested))
        if target > today:
            raise ValueError("Cannot collect or recover a future observation")
    elif event == "workflow_dispatch" or today.day == calendar.monthrange(today.year, today.month)[1]:
        target = today
    elif today.day <= 2:
        target = today.replace(day=1) - dt.timedelta(days=1)
    else:
        return {"should_run": "false", "target_date": "", "allow_live": "false"}
    if event == "schedule" and first_required and target < dt.date.fromisoformat(first_required):
        return {"should_run": "false", "target_date": target.isoformat(), "allow_live": "false"}
    return {
        "should_run": "true", "target_date": target.isoformat(),
        "allow_live": str(target == today).lower(),
    }


class GitArchive:
    """Append files without checking out a branch or touching the working index.

    Every successful write is fetched back from the remote and verified. A
    rejected or ambiguous push is reconciled before retrying; never force-push.
    """

    def __init__(self, date: str, root: Path = ROOT, remote: str = "origin"):
        self.root, self.remote = root, remote
        self.branch = f"snapshot-captures/{date_value(date)}"
        self.ref = f"refs/remotes/{remote}/{self.branch}"
        self.refresh()

    def git(self, *args: str, data: bytes | None = None, env: dict | None = None,
            check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args], input=data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, **(env or {})}, timeout=180,
        )
        if check and result.returncode:
            # Do not echo remote URLs, credentials, or machine paths.
            raise RuntimeError(f"Git archive operation failed: {args[0]} (exit {result.returncode})")
        return result

    def refresh(self) -> None:
        remote_ref = f"refs/heads/{self.branch}"
        listing = self.git("ls-remote", "--heads", self.remote, remote_ref).stdout
        if listing.strip():
            self.git("fetch", "--no-tags", self.remote, f"+{remote_ref}:{self.ref}")
            self.head = self.git("rev-parse", self.ref).stdout.decode().strip()
        else:
            self.head = None

    def read(self, name: str) -> bytes | None:
        if not self.head:
            return None
        result = self.git("show", f"{self.head}:{name}", check=False)
        return result.stdout if result.returncode == 0 else None

    def put(self, files: dict[str, bytes]) -> None:
        if any(not re.fullmatch(r"[a-zA-Z0-9_./-]+", name) or ".." in name for name in files):
            raise ValueError("Invalid checkpoint path")
        for attempt in range(3):
            self.refresh()
            missing = {}
            for name, content in files.items():
                existing = self.read(name)
                if existing is not None and existing != content:
                    raise RuntimeError(f"Refusing to replace immutable checkpoint: {name}")
                if existing is None:
                    missing[name] = content
            if not missing:
                return
            directory = self.root / ".cache"
            directory.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="capture-index-", dir=directory) as temp:
                env = {
                    "GIT_INDEX_FILE": str(Path(temp) / "index"),
                    "GIT_AUTHOR_NAME": "github-actions[bot]",
                    "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                    "GIT_COMMITTER_NAME": "github-actions[bot]",
                    "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                }
                self.git("read-tree", *([self.head] if self.head else ["--empty"]), env=env)
                for name, content in missing.items():
                    blob = self.git("hash-object", "-w", "--stdin", data=content).stdout.decode().strip()
                    self.git("update-index", "--add", "--cacheinfo", f"100644,{blob},{name}", env=env)
                tree = self.git("write-tree", env=env).stdout.decode().strip()
                commit = self.git(
                    "commit-tree", tree, *(["-p", self.head] if self.head else []),
                    data=f"archive: checkpoint {self.branch}\n".encode(), env=env,
                ).stdout.decode().strip()
                try:
                    self.git("push", self.remote, f"{commit}:refs/heads/{self.branch}", check=False)
                except subprocess.TimeoutExpired:
                    # A timeout does not tell us whether the server accepted it.
                    pass
            self.refresh()
            if all(self.read(name) == content for name, content in files.items()):
                return
            if attempt < 2:
                time.sleep(2 ** attempt)
        raise RuntimeError("Checkpoint could not be verified on the remote; backup remains local")


def encoded(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def save_backup(backup: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        path = backup / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def make_source(source: str, endpoint: str, collection: dict, observed: dt.datetime) -> dict:
    integrity = collection.get("collection_integrity", {})
    if not integrity.get("passed") or not collection.get("features"):
        raise RuntimeError(f"Unreconciled or empty source: {source}")
    rows = []
    for feature in collection["features"]:
        props = feature.get("properties") or {}
        rows.append({
            "source_name": source,
            "source_record_id": tracker.clean(build_release.native_id_for(source, props)),
            "source_object_id": tracker.clean(props.get("OBJECTID")),
            "source_global_id": tracker.clean(props.get("GlobalID")),
            "source_endpoint": endpoint,
            "retrieved_at_utc": observed.isoformat(),
            "properties_json": json.dumps(build_release.scrub_properties(props), ensure_ascii=False, separators=(",", ":")),
        })
    return {
        "format_version": 1, "source": source, "endpoint": endpoint,
        "retrieved_at_utc": observed.isoformat(), "integrity": integrity,
        "rows_sha256": tracker.rows_sha256(rows), "rows": rows,
    }


def verify_source(payload: dict, source: str, endpoint: str, date: str) -> list[dict]:
    rows = payload["rows"]
    observed = dt.datetime.fromisoformat(payload["retrieved_at_utc"])
    if observed.tzinfo is None or observed.astimezone(TAMPA).date().isoformat() != date:
        raise RuntimeError(f"Checkpoint was not observed on {date}: {source}")
    integrity = payload["integrity"]
    counts = [integrity.get(k) for k in ("count_only", "id_only", "paginated_feature_count", "final_count_only")]
    if (payload.get("format_version") != 1 or payload["source"] != source
            or payload["endpoint"] != endpoint or not rows or not integrity.get("passed")
            or any(count != len(rows) for count in counts)
            or payload["rows_sha256"] != tracker.rows_sha256(rows)):
        raise RuntimeError(f"Invalid source checkpoint: {source}")
    for row in rows:
        if (set(row) != set(tracker.SNAPSHOT_FIELDS) or row["source_name"] != source
                or row["source_endpoint"] != endpoint or row["retrieved_at_utc"] != observed.isoformat()):
            raise RuntimeError(f"Invalid checkpoint row: {source}")
        props = json.loads(row["properties_json"])
        if props != build_release.scrub_properties(props):
            raise RuntimeError(f"Checkpoint violates the source privacy policy: {source}")
    ids = [r["source_object_id"] for r in rows]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise RuntimeError(f"Checkpoint has missing or duplicate object IDs: {source}")
    return rows


def validate_snapshot(files: dict[str, bytes], date: str) -> dict:
    meta = json.loads(files["complete/metadata.json"])
    if meta["snapshot_date"] != date or meta["source_count"] != 8 or meta["record_count"] < 3000:
        raise RuntimeError("Invalid complete snapshot metadata")
    if hashlib.sha256(files["complete/source_records.csv.gz"]).hexdigest() != meta["source_records_gzip_sha256"]:
        raise RuntimeError("Complete snapshot checksum mismatch")
    rows = tracker.canonical_snapshot_rows(list(csv.DictReader(io.StringIO(
        gzip.decompress(files["complete/source_records.csv.gz"]).decode("utf-8"), newline="",
    ))))
    counts = dict(sorted(Counter(row["source_name"] for row in rows).items()))
    if (len(rows) != meta["record_count"] or counts != meta["source_counts"]
            or set(counts) != set(endpoints())
            or tracker.snapshot_date_from_rows(rows)[0] != date
            or tracker.rows_sha256(rows) != meta["source_records_content_sha256"]
            or tracker.source_state_sha256(rows) != meta["source_state_sha256"]):
        raise RuntimeError("Complete snapshot content does not match its metadata")
    return meta


def capture(date: str, store: GitArchive, backup: Path, *, allow_live: bool,
            now=utcnow, fetch=build_release.fetch_arcgis_layer) -> dict:
    date_value(date)
    configured = endpoints()
    if len(configured) != 8:
        raise RuntimeError("Expected exactly eight sources")
    rows, receipts = [], {}
    for source, endpoint in configured.items():
        name = f"sources/{source}.json"
        content = store.read(name)
        if content is None:
            if not allow_live or now().astimezone(TAMPA).date().isoformat() != date:
                raise RuntimeError(f"No checkpoint for {source} on {date}; cannot reconstruct a past observation")
            started = now()
            collection = fetch(endpoint, return_geometry=False)
            observed = now()
            if started.astimezone(TAMPA).date() != observed.astimezone(TAMPA).date():
                raise RuntimeError(f"Source collection crossed Tampa midnight: {source}")
            payload = make_source(source, endpoint, collection, observed)
            verify_source(payload, source, endpoint, date)
            content = encoded(payload)
            # Save locally before networking, so artifact upload remains possible
            # when a Git push fails. Never advance to another source without a
            # verified remote checkpoint for the previous one.
            save_backup(backup, {name: content})
            store.put({name: content})
        payload = json.loads(content)
        source_rows = verify_source(payload, source, endpoint, date)
        save_backup(backup, {name: content})
        rows.extend(source_rows)
        receipts[source] = {
            "retrieved_at_utc": payload["retrieved_at_utc"],
            "checkpoint_sha256": hashlib.sha256(content).hexdigest(),
            "collection_integrity": payload["integrity"],
        }
        print(f"Verified durable checkpoint: {source} ({len(source_rows)} records)", flush=True)
    if len(rows) < 3000:
        raise RuntimeError("Complete snapshot failed record-count safeguard")
    # The compact snapshot uses the final source retrieval time. Per-source
    # times remain in the receipts and checkpoint rows; all must share a day.
    completed = max(dt.datetime.fromisoformat(row["retrieved_at_utc"]) for row in rows).astimezone(dt.timezone.utc).isoformat()
    combined = [{**row, "retrieved_at_utc": completed} for row in rows]
    expected_receipt = {"snapshot_date": date, "sources": receipts}
    complete_names = ("complete/metadata.json", "complete/source_records.csv.gz", "complete/receipt.json")
    saved = {name: store.read(name) for name in complete_names}
    if any(content is not None for content in saved.values()):
        if any(content is None for content in saved.values()):
            raise RuntimeError("Incomplete immutable snapshot bundle")
        metadata = validate_snapshot(saved, date)
        if (metadata["source_records_content_sha256"] != tracker.rows_sha256(tracker.canonical_snapshot_rows(combined))
                or json.loads(saved["complete/receipt.json"]) != expected_receipt):
            raise RuntimeError("Complete snapshot differs from its source checkpoints")
        # Restore the original bytes: future gzip/library changes must not
        # require regeneration or rewriting a valid historical capture.
        save_backup(backup, saved)
        return metadata
    backup.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="assemble-", dir=backup) as temp:
        archive = Path(temp)
        metadata = tracker.archive_rows(combined, archive)
        directory = archive / date
        metadata.update({
            "audit_status": "inventory_reconciled",
            "collection_integrity_passed": True,
            "collection_receipt": "collection_receipt.json",
            "first_source_retrieved_at_utc": min(
                dt.datetime.fromisoformat(item["retrieved_at_utc"]) for item in receipts.values()
            ).astimezone(dt.timezone.utc).isoformat(),
        })
        tracker.atomic_json(directory / "metadata.json", metadata)
        files = {
            "complete/metadata.json": (directory / "metadata.json").read_bytes(),
            "complete/source_records.csv.gz": (directory / "source_records.csv.gz").read_bytes(),
            "complete/receipt.json": encoded(expected_receipt),
        }
    validate_snapshot(files, date)
    save_backup(backup, files)
    store.put(files)
    return metadata


def restore(date: str, store: GitArchive, destination: Path) -> dict:
    """Rebuild solely from eight verified durable checkpoints, never live data."""
    (ROOT / ".cache").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="restore-", dir=ROOT / ".cache") as temp:
        meta = capture(date, store, Path(temp), allow_live=False)
        directory = destination / date
        for name in ("source_records.csv.gz", "metadata.json", "receipt.json"):
            content = store.read(f"complete/{name}")
            target = directory / ("collection_receipt.json" if name == "receipt.json" else name)
            if target.exists() and target.read_bytes() != content:
                raise RuntimeError(f"Refusing to overwrite existing snapshot: {date}/{name}")
        directory.mkdir(parents=True, exist_ok=True)
        for name in ("source_records.csv.gz", "metadata.json"):
            (directory / name).write_bytes(store.read(f"complete/{name}"))
        # Receipt documents per-source times without changing legacy metadata.
        (directory / "collection_receipt.json").write_bytes(store.read("complete/receipt.json"))
        return meta


def verify_published(root: Path, date: str) -> dict:
    directory = root / "data" / "snapshots" / date_value(date)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    path = directory / "source_records.csv.gz"
    rows = tracker.canonical_snapshot_rows(tracker.read_csv(path))
    counts = dict(sorted(Counter(r["source_name"] for r in rows).items()))
    if (metadata["snapshot_date"] != date or metadata["record_count"] != len(rows)
            or metadata["source_counts"] != counts or metadata["source_count"] != 8
            or set(counts) != set(endpoints())
            or metadata["source_records_gzip_sha256"] != tracker.file_sha256(path)
            or metadata["source_records_content_sha256"] != tracker.rows_sha256(rows)
            or metadata["source_state_sha256"] != tracker.source_state_sha256(rows)):
        raise RuntimeError(f"Published snapshot failed integrity checks: {date}")
    return metadata


def watchdog(root: Path = ROOT, now: dt.datetime | None = None) -> str:
    today = (now or utcnow()).astimezone(TAMPA).date()
    expected = today.replace(day=1) - dt.timedelta(days=1)
    config = json.loads((root / "config" / "snapshot_pipeline.json").read_text(encoding="utf-8"))
    first_required = dt.date.fromisoformat(config["first_required_month_end"])
    if expected < first_required:
        return f"Monitoring starts with {first_required}; historical gaps remain documented."
    verify_published(root, expected.isoformat())
    return f"Published month-end verified: {expected}"


def output(values: dict) -> None:
    print(json.dumps(values, indent=2))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            for key, value in values.items():
                if isinstance(value, (str, int)):
                    handle.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    gate = commands.add_parser("plan")
    gate.add_argument("--event", required=True)
    gate.add_argument("--date", default="")
    for command in ("capture", "restore", "import-backup"):
        command_parser = commands.add_parser(command)
        command_parser.add_argument("--date", required=True)
        command_parser.add_argument("--directory", type=Path, required=True)
        if command == "capture":
            command_parser.add_argument("--allow-live", action="store_true")
    commands.add_parser("watchdog")
    args = parser.parse_args()
    if args.command == "plan":
        config = json.loads((ROOT / "config" / "snapshot_pipeline.json").read_text(encoding="utf-8"))
        decision = plan(args.event, args.date, first_required=config["first_required_month_end"])
        if decision["should_run"] == "true":
            published = ROOT / "data" / "snapshots" / decision["target_date"] / "metadata.json"
            if published.is_file():
                verify_published(ROOT, decision["target_date"])
                decision["should_run"] = "false"
        output(decision)
        return
    if args.command == "watchdog":
        print(watchdog())
        return
    store = GitArchive(args.date)
    if args.command == "capture":
        output(capture(args.date, store, args.directory, allow_live=args.allow_live))
    elif args.command == "restore":
        (ROOT / ".cache").mkdir(exist_ok=True)
        output(restore(args.date, store, args.directory))
    else:
        # Artifacts are treated as data, never executable code. Validate all
        # source payloads before importing any of them into the archive branch.
        files = {}
        for source, endpoint in endpoints().items():
            name = f"sources/{source}.json"
            path = args.directory / name
            if path.is_file():
                content = path.read_bytes()
                verify_source(json.loads(content), source, endpoint, args.date)
                files[name] = content
        if not files:
            raise RuntimeError("No valid source checkpoints found in backup")
        store.put(files)
        print(f"Imported {len(files)} verified source checkpoints")


if __name__ == "__main__":
    main()
