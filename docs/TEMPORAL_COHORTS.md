# Source-date monthly events and plans

## Purpose

The cohort view adds retrospective time structure to records already retained
by TDR. It complements the prospective snapshot tracker; it does not replace
or backfill the observation history.

The canonical table is `data/processed/activity_by_month.csv`. It contains one
row per in-scope source-record identity ever retained in an immutable TDR
snapshot and preserves both past and forward-looking source dates with explicit
flags. The historical dataset boundary is January 1, 2020. Records with a known
selected event date before that boundary are excluded from the canonical cohort
table and researcher-facing monthly extracts. Immutable source snapshots remain
unchanged as provenance.

Researcher-facing extracts separate those meanings:

- `data/monthly_events/YYYY-MM.csv` contains source-described dates on or
  before the snapshot supplying each row.
- `data/planned_events/YYYY-MM.csv` contains only explicit source-reported plan
  dates after the snapshot supplying each row.

Each directory has an `index.json` reporting counts by month, source, and date
type. The former `data/monthly_records/` mixed extract is intentionally removed.

## Three different month concepts

| Field | Question answered | Source |
| --- | --- | --- |
| `event_month` | What month does a selected source date describe? | A documented field in the City record |
| `first_observed_month` | When did TDR first retain this record identity? | Earliest TDR snapshot containing it |
| `snapshot_month` | Which snapshot supplies the attributes in this row? | Latest TDR snapshot containing it |

For example, a permit can have `event_month=2025-04` and
`first_observed_month=2026-08`. That supports the statement that the selected
source field reports an April 2025 event. It does not show that the record
entered the City's GIS layer in April 2025.

`last_observed_month` separately records the latest snapshot in which TDR saw
the identity. `currently_observed=0` means it is absent from the latest
snapshot. That does not prove deletion, cancellation, or completion.

## Event-date selection rules

The pipeline selects at most one cohort date per source record. Every populated
date carries `event_date_type`, `event_date_source_field`, and
`event_date_basis` so unlike concepts remain distinguishable.

| Source | Selection hierarchy | Date type | Basis |
| --- | --- | --- | --- |
| Single-Family Permits | Issued task/status date; otherwise opened date; otherwise record creation | `permit_issued`, `permit_application_opened`, or `source_record_created` | Reported event or record metadata |
| Construction Inspections | Record creation date | `permit_record_created` | Record metadata |
| Development Coordination | Record creation date | `planning_application_created` | Reported application event |
| Historic Preservation | Record creation date | `preservation_application_created` | Reported application event |
| Capital-project layers | Actual start; otherwise planned start; otherwise record creation | `capital_actual_start`, `capital_planned_start`, or `source_record_created` | Reported event, reported plan, or record metadata |

The Construction Inspections layer does not expose a dedicated permit-issued
date in the archived fields. Its generic last-update field is therefore not
relabeled as issuance. Capital planned starts are retained because they are
analytically useful, but `event_date_is_planned=1` and
`event_date_basis=source_reported_plan` make the limitation explicit.

Dates before 2000 and after 2100 are treated as invalid rather than preserving
known ArcGIS sentinel values. Valid dates before January 1, 2020 are recognized
for deterministic scope filtering and then excluded from published cohort
outputs. `event_date_is_after_snapshot=1` identifies a
future-dated value relative to the snapshot supplying the row. Publication
fails if such a value is not also an explicit source-reported plan. Valid
future plans are routed only to `data/planned_events/` and cannot appear in
`data/monthly_events/`.

## Extract routing

| Output | Rule | Meaning |
| --- | --- | --- |
| `activity_by_month.csv` | Undated identities plus identities with `event_date >= 2020-01-01` | Canonical in-scope table; inspect flags before analysis |
| `monthly_events/YYYY-MM.csv` | `2020-01-01 <= event_date <= snapshot_date` | In-scope source-described dates that are not forward-looking relative to collection |
| `planned_events/YYYY-MM.csv` | `event_date > snapshot_date` and `event_date_is_planned=1` | Forward-looking intentions reported by the source |
| `snapshots/YYYY-MM-DD/` | TDR retrieval date | What the City source layers published when collected |

For example, `monthly_events/2026-08.csv` is not a September-or-later forecast,
while `planned_events/2027-09.csv` is explicitly forward-looking. Neither file
shows when a record first appeared in the City's own system; use the snapshot
fields and immutable snapshot archive for TDR observation history.

## Appropriate analysis

Researchers can count records in `monthly_events` by source-described month,
compare year-over-year patterns within the same source and date type, examine
neighborhood composition, or measure how long identities remain observable
across TDR snapshots. Analyze `planned_events` separately as a schedule or
pipeline of intentions. Analyses should group or filter by both `source_name`
and `event_date_type` unless the research design justifies combining them.

Do not interpret the cohort table as:

- a census of all Tampa development activity;
- the month a record first entered the City's internal or public system;
- proof that permitted work started or finished;
- a homogeneous event series combining applications, record creation,
  issuance, actual starts, and planned starts; or
- an immutable monthly publication history.

Monthly event and planned-event files are regenerated from the latest value
observed for each record identity. If a source corrects a date—or a planned
date becomes non-future relative to a later snapshot—the record can move to a
different extract or cohort. The immutable snapshots preserve the observed
source states needed to audit that change.

## Rebuild

The full release build and scheduled snapshot tracker regenerate the cohort
view automatically. It can also be run directly:

```bash
python scripts/monthly_cohorts.py
```

## Accela expanded-edition timing

The optional integrated Accela edition uses the same conceptual separation but
does not alter the core cohort table. Its fields are `event_date`,
`event_date_type`, `first_observed_date`, `snapshot_date`,
`last_observed_date`, `historical_reconstruction`, and `temporal_evidence`.

Records opened from 2025-08-01 through 2026-07-31 were retrieved in August
2026 and are classified as `retrospective_source_record`. They support analysis
of dates currently reported by Tampa, subject to coverage discontinuities, but
they are not historical snapshots. Records from 2026-08-01 onward are
classified as `prospective_snapshot` when collected by TDR. The collector does
not emit `retrospective_event_history` without an actual dated event-history
source.
