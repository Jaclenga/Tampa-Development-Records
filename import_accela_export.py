#!/usr/bin/env python3
"""Stage a City-provided Accela CSV/JSON/NDJSON export without guessing fields."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALIASES = {
    "permit_id": ["permit_id", "record_id", "recordid", "alt_id", "cap_id"],
    "record_type": ["record_type", "type", "permit_type"],
    "status": ["status", "record_status", "cap_status"],
    "parcel_folio": ["parcel_folio", "folio", "parcel_number"],
    "site_address": ["site_address", "address", "full_address"],
    "declared_valuation": ["declared_valuation", "valuation", "job_value", "estimated_cost"],
}


def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix.lower() in {".ndjson", ".jsonl"}:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("records", data.get("features", []))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/staging/accela_records.csv")
    args = parser.parse_args()
    rows = read_rows(args.export)
    if not rows:
        raise SystemExit("Export is empty")
    lowered = {str(k).lower(): k for k in rows[0]}
    mapping = {target: next((lowered[a] for a in aliases if a in lowered), "") for target, aliases in ALIASES.items()}
    if not mapping["permit_id"]:
        raise SystemExit("No permit/record identifier found; supply a machine-readable export with a stable ID")
    normalized = []
    for row in rows:
        normalized.append({target: row.get(source, "") if source else "" for target, source in mapping.items()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ALIASES))
        writer.writeheader(); writer.writerows(normalized)
    report = {"input_rows": len(rows), "field_mapping": mapping,
              "warning": "This staging import does not infer inspections, COs, relationships, or completion from absent fields."}
    args.output.with_suffix(".report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
