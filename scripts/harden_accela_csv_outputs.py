#!/usr/bin/env python3
"""Re-serialize generated Accela CSVs with spreadsheet-safe literal cells."""

from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tampa_accela.csv_safety import restore_csv_row
from tampa_accela.output import write_csv


def generated_accela_csvs() -> list[Path]:
    processed = ROOT / "data" / "processed"
    integrated = ROOT / "data" / "integrated"
    candidates = set(processed.glob("accela*.csv"))
    candidates.update((processed / "accela_snapshots").glob("*.csv"))
    candidates.update(integrated.glob("*accela*.csv"))
    return sorted(path for path in candidates if path.is_file())


def harden(path: Path) -> tuple[int, int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        rows = [restore_csv_row(row) for row in reader]
    if not fields:
        raise ValueError(f"CSV has no header: {path}")
    write_csv(path, rows, fields)
    return len(rows), len(fields)


def main() -> int:
    paths = generated_accela_csvs()
    for path in paths:
        rows, fields = harden(path)
        print(f"hardened {path.relative_to(ROOT)} rows={rows} fields={fields}")
    print(f"complete files={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
