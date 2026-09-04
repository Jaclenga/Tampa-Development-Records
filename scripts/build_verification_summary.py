#!/usr/bin/env python3
"""Build transparent, release-level verification coverage summaries.

This module intentionally reports verification layers separately.  It never
turns source fidelity, structural QA, or a partial review into a universal
``verified`` flag or a dataset-wide accuracy estimate.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

try:
    from . import review_metrics
except ImportError:  # Direct execution: python scripts/build_verification_summary.py
    import review_metrics


ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
VALIDATION_REPORTS = ROOT / "reports" / "validation"
OUTPUT_DIR = ROOT / "verification"
SUMMARY_COLUMNS = (
    "snapshot_date",
    "verification_type",
    "eligible_records",
    "evaluated_records",
    "passed_supported",
    "failed_conflicting",
    "unknown",
    "not_applicable",
    "partial_support",
    "awaiting_review",
    "second_review_count",
    "checks_evaluated",
    "checks_passed",
    "checks_flagged",
    "coverage_percentage",
    "status",
    "notes",
)


@dataclass(frozen=True)
class ReviewCounts:
    eligible: int
    evaluated: int
    supported: int
    conflicting: int
    unknown: int
    not_applicable: int
    partial: int
    awaiting: int


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def require_unique(rows: list[dict[str, str]], key: str, label: str) -> None:
    values = [row.get(key, "").strip() for row in rows]
    missing = sum(not value for value in values)
    duplicates = sorted(value for value, count in Counter(values).items() if value and count > 1)
    if missing or duplicates:
        raise ValueError(
            f"{label} must contain one nonblank {key} per row; "
            f"missing={missing}, duplicates={duplicates[:10]}"
        )


def summarize_reviews(
    rows: list[dict[str, str]],
    *,
    outcome_field: str | None = None,
    allowed_outcomes: set[str] | None = None,
    complete_predicate=None,
) -> ReviewCounts:
    """Count coverage and optional mutually exclusive outcomes.

    Manual-study rows have several claim-specific results, so callers omit
    ``outcome_field`` rather than manufacturing a record-level pass/fail label.
    """
    require_unique(rows, "audit_sample_id", "review rows")
    complete_predicate = complete_predicate or (
        lambda row: row.get("review_status", "").strip() == "complete"
    )
    complete = [row for row in rows if complete_predicate(row)]
    counts = Counter(row.get(outcome_field, "").strip() for row in complete) if outcome_field else Counter()
    if outcome_field:
        if allowed_outcomes is None:
            raise ValueError(f"allowed_outcomes is required when summarizing {outcome_field}")
        unexpected = sorted(set(counts) - allowed_outcomes)
        if unexpected:
            raise ValueError(f"Unexpected {outcome_field} values: {unexpected}")
    return ReviewCounts(
        eligible=len(rows),
        evaluated=len(complete),
        supported=counts["supported"] + counts["yes"],
        conflicting=counts["contradicted"] + counts["conflicting"] + counts["no"],
        unknown=counts["unknown"] + counts["inconclusive"] + counts["not_established"],
        not_applicable=counts["not_applicable"],
        partial=counts["partial"] + counts["partially_supported"],
        awaiting=len(rows) - len(complete),
    )


def coverage(evaluated: int, eligible: int) -> str:
    if eligible == 0:
        return "0.0"
    return f"{evaluated / eligible * 100:.1f}"


def row(snapshot: str, kind: str, counts: ReviewCounts, status: str, notes: str, **extra) -> dict:
    result = {
        "snapshot_date": snapshot,
        "verification_type": kind,
        "eligible_records": counts.eligible,
        "evaluated_records": counts.evaluated,
        "passed_supported": counts.supported,
        "failed_conflicting": counts.conflicting,
        "unknown": counts.unknown,
        "not_applicable": counts.not_applicable,
        "partial_support": counts.partial,
        "awaiting_review": counts.awaiting,
        "second_review_count": "",
        "checks_evaluated": "",
        "checks_passed": "",
        "checks_flagged": "",
        "coverage_percentage": coverage(counts.evaluated, counts.eligible),
        "status": status,
        "notes": notes,
    }
    result.update(extra)
    return result


def manual_study_row(
    snapshot: str, kind: str, counts: ReviewCounts, notes: str, **extra
) -> dict:
    result = row(
        snapshot,
        kind,
        counts,
        "complete" if counts.awaiting == 0 else "awaiting_review",
        notes,
        **extra,
    )
    if counts.evaluated == 0:
        for field in ("passed_supported", "failed_conflicting", "unknown", "not_applicable", "partial_support"):
            result[field] = ""
    return result


def not_measured_row(snapshot: str, kind: str, notes: str) -> dict:
    result = row(snapshot, kind, ReviewCounts(0, 0, 0, 0, 0, 0, 0, 0), "not_measured", notes)
    for field in (
        "eligible_records", "evaluated_records", "passed_supported", "failed_conflicting",
        "unknown", "not_applicable", "partial_support", "awaiting_review",
        "second_review_count", "coverage_percentage",
    ):
        result[field] = ""
    return result


def summarize_study(path: Path, outcome_field: str) -> ReviewCounts:
    adapted = [
        {
            **item,
            "audit_sample_id": item["validation_sample_id"],
            "outcome": item.get(outcome_field, ""),
        }
        for item in read_csv(path)
    ]
    return summarize_reviews(
        adapted,
        outcome_field="outcome",
        allowed_outcomes={"yes", "no", "unknown", "not_applicable"},
    )


def summarize_selected_plan(
    plan_path: Path, outcome_fields: dict[str, str]
) -> ReviewCounts:
    """Summarize only active v2 cases while retaining legacy source files."""
    selected = read_csv(plan_path)
    cache: dict[str, dict[str, dict[str, str]]] = {}
    adapted = []
    for item in selected:
        source_file = item["source_assignment_file"]
        if source_file not in outcome_fields:
            raise ValueError(f"No outcome mapping for active plan source: {source_file}")
        if source_file not in cache:
            source_rows = read_csv(ROOT / source_file)
            require_unique(source_rows, "validation_sample_id", source_file)
            cache[source_file] = {row["validation_sample_id"]: row for row in source_rows}
        identifier = item["source_validation_sample_id"]
        if identifier not in cache[source_file]:
            raise ValueError(f"Active plan case {identifier} is missing from {source_file}")
        source = cache[source_file][identifier]
        adapted.append({
            **source,
            "audit_sample_id": f"{source_file}:{identifier}",
            "outcome": source.get(outcome_fields[source_file], ""),
        })
    return summarize_reviews(
        adapted,
        outcome_field="outcome",
        allowed_outcomes={"yes", "no", "unknown", "not_applicable"},
    )


def summarize_expanded_second_reviews(paths: list[Path]) -> ReviewCounts:
    rows = []
    for path in paths:
        rows.extend({
            **item,
            "audit_sample_id": item["second_review_assignment_id"],
            "review_status": item.get("second_review_status", ""),
        } for item in read_csv(path))
    return summarize_reviews(rows)


def latest_snapshot_metadata(snapshot_root: Path, *, content_hash: str | None = None) -> dict:
    candidates = []
    for path in snapshot_root.glob("*/metadata.json"):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        snapshot_date = metadata.get("snapshot_date", "")
        try:
            parsed = dt.date.fromisoformat(snapshot_date)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid snapshot_date in {path}: {snapshot_date!r}") from error
        if path.parent.name != snapshot_date:
            raise ValueError(
                f"Snapshot directory/date mismatch: directory={path.parent.name}, metadata={snapshot_date}"
            )
        if content_hash is None or metadata.get("source_records_content_sha256") == content_hash:
            candidates.append((parsed, metadata))
    if not candidates:
        qualifier = f" matching source content hash {content_hash}" if content_hash else ""
        raise FileNotFoundError(f"No snapshot metadata{qualifier} found below {snapshot_root}")
    dates = [parsed for parsed, _ in candidates]
    if len(dates) != len(set(dates)):
        raise ValueError("Duplicate snapshot dates found")
    return max(candidates, key=lambda item: item[0])[1]


def load_manual_reviews(processed: Path) -> list[dict[str, str]]:
    phase_rows = []
    for phase in ("development", "holdout"):
        rows = read_csv(processed / f"manual_validation_{phase}_sample.csv")
        wrong_phase = [row.get("audit_sample_id", "") for row in rows if row.get("sample_phase") != phase]
        if wrong_phase:
            raise ValueError(f"{phase} review file contains rows from another phase: {wrong_phase[:10]}")
        phase_rows.extend(rows)
    require_unique(phase_rows, "audit_sample_id", "manual phase review files")
    combined = read_csv(processed / "manual_validation_sample.csv")
    require_unique(combined, "audit_sample_id", "combined manual sample")
    phase_ids = {row["audit_sample_id"] for row in phase_rows}
    combined_ids = {row["audit_sample_id"] for row in combined}
    if phase_ids != combined_ids:
        raise ValueError("Phase review files do not contain the same assignments as the combined sample")
    return phase_rows


def summarize_automated_qa(accuracy: dict) -> tuple[ReviewCounts, list[str], dict[str, int]]:
    source_count = int(accuracy["counts"]["source_records"])
    raw_count = int(accuracy["counts"]["raw_features"])
    checks = accuracy.get("checks", {})
    failed_checks = sorted(name for name, passed in checks.items() if passed is not True)
    mismatch_groups = sorted(
        name for name, value in accuracy.get("mismatch_counts", {}).items() if int(value)
    )
    issues = failed_checks + [f"mismatch:{name}" for name in mismatch_groups]
    if source_count != raw_count:
        issues.append("source_record_count_mismatch")
    counts = ReviewCounts(raw_count, raw_count, 0, 0, 0, 0, 0, 0)
    check_counts = {
        "evaluated": len(checks) + len(mismatch_groups) + int(source_count != raw_count),
        "passed": len(checks) - len(failed_checks),
        "flagged": len(issues),
    }
    return counts, issues, check_counts


def build_summary() -> list[dict]:
    accuracy = json.loads((VALIDATION_REPORTS / "accuracy_verification_report.json").read_text(encoding="utf-8"))
    try:
        from . import snapshot_tracker
    except ImportError:  # Direct execution.
        import snapshot_tracker
    current_source_rows = read_csv(PROCESSED / "source_records.csv")
    content_hash = snapshot_tracker.rows_sha256(
        snapshot_tracker.canonical_snapshot_rows(current_source_rows)
    )
    snapshot = latest_snapshot_metadata(ROOT / "data" / "snapshots", content_hash=content_hash)
    snapshot_date = snapshot["snapshot_date"]
    source_count = int(accuracy["counts"]["source_records"])
    raw_count = int(accuracy["counts"]["raw_features"])
    qa_counts, qa_issues, qa_check_counts = summarize_automated_qa(accuracy)
    qa_passed = not qa_issues

    manual = load_manual_reviews(PROCESSED)
    second = read_csv(PROCESSED / "manual_validation_core_reliability.csv")
    pilot = read_csv(PROCESSED / "external_verification_pilot.csv")
    require_unique(pilot, "verification_id", "external verification pilot")
    # Reuse the protocol's strict completion rule for both first and second review.
    manual_counts = summarize_reviews(manual, complete_predicate=review_metrics.is_complete)
    second_counts = summarize_reviews(second, complete_predicate=review_metrics.is_complete)
    pilot_rows = [dict(item, audit_sample_id=item["verification_id"], review_status="complete") for item in pilot]
    pilot_counts = summarize_reviews(
        pilot_rows,
        outcome_field="physical_realization_verified",
        allowed_outcomes={"yes", "no", "partial", "not_established", "unknown", "not_applicable"},
    )

    accela_counts = summarize_selected_plan(
        PROCESSED / "manual_validation_accela_audit_plan.csv",
        {
            "data/processed/manual_validation_accela_source_fidelity.csv": "source_fidelity_outcome",
            "data/processed/manual_validation_accela_normalization.csv": "normalization_outcome",
            "data/processed/manual_validation_integration_links.csv": "linkage_outcome",
        },
    )
    change_counts = summarize_selected_plan(
        PROCESSED / "manual_validation_longitudinal_initial_plan.csv",
        {"data/processed/manual_validation_change_events.csv": "change_validation_outcome"},
    )
    backfill = json.loads(
        (ROOT / "data" / "integrated" / "accela_backfill_report.json").read_text(encoding="utf-8")
    )
    backfill_runs = int(backfill.get("monthly_runs", 0))
    backfill_passed = bool(backfill.get("passed")) and not backfill.get("errors")
    collection_counts = ReviewCounts(
        backfill_runs,
        backfill_runs,
        backfill_runs if backfill_passed else 0,
        0 if backfill_passed else backfill_runs,
        0, 0, 0, 0,
    )

    trace_passed = source_count == raw_count and accuracy.get("source_snapshot_fidelity") == "verified"
    trace_counts = ReviewCounts(raw_count, raw_count, raw_count if trace_passed else 0,
                                0 if trace_passed else raw_count, 0, 0, 0, 0)
    rows = [
        row(snapshot_date, "automated_qa_core_release", qa_counts, "passed" if qa_passed else "flagged",
            "Record coverage is the bounded source census; results are check-level because some checks are release-wide."
            + (f" Flagged checks: {', '.join(qa_issues)}." if qa_issues else ""),
            passed_supported="", failed_conflicting="",
            checks_evaluated=qa_check_counts["evaluated"], checks_passed=qa_check_counts["passed"],
            checks_flagged=qa_check_counts["flagged"]),
        row(snapshot_date, "core_source_traceability", trace_counts, "passed" if trace_passed else "flagged",
            "Reconciles bundled City source features to retained source rows; establishes source fidelity, not real-world truth."),
        manual_study_row(snapshot_date, "core_eight_layer_manual_validation", manual_counts,
            "Frozen seeded stratified probability sample from the original core universe; partial development results are "
            "exploratory only and do not validate the Accela expansion or estimate population accuracy.",
            passed_supported="", failed_conflicting="", unknown="", not_applicable="", partial_support="",
            second_review_count=second_counts.evaluated),
        row(snapshot_date, "core_external_outcome_verification", pilot_counts, "historical_pilot",
            "Historical evidence-selected pilot; physical-realization outcomes are not a population estimate."),
        row(snapshot_date, "core_double_review", second_counts,
            "complete" if second_counts.awaiting == 0 else "in_progress",
            "Active plan-v2 independent blinded subset; 25 of the 50 frozen candidates are required.",
            passed_supported="", failed_conflicting="", unknown="", not_applicable="", partial_support="",
            second_review_count=second_counts.evaluated),
        row(snapshot_date, "accela_collection_integrity", collection_counts,
            "passed" if backfill_passed else "flagged",
            "Reconciles Accela module-month partitions, gap/truncation checks, and aggregate counts; this is not record-level accuracy."),
        manual_study_row(snapshot_date, "targeted_accela_manual_audit", accela_counts,
            "Risk-based 75-case portfolio spanning source-fidelity spot checks, normalization, and linkage; not a population accuracy sample."),
        manual_study_row(snapshot_date, "initial_longitudinal_change_audit", change_counts,
            "Plan-v2 subset of 20 high-impact changes and 10 controls; source-publication interpretation only."),
        not_measured_row(snapshot_date, "expanded_external_outcome_verification",
            "No probability-based external outcome study has yet been performed for the expanded Accela edition."),
    ]
    if (
        manual_counts.eligible != 150 or second_counts.eligible != 25
        or accela_counts.eligible != 75 or change_counts.eligible != 30
    ):
        raise ValueError(
            "Study denominators disagree with active plan: "
            f"manual={manual_counts.eligible}, second={second_counts.eligible}, "
            f"accela={accela_counts.eligible}, longitudinal={change_counts.eligible}"
        )
    return rows


def write_summary(rows: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / "verification_summary.csv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return output


def render_readme_scorecard(rows: list[dict]) -> str:
    by_type = {item["verification_type"]: item for item in rows}
    qa = by_type["automated_qa_core_release"]
    trace = by_type["core_source_traceability"]
    manual = by_type["core_eight_layer_manual_validation"]
    pilot = by_type["core_external_outcome_verification"]
    second = by_type["core_double_review"]
    collection = by_type["accela_collection_integrity"]
    accela = by_type["targeted_accela_manual_audit"]
    change = by_type["initial_longitudinal_change_audit"]
    outcome = by_type["expanded_external_outcome_verification"]

    def progress(item: dict) -> str:
        if item["eligible_records"] == "":
            return "Not measured"
        return f"{int(item['evaluated_records']):,} / {int(item['eligible_records']):,} ({item['coverage_percentage']}%)"

    def manual_result(item: dict) -> str:
        if item["evaluated_records"] == "" or int(item["evaluated_records"]) == 0:
            return "Not measured"
        if item["awaiting_review"] != "" and int(item["awaiting_review"]) > 0:
            return "Exploratory partial results only"
        return "See study-specific outcomes"

    qa_result = (
        f"{qa['checks_passed']} checks passed; {qa['checks_flagged']} checks flagged"
        if qa["checks_evaluated"] != ""
        else "Not measured"
    )
    return f"""Validation results apply only to the stated sampling universe and validation
layer. Source fidelity, transformation validity, and real-world outcome validity
are separate claims. No composite verification score is calculated.

### Core eight-layer verification

The frozen 150-row core sample was selected before the Accela expansion and has
not been redrawn from the expanded dataset.

| Validation layer | Coverage / progress | Result among evaluated | What it establishes |
| --- | ---: | --- | --- |
| Automated QA — core release | {progress(qa)} | {qa_result} | Structural and release-integrity checks |
| Core source traceability | {progress(trace)} | {int(trace['passed_supported']):,} reconciled; {int(trace['failed_conflicting']):,} conflicting | Fidelity to the eight archived City layers, not real-world outcomes |
| Core eight-layer manual validation | {progress(manual)} | {manual_result(manual)} | Claim-specific review of the original normalized/core universe only |
| Core external outcome verification | {pilot['evaluated_records']} / {pilot['eligible_records']} historical pilot rows | {pilot['passed_supported']} documented; {pilot['partial_support']} partial; {pilot['unknown']} not established; {pilot['not_applicable']} not applicable | Evidence-selected pilot, not a population estimate |
| Core reviewer reliability | {progress(second)} | {manual_result(second)} | Independent blinded review of the active 25-row subset |

### Expanded Accela verification

| Validation layer | Coverage / progress | Result among evaluated | What it establishes |
| --- | ---: | --- | --- |
| Accela collection integrity | {progress(collection)} | {collection['passed_supported']} module-month partitions passed | Retrieval completeness and reconciliation, not semantic or outcome accuracy |
| Targeted Accela manual audit | {progress(accela)} | {manual_result(accela)} | Risk-focused source fidelity, normalization, and linkage checks; no global accuracy estimate |
| Expanded external outcome verification | {progress(outcome)} | Not measured | Whether external evidence establishes real-world activity |

### Longitudinal verification

| Validation layer | Coverage / progress | Result among evaluated | What it establishes |
| --- | ---: | --- | --- |
| Initial longitudinal change audit | {progress(change)} | {manual_result(change)} | High-impact changes plus controls; source-publication changes rather than physical outcomes |"""


def update_readme(rows: list[dict]) -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    start = "<!-- verification-scorecard:start -->"
    end = "<!-- verification-scorecard:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("README must contain exactly one verification scorecard marker pair")
    snapshot_date = rows[0]["snapshot_date"]
    text, heading_count = re.subn(
        r"^## Verification Status .* snapshot$",
        f"## Verification Status — {snapshot_date} snapshot",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if heading_count != 1:
        raise ValueError("README must contain exactly one Verification Status snapshot heading")
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    path.write_text(f"{before}{start}\n{render_readme_scorecard(rows)}\n{end}{after}", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    rows = build_summary()
    output = write_summary(rows)
    update_readme(rows)
    print(output.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
