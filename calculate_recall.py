#!/usr/bin/env python3
"""Measure dataset recall against a sampled official permit denominator."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def wilson(found: int, total: int) -> tuple[float, float]:
    z = 1.959963984540054
    p = found / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0, center - margin), min(1, center + margin)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path, help="CSV with permit_id, permit_category, and period")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/recall_estimates.csv")
    args = parser.parse_args()
    if not args.sample.exists():
        raise SystemExit(f"Sample not found: {args.sample}")
    with args.sample.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"permit_id", "permit_category", "period"}
    if not rows or not required.issubset(rows[0]):
        raise SystemExit("The official sample must be nonempty and contain permit_id, permit_category, period")
    with (ROOT / "data/processed/source_records.csv").open(encoding="utf-8", newline="") as handle:
        known = {r["source_record_id"].strip().upper() for r in csv.DictReader(handle) if r["source_record_id"].strip()}
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["period"], row["permit_category"])].append(row)
    output = []
    for (period, category), items in sorted(groups.items()):
        found = sum(r["permit_id"].strip().upper() in known for r in items)
        low, high = wilson(found, len(items))
        output.append({"period": period, "permit_category": category, "sample_n": len(items),
                       "found_in_dataset": found, "recall_estimate": round(found / len(items), 6),
                       "recall_95ci_lower": round(low, 6), "recall_95ci_upper": round(high, 6)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader(); writer.writerows(output)
    print(f"Wrote {len(output)} strata to {args.output}")


if __name__ == "__main__":
    main()
