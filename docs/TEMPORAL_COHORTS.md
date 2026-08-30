# Source-date monthly cohorts

## Purpose

The cohort view adds retrospective time structure to records already retained
by TDR. It complements the prospective snapshot tracker; it does not replace
or backfill the observation history.

The main table is `data/processed/activity_by_month.csv`. It contains one row
per source-record identity ever retained in an immutable TDR snapshot. Nonempty
event months are also partitioned into `data/monthly_records/YYYY-MM.csv` for
convenient analysis. `data/monthly_records/index.json` reports counts by month,
source, and date type.

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
known ArcGIS sentinel values. `event_date_is_after_snapshot=1` identifies a
future-dated value relative to the snapshot supplying the row. This can be
expected for a plan but should be reviewed for event or record-metadata dates.

## Appropriate analysis

Researchers can count records by event month, compare year-over-year patterns
within the same source and date type, examine neighborhood composition, or
measure how long identities remain observable across TDR snapshots. Analyses
should group or filter by both `source_name` and `event_date_type` unless the
research design justifies combining them.

Do not interpret the cohort table as:

- a census of all Tampa development activity;
- the month a record first entered the City's internal or public system;
- proof that permitted work started or finished;
- a homogeneous event series combining applications, record creation,
  issuance, actual starts, and planned starts; or
- an immutable monthly publication history.

Monthly cohort files are regenerated from the latest value observed for each
record identity. If a source corrects an event date, the record can move to a
different cohort. The immutable snapshots preserve the observed source states
needed to audit that change.

## Rebuild

The full release build and scheduled snapshot tracker regenerate the cohort
view automatically. It can also be run directly:

```bash
python scripts/monthly_cohorts.py
```

