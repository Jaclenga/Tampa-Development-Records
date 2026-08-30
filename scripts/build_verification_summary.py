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
DOCS = ROOT / "docs"
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
    accuracy = json.loads((DOCS / "accuracy_verification_report.json").read_text(encoding="utf-8"))
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
    second = read_csv(PROCESSED / "manual_validation_second_review.csv")
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

    trace_passed = source_count == raw_count and accuracy.get("source_snapshot_fidelity") == "verified"
    trace_counts = ReviewCounts(raw_count, raw_count, raw_count if trace_passed else 0,
                                0 if trace_passed else raw_count, 0, 0, 0, 0)
    rows = [
        row(snapshot_date, "automated_qa", qa_counts, "passed" if qa_passed else "flagged",
            "Record coverage is the bounded source census; results are check-level because some checks are release-wide."
            + (f" Flagged checks: {', '.join(qa_issues)}." if qa_issues else ""),
            passed_supported="", failed_conflicting="",
            checks_evaluated=qa_check_counts["evaluated"], checks_passed=qa_check_counts["passed"],
            checks_flagged=qa_check_counts["flagged"]),
        row(snapshot_date, "source_traceability", trace_counts, "passed" if trace_passed else "flagged",
            "Reconciles bundled City source features to retained source rows; establishes source fidelity, not real-world truth."),
        {
            **row(snapshot_date, "automated_evidence", ReviewCounts(0, 0, 0, 0, 0, 0, 0, 0),
                  "not_measured", "No distinct reproducible software check of external supporting evidence exists."),
            "eligible_records": "", "evaluated_records": "", "passed_supported": "",
            "failed_conflicting": "", "unknown": "", "not_applicable": "",
            "partial_support": "", "awaiting_review": "", "coverage_percentage": "",
        },
        row(snapshot_date, "manual_validation", manual_counts,
            "complete" if manual_counts.awaiting == 0 else "in_progress",
            "Frozen seeded stratified probability sample; results are claim-specific, so no universal supported count is produced.",
            passed_supported="", failed_conflicting="", unknown="", not_applicable="", partial_support="",
            second_review_count=second_counts.evaluated),
        row(snapshot_date, "external_outcome_verification", pilot_counts, "historical_pilot",
            "Historical evidence-selected pilot; physical-realization outcomes are not a population estimate."),
        row(snapshot_date, "double_review", second_counts,
            "complete" if second_counts.awaiting == 0 else "in_progress",
            "Independent blinded second-review assignments only; automated checks are excluded.",
            passed_supported="", failed_conflicting="", unknown="", not_applicable="", partial_support="",
            second_review_count=second_counts.evaluated),
    ]
    if manual_counts.eligible != 150 or second_counts.eligible != 50:
        raise ValueError(
            f"Study denominators disagree with frozen design: manual={manual_counts.eligible}, second={second_counts.eligible}"
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
    qa = by_type["automated_qa"]
    trace = by_type["source_traceability"]
    manual = by_type["manual_validation"]
    pilot = by_type["external_outcome_verification"]
    second = by_type["double_review"]
    study_status = "COMPLETE" if manual["status"] == second["status"] == "complete" else "IN PROGRESS"
    qa_result = (
        f"{qa['checks_passed']} checks passed; {qa['checks_flagged']} checks flagged"
        if qa["checks_evaluated"] != ""
        else "Not measured"
    )
    return f"""Coverage says how many eligible records were evaluated. Results describe only
those evaluated records; they are not a dataset-wide accuracy percentage.

| Verification layer | Coverage / progress | Result among evaluated | What it establishes |
| --- | ---: | --- | --- |
| Automated QA | {int(qa['evaluated_records']):,} / {int(qa['eligible_records']):,} ({qa['coverage_percentage']}%) | {qa_result} | Structural, relationship, range, consistency, privacy, and release-integrity checks |
| Source traceability | {int(trace['evaluated_records']):,} / {int(trace['eligible_records']):,} ({trace['coverage_percentage']}%) | {int(trace['passed_supported']):,} reconciled; {int(trace['failed_conflicting']):,} conflicting | Fidelity to the eight archived City source layers, not necessarily real-world truth |
| Automated evidence checks | Not measured | Not measured | No separate software system currently checks external supporting evidence |
| Manual validation sample | {manual['evaluated_records']} / {manual['eligible_records']} ({manual['coverage_percentage']}%) | {'No claim outcomes yet' if manual['evaluated_records'] == 0 else 'See claim-specific review metrics'} | Human application of the frozen, documented validation protocol |
| External outcome verification | {pilot['evaluated_records']} / {pilot['eligible_records']} historical pilot rows | {pilot['passed_supported']} work documented; {pilot['partial_support']} partial; {pilot['unknown']} not established; {pilot['not_applicable']} not applicable | Limited cited evidence about physical realization; not a representative estimate |
| Double review | {second['evaluated_records']} / {second['eligible_records']} ({second['coverage_percentage']}%) | {'No agreement result yet' if second['evaluated_records'] == 0 else 'See reviewer-agreement metrics'} | Independent, blinded second-review coverage |

**Release-level status:** Automated QA {int(qa['evaluated_records']):,} / {int(qa['eligible_records']):,}; source traceability
{int(trace['evaluated_records']):,} / {int(trace['eligible_records']):,}; automated evidence `Not measured`; manual validation {manual['evaluated_records']} / {manual['eligible_records']};
external outcome pilot {pilot['evaluated_records']} / {pilot['eligible_records']}; double-reviewed {second['evaluated_records']} / {second['eligible_records']}; validation study
`{study_status}`.

```text
Manual validation sample
{manual['eligible_records']} selected
|
+-- Reviewed ............... {manual['evaluated_records']}
|   `-- Claim outcomes ..... {'Not measured' if manual['evaluated_records'] == 0 else 'See claim-specific metrics'}
|
`-- Awaiting review ....... {manual['awaiting_review']}
```"""


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
