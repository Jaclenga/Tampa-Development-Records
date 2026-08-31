"""Atomic, deterministic outputs for Accela collection runs."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterable, Mapping, Sequence

from .csv_safety import restore_csv_row, safe_csv_row
from .models import (
    INSPECTION_FIELDS,
    NORMALIZED_FIELDS,
    CollectionResult,
    Inspection,
    NormalizedRecord,
    temporalize_inspection_row,
    temporalize_row,
)
from .normalize import stable_inspection_id


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
        output.writerows(safe_csv_row(row) for row in materialized)

    _atomic_write(path, render)


def write_json(path: Path, value: object) -> None:
    _atomic_write(path, lambda handle: json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [restore_csv_row(row) for row in csv.DictReader(handle)]


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


def _number_key(value: object) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _canonicalize_inspection(
    row: Mapping[str, object], record_id_by_number: Mapping[str, str]
) -> dict[str, object]:
    result = dict(row)
    canonical = record_id_by_number.get(_number_key(result.get("record_number")))
    if canonical:
        result["record_id"] = canonical
        result["inspection_id"] = stable_inspection_id(
            canonical,
            source_identifier=result.get("source_inspection_id"),
            inspection_type=result.get("inspection_type"),
            scheduled_date=result.get("scheduled_date"),
            completed_date=result.get("completed_date"),
            result_date=result.get("result_date"),
        )
    return result


def upsert_inspections(
    path: Path,
    inspections: Iterable[Inspection],
    *,
    record_id_by_number: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    canonical_ids = record_id_by_number or {}
    by_id: dict[str, dict[str, object]] = {
        canonical["inspection_id"]: temporalize_inspection_row(canonical)
        for row in _read_csv(path)
        if (
            canonical := _canonicalize_inspection(row, canonical_ids)
        ).get("inspection_id")
        and canonical.get("record_id")
        and (canonical.get("source_inspection_id") or canonical.get("inspection_type"))
    }
    for inspection in inspections:
        if inspection.inspection_id:
            row = _canonicalize_inspection(inspection.as_row(), canonical_ids)
            inspection_id = str(row["inspection_id"])
            old = by_id.get(inspection_id, {})
            merged = {
                field: row.get(field) if row.get(field) not in {None, ""} else old.get(field)
                for field in INSPECTION_FIELDS
            }
            first = [str(value) for value in (old.get("first_observed_date"), row.get("first_observed_date")) if value]
            last = [str(value) for value in (old.get("last_observed_date"), row.get("last_observed_date")) if value]
            if first:
                merged["first_observed_date"] = min(first)
            if last:
                merged["last_observed_date"] = max(last)
            by_id[inspection_id] = temporalize_inspection_row(merged)
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
        ids_by_number = {
            _number_key(row.get("record_number")): str(row["record_id"])
            for row in all_rows if row.get("record_number") and row.get("record_id")
        }
        upsert_inspections(
            inspection_path,
            result.inspections,
            record_id_by_number=ids_by_number,
        )
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
