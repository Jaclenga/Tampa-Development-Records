#!/usr/bin/env python3
"""Analyze one or all archived snapshot comparisons and enrich their reports."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import change_analysis  # noqa: E402


def pct(value: float | None) -> str:
    return "undefined" if value is None else f"{value * 100:+.1f}%"


def rate_text(value: float | None) -> str:
    return "undefined" if value is None else f"{value * 100:.1f}%"


def source_label(value: str) -> str:
    return value.replace("_", " ").title()


def markdown_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def valid_link(value: str) -> bool:
    return change_analysis.valid_url(value)


def render_report(analysis: dict[str, object], changes: list[dict[str, str]]) -> str:
    comparison = analysis["comparison"]
    overall = analysis["overall"]
    trend = analysis["trend_eligibility"]
    integrity = analysis.get("collection_integrity", {})
    excluded = overall["excluding_critical_sources"]
    severity_counts = Counter(item["severity"] for item in analysis["alerts"])
    lines = [
        f"# Tampa Published Development Records — {comparison['comparison_month']} update",
        "",
        f"Comparison: **{comparison['snapshot_from']} → {comparison['snapshot_to']}**",
        "",
        "> This report measures changes in records returned by published sources. A disappearance means a record was no longer returned; it does not prove cancellation, deletion, or completion.",
        "",
        "## Comparison classification and health",
        "",
        f"- Classification: `{comparison['comparison_kind']}`",
        f"- Canonical month-end comparison: `{'true' if comparison['canonical_monthly_comparison'] else 'false'}`",
        f"- Interval: {comparison['interval_days']} days",
        f"- Alert status: **{analysis['overall_status'].upper()}** ({severity_counts['critical']} critical, {severity_counts['warning']} warning)",
        f"- Later-snapshot collection integrity: `{integrity.get('status', 'not_audited')}` (passed: `{str(integrity.get('passed')).lower()}`)",
        f"- Eligible for raw reporting: `{'true' if trend['usable_for_raw_reporting'] else 'false'}`",
        f"- Eligible for global aggregate trend: `{'true' if trend['usable_for_global_aggregate_trend'] else 'false'}`",
        f"- Eligible for unflagged-source trends: `{'true' if trend['usable_for_unflagged_source_trends'] else 'false'}`",
        "",
        "## Raw and diagnostic totals",
        "",
        "| View | Before | After | Net | Percent | New | No longer returned | Churn |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| All sources (raw) | {overall['count_before']:,} | {overall['count_after']:,} | {overall['absolute_net_change']:+,} | {pct(overall['percentage_net_change'])} | {overall['new_records']:,} | {overall['disappeared_records']:,} | {rate_text(overall['publication_churn'])} |",
    ]
    if excluded:
        names = ", ".join(f"`{value}`" for value in excluded["excluded_source_ids"])
        lines.append(
            f"| Diagnostic excluding {names} | {excluded['count_before']:,} | {excluded['count_after']:,} | "
            f"{excluded['absolute_net_change']:+,} | {pct(excluded['percentage_net_change'])} | "
            f"{excluded['new_records']:,} | {excluded['disappeared_records']:,} | {rate_text(excluded['publication_churn'])} |"
        )
        lines.extend(["", f"The exclusion-based row names {names} explicitly and is diagnostic only; it never replaces the raw all-source result."])
    else:
        lines.extend(["", "No critical source is excluded from the diagnostic view."])

    lines.extend(["", "## Alerts", ""])
    if analysis["alerts"]:
        for item in analysis["alerts"]:
            source = f" — `{item['source_id']}`" if item.get("source_id") else ""
            lines.append(f"- **{item['severity'].upper()} `{item['alert_code']}`{source}:** {item['explanation']}")
    else:
        lines.append("- No configured alert threshold was crossed.")

    lines.extend([
        "",
        "## Source health",
        "",
        "| Source | Before | After | Net | New | No longer returned | Retention | Churn | Changed identities | Alert |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for row in analysis["source_health"]:
        reasons = ", ".join(row["alert_reasons"]) or "—"
        lines.append(
            f"| `{row['source_id']}` | {row['before_count']:,} | {row['after_count']:,} | {row['absolute_delta']:+,} | "
            f"{row['new_records']:,} | {row['disappeared_records']:,} | {rate_text(row['retention_rate'])} | "
            f"{rate_text(row['publication_churn'])} | {row['unique_changed_identities']:,} | {row['alert_level']}: {reasons} |"
        )

    fields = sorted(
        analysis["field_change_concentration"],
        key=lambda row: (not row["mass_refresh_warning"], -(row["affected_retained_rate"] or -1), row["source_id"], row["changed_field"]),
    )
    lines.extend([
        "",
        "## Highest-concentration changed fields",
        "",
        "| Source | Exact field | Category | Retained records affected | Rate | Mass refresh |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ])
    for row in fields[:25]:
        lines.append(
            f"| `{row['source_id']}` | `{markdown_escape(row['changed_field'])}` | `{row['semantic_change_category']}` | "
            f"{row['unique_retained_identities_affected']:,} / {row['retained_record_denominator']:,} | "
            f"{rate_text(row['affected_retained_rate'])} | {'warning' if row['mass_refresh_warning'] else 'no'} |"
        )

    lines.extend([
        "",
        "## What changed in the published layers",
        "",
        f"- {overall['new_records']:,} newly observed source records",
        f"- {overall['disappeared_records']:,} records no longer returned",
        f"- {overall['change_type_counts'].get('status_changed', 0):,} status changes",
        f"- {overall['semantic_change_category_counts'].get('planning_application_added', 0):,} newly observed planning applications",
        f"- {overall['change_type_counts'].get('capital_project_phase_changed', 0):,} capital-project phase changes",
        f"- {overall['change_type_counts'].get('estimated_cost_changed', 0):,} estimated-cost changes",
        f"- {overall['change_type_counts'].get('planned_date_changed', 0):,} planned-date changes",
        "",
        f"The earlier snapshot contained {overall['count_before']:,} source records; the later snapshot contained {overall['count_after']:,}. "
        f"A total of {overall['unique_changed_record_identities']:,} canonical record identities had at least one reported change.",
        "",
        "## Status and phase transitions",
        "",
        f"The comparison contains {sum(row['unique_record_count'] for row in analysis['status_transitions']):,} source-specific status transitions and "
        f"{sum(row['unique_record_count'] for row in analysis['phase_transitions']):,} source-specific phase transitions. "
        "No universal forward/backward ordering is imposed on source labels.",
        "",
        "## Planned dates and costs",
        "",
        f"- Planned-date changes analyzed: {len(analysis['planned_date_changes']['events']):,}",
        f"- Cost changes analyzed: {len(analysis['cost_changes']['events']):,}",
        "",
        analysis["cost_changes"]["aggregation_warning"],
        "",
        "## Selected field changes",
        "",
        "| Type | Source | Canonical identity | Native ID | Fields | Old | New |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    notable_types = {
        "status_changed", "capital_project_phase_changed", "estimated_cost_changed",
        "reported_actual_cost_changed", "planned_date_changed",
    }
    notable = [row for row in changes if row["change_type"] in notable_types][:30]
    for row in notable:
        native = clean_native = row.get("source_record_id", "").strip() or "(blank)"
        label = markdown_escape(native)
        if valid_link(row.get("source_url", "")):
            label = f"[{label}]({row['source_url']})"
        lines.append(
            f"| `{row['change_type']}` | `{row['source_name']}` | `{markdown_escape(row['record_identity'])}` | {label} | "
            f"`{markdown_escape(row['changed_fields'])}` | {markdown_escape(row['old_value'])[:180]} | {markdown_escape(row['new_value'])[:180]} |"
        )
    if not notable:
        lines.append("| — | — | — | — | — | — | — |")

    lines.extend([
        "",
        "## Interpretation",
        "",
        "This report compares two observations of eight named City of Tampa public GIS layers. A newly observed record may have existed before the interval, and a record no longer returned is not necessarily deleted, cancelled, or complete. A phase change is a source-reported label change, not proof of completed construction. Permit issuance is authorization, planned dates are schedules, and estimated or reported actual costs are not a citywide investment total.",
        "",
        f"- Raw changes: [`data/monthly_changes/{comparison['comparison_month']}.csv`](../data/monthly_changes/{comparison['comparison_month']}.csv)",
        f"- Analysis: [`data/monthly_changes/analysis/{comparison['comparison_month']}.json`](../data/monthly_changes/analysis/{comparison['comparison_month']}.json)",
        f"- Dashboard detail: [`docs/dashboard/comparisons/{comparison['comparison_month']}.html`](../docs/dashboard/comparisons/{comparison['comparison_month']}.html)",
        "",
    ])
    return "\n".join(lines)


def analyze_pair(before_date: str, after_date: str) -> dict[str, object]:
    analysis, changes = change_analysis.analyze_paths(before_date, after_date)
    paths = change_analysis.write_analysis_artifacts(analysis)
    report = ROOT / "reports" / f"{analysis['comparison']['comparison_month']}.md"
    change_analysis.atomic_text(report, render_report(analysis, changes))
    change_analysis.update_index()
    return {"analysis": analysis, "paths": paths, "report": report.relative_to(ROOT).as_posix()}


def comparison_pairs() -> list[tuple[str, str]]:
    pairs = []
    for path in sorted(change_analysis.CHANGES.glob("????-??.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        before = value.get("before_snapshot_date")
        after = value.get("after_snapshot_date")
        if before and after:
            pairs.append((str(before), str(after)))
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.all:
        pairs = comparison_pairs()
        if not pairs:
            raise SystemExit("No comparison artifacts are available")
    elif args.from_date and args.to_date:
        pairs = [(args.from_date, args.to_date)]
    else:
        parser.error("provide --all or both --from-date and --to-date")
    results = [analyze_pair(before, after) for before, after in pairs]
    try:
        from scripts import build_change_dashboard
    except ImportError:
        import build_change_dashboard
    dashboard = build_change_dashboard.build_dashboard()
    print(json.dumps({
        "comparisons_analyzed": len(results),
        "results": [
            {
                "comparison": result["analysis"]["comparison"],
                "overall_status": result["analysis"]["overall_status"],
                "paths": result["paths"],
                "report": result["report"],
            }
            for result in results
        ],
        "dashboard": dashboard,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
