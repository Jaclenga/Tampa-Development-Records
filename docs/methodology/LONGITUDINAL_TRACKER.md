# Longitudinal tracker

## Current state

The tracker contains three immutable core observations: the August 23, 2026
baseline and September 1 and October 1 follow-ups. The August 23 to September 1
comparison is a nine-day initial interval. The September 1 to October 1
comparison is a manual interval after the September 30 scheduled collection
was missed. Neither is a full month-end interval. A separate August 31 Accela
day-freeze preserves that portal query without pretending that the core GIS
retrieval, which occurred at 3:15 a.m. Tampa time, happened on August 31.

October 31 is the next eligible core month-end observation. If both October 31
and November 30 are collected, they form the first full month-end-to-month-end
comparison. The separate source-date cohort view provides retrospective monthly
organization without claiming earlier TDR observations.

## Archived core observations

| Snapshot date | Retrieved at UTC | Records | Role | Artifacts |
| --- | --- | ---: | --- | --- |
| `2026-08-23` | `2026-08-23T02:06:02+00:00` | 4,469 | Original baseline | [Snapshot](../../data/snapshots/2026-08-23/) |
| `2026-09-01` | `2026-09-01T07:15:12+00:00` | 4,408 | Reconciled first follow-up | [Snapshot](../../data/snapshots/2026-09-01/) |
| `2026-10-01` | `2026-10-01T06:47:51+00:00` | 4,624 | Manual recovery observation | [Snapshot](../../data/snapshots/2026-10-01/) |

The accepted September 1 observation was retrieved at 3:15 a.m. Tampa time. The
[machine-readable comparison](../../data/monthly_changes/2026-09.json) and
[September update](../../reports/changes/2026-09.md) compare it with the August 23
baseline. The separate [August 31 Accela freeze](../../data/frozen/accela/2026-08-31/)
contains records returned for that Accela query date and is not a core
observation.

The [October 1 comparison](../../data/monthly_changes/2026-10-01.json) and
[manual update](../../reports/changes/2026-10-01.md) compare the September 1
and October 1 core observations. They use a dated artifact ID to leave room for
another comparison in October. The October 1 retrieval occurred at 2:47 a.m.
Tampa time and cannot be relabeled as September 30.

## Two complementary temporal views

| View | Time basis | Main question |
| --- | --- | --- |
| Source-date cohorts | Dates reported within retained source records | What dates do the currently or previously published records describe? |
| Snapshot comparisons | Repeated TDR retrievals | How did the configured public layers change between observations? |

The cohort view is documented in [TEMPORAL_COHORTS.md](TEMPORAL_COHORTS.md).
Its `event_month`, `first_observed_month`, and `snapshot_month` fields are kept
separate. Historical source dates do not backfill TDR publication history.

## What the tracker does

After a successful collection, the tracker:

1. retrieves the eight configured City layers using privacy-minimized fields;
2. validates and archives a compact source-record state under
   `data/snapshots/YYYY-MM-DD/`;
3. refuses to overwrite an existing dated snapshot with different contents;
4. compares the new state with the prior snapshot; and
5. writes record-level CSV, summary JSON, and readable Markdown outputs.

Before a live layer can be accepted, the collector reconciles two initial
`returnCountOnly=true` queries, the complete `returnIdsOnly=true` inventory,
the object IDs returned by chunked feature requests, and a final count query.
Any disagreement, duplicate ID, missing ID, ArcGIS error payload, timeout, or
partial nonzero response fails collection and prevents archiving. This is a
collection-integrity test; it does not establish that the source itself is
complete or that a published record represents a real-world outcome.

An earlier September 1 capture predated this safeguard and contained only 280
permit records. It was replaced, after explicit authorization, by a fully
reconciled same-day observation containing 1,016 permit records. The accepted
snapshot metadata retains the earlier retrieval time, count, and content hash
as supersession provenance. The original bytes remain recoverable from Git
history, but they are no longer the active September 1 snapshot.

The snapshot metadata records source counts, observation time, identity rules,
and SHA-256 content hashes. Geometry remains in the full raw release instead
of being duplicated in every compact snapshot.

## Record identity

The tracker prefers stable native record identifiers. If a native identifier
is duplicated, it uses GlobalID and then OBJECTID to disambiguate the records.
An upstream republish that replaces every available identifier may appear as a
paired disappearance and new record.

## Change semantics

| Change type | Meaning |
| --- | --- |
| `new_record` | Present in the later published snapshot only |
| `record_disappeared` | Present in the earlier published snapshot only |
| `status_changed` | Source-reported status changed |
| `description_changed` | Source description changed |
| `estimated_cost_changed` | Source-reported estimate changed |
| `planned_date_changed` | Planned start or end changed |
| `capital_project_phase_changed` | Source-reported capital phase changed |
| `other_field_changed` | Another non-volatile source attribute changed |

Semantic flags such as `permit_issued`, `planning_application_added`, and
`expected_completion_changed` are emitted only when source fields support the
narrower description. A new record is not assumed to be newly created, and a
disappearance is not evidence of cancellation, deletion, or completion.

## Commands

Collect and process the next live snapshot:

```bash
python scripts/snapshot_tracker.py collect-live
```

Archive an already-built `data/processed/source_records.csv` and compare it
with the prior snapshot:

```bash
python scripts/snapshot_tracker.py update
```

Compare two existing snapshots explicitly:

```bash
python scripts/snapshot_tracker.py compare --from-date 2026-08-23 --to-date 2026-09-01
```

Analyze one comparison or rebuild every available analysis:

```bash
python scripts/analyze_snapshot_changes.py --from-date 2026-08-23 --to-date 2026-09-01
python scripts/analyze_snapshot_changes.py --all
python scripts/build_change_dashboard.py
```

The analyzer reports raw and diagnostic totals, source health, exact-field
concentration, transitions, planned dates, costs, identity quality, alerts, and
trend eligibility. Thresholds are documented in
[CHANGE_DASHBOARD.md](CHANGE_DASHBOARD.md). These diagnostics are not evidence
that a source is wrong or that a real-world event occurred. The tracker runs
the analysis and static dashboard pipeline automatically after each successful
comparison.

The scheduled workflow in `.github/workflows/monthly-snapshot.yml` runs at
12:17 UTC on candidate dates from the 28th through the 31st, leaving at least
15 hours before Tampa midnight for a delayed start. A Tampa-time guard continues
only on the last local calendar day and skips collection if that observation
date is already archived. A second guard checks the archived date after
collection and prevents a commit if collection crossed Tampa midnight. The
tracker derives new snapshot dates from the Tampa date of the actual UTC
retrieval timestamp, including when the UTC date has already advanced.

Manual runs are still supported and always preserve their actual observation
date. The workflow collects, tests, and commits new tracker artifacts only when
the checks pass. It does not regenerate the frozen validation sample against a
changing population.

## Observation-date convention

- `2026-08-23` is the original core baseline.
- `2026-08-31` is an Accela day-freeze, not a core GIS snapshot.
- `2026-09-01` is the first core follow-up and retains its actual date.
- The scheduled `2026-09-30` core observation was missed.
- `2026-10-01` is a manual recovery observation, not a month-end snapshot.
- `2026-10-31` is the next eligible month-end observation.
- Later scheduled observations use each month's final Tampa calendar date.

New snapshot dates use the Tampa calendar date of `retrieved_at_utc`; the exact
UTC timestamp remains in metadata. The earlier archived snapshot labels are
preserved. Historical source dates and Accela query dates never substitute for
the observation timestamp.

## Outputs

```text
data/snapshots/YYYY-MM-DD/       immutable compact snapshot and metadata
data/monthly_changes/index.json  snapshot and comparison inventory
data/monthly_changes/YYYY-MM.csv       monthly-named record-level changes
data/monthly_changes/YYYY-MM.json      monthly-named comparison summary
data/monthly_changes/YYYY-MM-DD.*      interim comparison artifacts
reports/changes/YYYY-MM.md            monthly-named readable update
reports/changes/YYYY-MM-DD.md         interim readable update
data/monthly_changes/analysis/   deterministic analysis JSON and CSVs
reports/dashboard/index.html     static comparison dashboard
reports/dashboard/comparisons/   identity-safe comparison detail pages
data/processed/activity_by_month.csv canonical source-date table
data/monthly_events/YYYY-MM.csv  non-future source-date extracts
data/monthly_events/index.json   non-future extract inventory
data/planned_events/YYYY-MM.csv  forward-looking source plans
data/planned_events/index.json   planned extract inventory
```

`comparison_month` remains `YYYY-MM` in the data; `comparison_id` determines
the filename. Month-end comparisons normally use `YYYY-MM`, while manual
interim comparisons use their observation date (`YYYY-MM-DD`).
