# Snapshot-change analysis and dashboard

## Purpose and architecture

The snapshot-change system evaluates how the configured City of Tampa public
sources differ between archived observations. It does not verify physical
construction outcomes. A newly observed record may be old, a record no longer
returned is not necessarily cancelled or deleted, and a phase change does not
prove completed work.

The system has three layers:

1. `snapshot_tracker.py` preserves the existing snapshots and raw comparison
   CSV/JSON format.
2. `change_analysis.py` derives deterministic aggregate, source, exact-field,
   transition, planned-date, cost, identity-quality, alert, and trend-
   eligibility metrics.
3. `build_change_dashboard.py` renders those artifacts as static HTML with
   inline CSS, SVG, embedded data, and minimal vanilla JavaScript.

The analytical logic is independent of HTML rendering. No current clock time
is stored, and every output is sorted so identical inputs produce identical
bytes.

## Metrics and denominators

For all sources and for each source separately:

- `retained_records = count_before - disappeared_records`
- `union_size = retained_records + new_records + disappeared_records`
- retention rate uses `count_before` as its denominator;
- disappearance rate uses `count_before` as its denominator;
- publication churn is `(new_records + disappeared_records) / union_size`;
- changed-identity rate uses `union_size` as its denominator; and
- an exact field's affected rate uses retained records from that source.

An undefined denominator produces JSON `null`, never a substituted zero.
Change-row totals can exceed changed-identity totals because one canonical
`record_identity` can have multiple field categories. Exact-field metrics
deduplicate identities within each source and field.

## Alerts and thresholds

[`config/change_analysis_thresholds.json`](../../config/change_analysis_thresholds.json)
is the controlling configuration. Critical alerts identify source count
collapses or disappearance rates of at least 50% when at least 100 records are
affected. Warning thresholds cover 20% source shifts, 30% publication churn,
and exact-field refreshes affecting at least 75% of 25 or more retained
records. Noncanonical intervals are also flagged.

Every alert records a stable code, severity, source when applicable, metric,
observed value, threshold, affected count, explanation, and whether it blocks
global aggregate trend interpretation. Overall status is `healthy`, `review`,
or `critical` based on the highest emitted severity.

## Raw and exclusion-based views

Raw totals always include every configured source, including anomalous ones.
When a source receives a critical alert, the analysis also calculates
`overall.excluding_critical_sources`. This diagnostic view names every excluded
source and helps distinguish a source-specific publication collapse from
movement in the other sources. It never replaces the raw result and must not be
used to silently revise the archive.

## Interval classification and trend eligibility

Supported interval kinds are:

- `baseline_followup`: begins at the documented August 23, 2026 baseline;
- `month_end_to_month_end`: adjacent final calendar days beginning with the
  documented September 30 month-end series;
- `manual_interval`: valid observations outside those rules; and
- `unknown`: invalid or unavailable date semantics.

The September 1 observation retains its actual date and is not reconstructed
as August 31. The August 23 to September 1 interval is a nine-day
`baseline_followup`, not an ordinary monthly trend point.

The active September 1 snapshot is the reconciled 4,408-record retrieval. It
contains 1,016 single-family permit records and passed the collector's
count-only, ID-inventory, chunked-feature, and final-count checks. It supersedes
an incomplete same-day capture that returned only 280 permits. The current
August 23 to September 1 comparison has no critical collection-integrity alert;
its `review` status reflects systematic field refreshes and the noncanonical
nine-day interval. Supersession provenance is retained in the
[snapshot metadata](../../data/snapshots/2026-09-01/metadata.json).

`trend_eligibility` separates raw reporting from trend use. Raw reporting
remains available even for critical comparisons. Global aggregate trends
require a noncritical canonical month-end interval. Unflagged-source trends
can remain available with explicit caveats and named critical exclusions.

Dashboard historical charts hide noncanonical and critical intervals by
default. A visible control reveals them; they are never deleted.

## Planned dates, costs, and identities

Parseable planned dates are classified as moved earlier, moved later,
unchanged after normalization, added, or removed. Unparseable values remain
explicit. Cost changes are classified as increases, decreases, additions,
removals, equivalent formatting, or unparseable. Cost distributions stay
source-specific because overlapping sources must not be summed as Tampa-wide
investment.

Canonical `record_identity` controls uniqueness and drill-down behavior.
`source_record_id` is display-only. Duplicate or blank native IDs, duplicate
canonical identities, missing identities, and blank or malformed links are
reported rather than silently merged or discarded.

## Outputs

For comparison month `YYYY-MM`:

```text
data/monthly_changes/analysis/YYYY-MM.json
data/monthly_changes/analysis/YYYY-MM_sources.csv
data/monthly_changes/analysis/YYYY-MM_fields.csv
data/monthly_changes/analysis/YYYY-MM_transitions.csv
reports/changes/YYYY-MM.md
reports/dashboard/index.html
reports/dashboard/comparisons/YYYY-MM.html
```

The dashboard is self-contained and works from a local file or static host. It
uses no CDN, package, server, or network request.

## Regeneration

```bash
python scripts/analyze_snapshot_changes.py --from-date 2026-08-23 --to-date 2026-09-01
python scripts/analyze_snapshot_changes.py --all
python scripts/build_change_dashboard.py
```

The tracker runs the same pipeline after every successful comparison. The core
pipeline uses only Python's standard library.

## Limitations

Alerts identify unusual publication behavior, not errors or verified outcomes.
Status labels have no universal ordering; forward/backward interpretation is
omitted unless a source-specific order is explicitly documented. Compact
snapshots do not provide a stable geometry representation, so this dashboard
does not include a map. Record-level public attributes can remain sensitive;
the dashboard uses privacy-minimized snapshot fields and preserves the
repository privacy checks.
