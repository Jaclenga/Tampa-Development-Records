#!/usr/bin/env python3
"""Calculate audit metrics only after required review fields are populated."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
P = ROOT / "data/processed"


def rows(name: str) -> list[dict]:
    with (P / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def kappa(pairs: list[tuple[str, str]]) -> dict:
    labels = sorted({v for pair in pairs for v in pair})
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum((left[x] / n) * (right[x] / n) for x in labels)
    value = (observed - expected) / (1 - expected) if expected < 1 else 1.0
    return {"n": n, "raw_agreement": observed, "cohens_kappa": value}


def main() -> None:
    first = {r["audit_sample_id"]: r for r in rows("manual_validation_sample.csv")}
    second = rows("manual_validation_second_review.csv")
    required = ("one_activity_one_development", "building_match_correct", "likely_realized_classification_correct", "reviewer_id", "reviewed_at_utc")
    completed_first = [r for r in first.values() if all(r[x] for x in required)]
    pairs = []
    for r in second:
        a = first[r["audit_sample_id"]]
        if a["one_activity_one_development"] and r["reviewer_2_one_activity_one_development"]:
            pairs.append((a["one_activity_one_development"], r["reviewer_2_one_activity_one_development"]))
    if len(completed_first) < 150 or len(pairs) < 30:
        raise SystemExit(json.dumps({"status": "not_estimable", "completed_first_reviews": len(completed_first),
            "completed_independent_pairs": len(pairs), "required_first_reviews": 150,
            "required_independent_pairs": 30, "warning": "No accuracy or agreement statistic was produced."}, indent=2))
    report = {"status": "estimable", "one_activity_one_development_agreement": kappa(pairs)}
    (ROOT / "docs/review_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
