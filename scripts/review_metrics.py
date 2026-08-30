#!/usr/bin/env python3
"""Report claim-specific validation estimates and inter-reviewer agreement.

The default is the untouched holdout phase. Population estimates are withheld
until every assigned first and second review in the requested phase is marked
complete and passes the evidence-provenance checks.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .validation_study import CLAIM_RESULT_FIELDS, PROTOCOL_VERSION
except ImportError:  # Support direct execution: python scripts/review_metrics.py
    from validation_study import CLAIM_RESULT_FIELDS, PROTOCOL_VERSION


ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "processed"
ALLOWED_RESULTS = {"supported", "contradicted", "inconclusive", "not_applicable"}
ALLOWED_PHYSICAL = {"present", "absent", "unknown", "not_applicable"}
REQUIRED_COMPLETION_FIELDS = (
    *CLAIM_RESULT_FIELDS,
    "physical_work_evidence",
    "evidence_source_types",
    "evidence_accessed_at_utc",
    "ai_assistance_used",
    "manual_evidence_confirmed",
    "reviewer_id",
    "reviewed_at_utc",
    "review_notes",
)


def rows(name: str) -> list[dict[str, str]]:
    with (P / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def wilson(successes: float, total: float, z: float = 1.959963984540054) -> dict | None:
    if total <= 0:
        return None
    estimate = successes / total
    denominator = 1 + z * z / total
    center = (estimate + z * z / (2 * total)) / denominator
    half = z * math.sqrt(estimate * (1 - estimate) / total + z * z / (4 * total * total)) / denominator
    return {
        "estimate": estimate,
        "lower": max(0.0, center - half),
        "upper": min(1.0, center + half),
        "method": "Wilson score 95% interval",
    }


def is_complete(row: dict[str, str]) -> bool:
    if row.get("review_status") != "complete":
        return False
    if any(not row.get(field, "").strip() for field in REQUIRED_COMPLETION_FIELDS):
        return False
    if any(row[field] not in ALLOWED_RESULTS for field in CLAIM_RESULT_FIELDS):
        return False
    if row["physical_work_evidence"] not in ALLOWED_PHYSICAL:
        return False
    if row["ai_assistance_used"] not in {"yes", "no"}:
        return False
    if row["manual_evidence_confirmed"] != "yes":
        return False
    if row["activity_classification_result"] in {"supported", "contradicted"} and not row.get("reviewed_activity_class", "").strip():
        return False
    if row["status_interpretation_result"] in {"supported", "contradicted"} and not row.get("reviewed_activity_stage", "").strip():
        return False
    if row["sampling_stratum"] == "cross_source_merge":
        if row["cross_source_linkage_result"] == "not_applicable":
            return False
    elif row["cross_source_linkage_result"] != "not_applicable":
        return False
    has_building_match = bool(row.get("match_methods", "").strip())
    if has_building_match == (row["building_footprint_match_result"] == "not_applicable"):
        return False
    # A document reference can stand in for a URL. Failure to locate either is
    # never affirmative evidence that physical work did not occur.
    if not row.get("primary_evidence_url", "").strip() and not row.get("evidence_document_reference", "").strip():
        return False
    return True


def claim_metric(sample: list[dict[str, str]], field: str) -> dict:
    decisive = [row for row in sample if row[field] in {"supported", "contradicted"}]
    supported = sum(row[field] == "supported" for row in decisive)
    by_stratum = {}
    for stratum in sorted({row["sampling_stratum"] for row in sample}):
        group = [row for row in decisive if row["sampling_stratum"] == stratum]
        successes = sum(row[field] == "supported" for row in group)
        by_stratum[stratum] = {
            "supported": successes,
            "contradicted": len(group) - successes,
            "inconclusive": sum(
                row[field] == "inconclusive" for row in sample if row["sampling_stratum"] == stratum
            ),
            "not_applicable": sum(
                row[field] == "not_applicable" for row in sample if row["sampling_stratum"] == stratum
            ),
            "precision_95_ci": wilson(successes, len(group)),
        }

    weights = [float(row["sampling_weight"]) for row in decisive]
    weighted_supported = sum(
        weight for row, weight in zip(decisive, weights) if row[field] == "supported"
    )
    weight_total = sum(weights)
    weighted_estimate = weighted_supported / weight_total if weight_total else None
    effective_n = weight_total * weight_total / sum(w * w for w in weights) if weights else 0.0
    weighted_interval = wilson((weighted_estimate or 0.0) * effective_n, effective_n) if weighted_estimate is not None else None
    if weighted_interval:
        weighted_interval["method"] = "Approximate design-weighted Wilson 95% interval using Kish effective n"

    result = {
        "supported": supported,
        "contradicted": len(decisive) - supported,
        "inconclusive": sum(row[field] == "inconclusive" for row in sample),
        "not_applicable": sum(row[field] == "not_applicable" for row in sample),
        "unweighted_precision_95_ci": wilson(supported, len(decisive)),
        "design_weighted_precision_95_ci": weighted_interval,
        "kish_effective_n": effective_n,
        "by_stratum": by_stratum,
    }
    if field == "building_footprint_match_result":
        by_method = {}
        methods = sorted({method for row in sample for method in row.get("match_methods", "").split(";") if method})
        for method in methods:
            group = [
                row for row in decisive if method in row.get("match_methods", "").split(";")
            ]
            successes = sum(row[field] == "supported" for row in group)
            by_method[method] = {
                "supported": successes,
                "contradicted": len(group) - successes,
                "precision_95_ci": wilson(successes, len(group)),
            }
        result["by_match_method"] = by_method
    return result


def confusion_matrix(sample: list[dict[str, str]], predicted: str, reviewed: str) -> dict:
    counts: dict[str, Counter] = defaultdict(Counter)
    for row in sample:
        if row.get(reviewed, "").strip():
            counts[row[predicted]][row[reviewed]] += 1
    return {prediction: dict(sorted(values.items())) for prediction, values in sorted(counts.items())}


def kappa(pairs: list[tuple[str, str]]) -> dict:
    n = len(pairs)
    if not n:
        return {"n": 0, "percent_agreement": None, "cohens_kappa": None}
    labels = sorted({value for pair in pairs for value in pair})
    observed = sum(left == right for left, right in pairs) / n
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    expected = sum((left_counts[label] / n) * (right_counts[label] / n) for label in labels)
    value = (observed - expected) / (1 - expected) if expected < 1 else None
    return {"n": n, "percent_agreement": observed, "cohens_kappa": value, "labels": labels}


def agreement(first: list[dict[str, str]], second: list[dict[str, str]]) -> dict:
    first_by_id = {row["audit_sample_id"]: row for row in first}
    fields = (*CLAIM_RESULT_FIELDS, "physical_work_evidence", "reviewed_activity_class", "reviewed_activity_stage")
    report = {}
    for field in fields:
        pairs = []
        for row in second:
            original = first_by_id[row["audit_sample_id"]]
            left, right = original.get(field, ""), row.get(field, "")
            if not left or not right or "not_applicable" in {left, right}:
                continue
            if field in CLAIM_RESULT_FIELDS and "inconclusive" in {left, right}:
                continue
            pairs.append((left, right))
        report[field] = kappa(pairs)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("development", "holdout"), default="holdout")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Emit clearly labeled exploratory summaries before all assigned reviews are complete.",
    )
    parser.add_argument("--output", type=Path, help="JSON output path; defaults to docs/review_metrics_<phase>.json")
    args = parser.parse_args()

    first = rows(f"manual_validation_{args.phase}_sample.csv")
    second = [row for row in rows("manual_validation_second_review.csv") if row["sample_phase"] == args.phase]
    invalid_protocol = [row["audit_sample_id"] for row in first + second if row["protocol_version"] != PROTOCOL_VERSION]
    complete_first = [row for row in first if is_complete(row)]
    complete_second = [row for row in second if is_complete(row)]
    ready = not invalid_protocol and len(complete_first) == len(first) and len(complete_second) == len(second)

    report: dict = {
        "status": "estimable" if ready else "not_estimable",
        "analysis_type": "final_holdout" if args.phase == "holdout" else "development_debugging",
        "protocol_version": PROTOCOL_VERSION,
        "phase": args.phase,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "completion": {
            "first_reviews_complete": len(complete_first),
            "first_reviews_required": len(first),
            "second_reviews_complete": len(complete_second),
            "second_reviews_required": len(second),
            "invalid_protocol_rows": invalid_protocol,
        },
        "interpretation": "No population estimate is reported until all assigned reviews in this phase pass the frozen protocol checks.",
    }
    analysis_rows = complete_first if args.allow_partial and not ready else first if ready else []
    second_rows = complete_second if args.allow_partial and not ready else second if ready else []
    if analysis_rows:
        report["status"] = "exploratory_partial" if not ready else "estimable"
        report["claim_metrics"] = {
            field.removesuffix("_result"): claim_metric(analysis_rows, field)
            for field in CLAIM_RESULT_FIELDS
        }
        report["physical_work_evidence"] = {
            value: {
                "count": sum(row["physical_work_evidence"] == value for row in analysis_rows),
                "proportion_95_ci": wilson(
                    sum(row["physical_work_evidence"] == value for row in analysis_rows), len(analysis_rows)
                ),
            }
            for value in sorted(ALLOWED_PHYSICAL)
        }
        report["activity_class_confusion_matrix"] = confusion_matrix(
            analysis_rows, "activity_class", "reviewed_activity_class"
        )
        report["activity_stage_confusion_matrix"] = confusion_matrix(
            analysis_rows, "activity_stage", "reviewed_activity_stage"
        )
        report["inter_reviewer_agreement"] = agreement(analysis_rows, second_rows)
        report["interpretation"] = (
            "Exploratory partial results are not a population estimate and must not be used to tune rules and claim final performance."
            if not ready
            else "Claim types are reported separately. Inconclusive and not-applicable judgments are shown but excluded from precision denominators."
        )

    output = args.output or ROOT / "docs" / f"review_metrics_{args.phase}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not ready and not args.allow_partial:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
