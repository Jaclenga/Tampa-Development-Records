# Longitudinal tracker

## Current state

The tracker contains one immutable observation dated August 23, 2026. It is a
baseline only: there are no month-to-month comparisons or observed
longitudinal results yet. A separate source-date cohort view provides
retrospective monthly organization without claiming earlier TDR observations.

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

The scheduled workflow in `.github/workflows/monthly-snapshot.yml` runs on the
first day of each month and can be triggered manually. It collects, tests, and
commits new tracker artifacts only when the checks pass. It does not regenerate
the frozen validation sample against a changing population.

## Outputs

```text
data/snapshots/YYYY-MM-DD/       immutable compact snapshot and metadata
data/monthly_changes/index.json  snapshot and comparison inventory
data/monthly_changes/YYYY-MM.csv record-level changes
data/monthly_changes/YYYY-MM.json comparison summary
reports/YYYY-MM.md               readable monthly update
data/processed/activity_by_month.csv source-record cohort table
data/monthly_records/YYYY-MM.csv source-date cohort extracts
data/monthly_records/index.json  cohort inventory and counts
```
