"""Atomic, deterministic outputs for Accela collection runs."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterable, Mapping, Sequence

from .models import (
    INSPECTION_FIELDS,
    NORMALIZED_FIELDS,
    CollectionResult,
    Inspection,
    NormalizedRecord,
    temporalize_row,
)


def _atomic_write(path: Path, writer) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer(handle)
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


def write_csv(path: Path, rows: Iterable[Mapping[str, object]], fields: Sequence[str]) -> None:
    materialized = list(rows)

    def render(handle) -> None:
        output = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        output.writeheader()
        output.writerows({key: "" if value is None else value for key, value in row.items()} for row in materialized)

    _atomic_write(path, render)


def write_json(path: Path, value: object) -> None:
    _atomic_write(path, lambda handle: json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _public_number_key(row: Mapping[str, object]) -> tuple[str, str] | None:
    module = str(row.get("source_module") or "").strip().upper()
    number = "".join(character for character in str(row.get("record_number") or "").upper() if character.isalnum())
    return (module, number) if module and number else None


def upsert_records(path: Path, records: Iterable[NormalizedRecord]) -> list[dict[str, object]]:
    """Upsert the latest observation by stable ID without deleting older IDs."""
    existing_rows = [temporalize_row(row) for row in _read_csv(path) if row.get("record_id")]
    by_id: dict[str, dict[str, object]] = {str(row["record_id"]): row for row in existing_rows}
    id_by_number = {
        key: str(row["record_id"])
        for row in existing_rows
        if (key := _public_number_key(row)) is not None
    }
    for record in records:
        if not record.record_id:
            continue
        key = _public_number_key(record.as_row())
        target_id = id_by_number.get(key, record.record_id) if key else record.record_id
        old = by_id.get(target_id, {})
        row = temporalize_row(record.as_row())
        row["record_id"] = target_id
        merged = {
            field: row.get(field) if row.get(field) not in {None, ""} else old.get(field)
            for field in NORMALIZED_FIELDS
        }
        observed = [
            str(value) for value in (old.get("first_observed_date"), row.get("first_observed_date")) if value
        ]
        if observed:
            merged["first_observed_date"] = min(observed)
        observed = [
            str(value) for value in (old.get("last_observed_date"), row.get("last_observed_date")) if value
        ]
        if observed:
            merged["last_observed_date"] = max(observed)
        by_id[target_id] = temporalize_row(merged)
        if key:
            id_by_number[key] = target_id
    rows = [by_id[key] for key in sorted(by_id)]
    write_csv(path, rows, NORMALIZED_FIELDS)
    return rows


def upsert_inspections(path: Path, inspections: Iterable[Inspection]) -> list[dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {
        row["inspection_id"]: dict(row) for row in _read_csv(path) if row.get("inspection_id")
    }
    for inspection in inspections:
        if inspection.inspection_id:
            by_id[inspection.inspection_id] = inspection.as_row()
    rows = [by_id[key] for key in sorted(by_id)]
    write_csv(path, rows, INSPECTION_FIELDS)
    return rows


def write_collection_outputs(
    output_dir: Path,
    result: CollectionResult,
    *,
    module: str,
    run_id: str,
    query: Mapping[str, object],
) -> dict[str, str]:
    snapshots = output_dir / "accela_snapshots"
    snapshot = snapshots / f"{run_id}-{module.lower()}.csv"
    write_csv(snapshot, (record.as_row() for record in result.records), NORMALIZED_FIELDS)
    current = output_dir / "accela_records.csv"
    all_rows = upsert_records(current, result.records)
    module_path = output_dir / f"accela_{module.lower()}_records.csv"
    write_csv(module_path, (row for row in all_rows if row.get("source_module") == module), NORMALIZED_FIELDS)
    inspection_path = output_dir / "accela_inspections.csv"
    if result.inspections or inspection_path.exists():
        upsert_inspections(inspection_path, result.inspections)
    gaps_path = snapshots / f"{run_id}-{module.lower()}-gaps.json"
    summary_path = snapshots / f"{run_id}-{module.lower()}-summary.json"
    write_json(gaps_path, result.gaps)
    write_json(
        summary_path,
        {
            "run_id": run_id,
            "module": module,
            "query": dict(query),
            "records": len(result.records),
            "inspections": len(result.inspections),
            "pages": result.pages,
            "requests": result.requests,
            "truncated": result.truncated,
            "gap_count": len(result.gaps),
            "checkpoint_path": result.checkpoint_path,
            "output_format": "CSV (Parquet is not emitted because this repository does not require a Parquet engine)",
        },
    )
    return {
        "snapshot": str(snapshot),
        "current": str(current),
        "module": str(module_path),
        "inspections": str(inspection_path),
        "gaps": str(gaps_path),
        "summary": str(summary_path),
    }
