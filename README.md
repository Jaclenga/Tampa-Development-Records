# Tampa Published Development Records

This repository archives development-related records published by the City of
Tampa and tracks how those published records change over time.

## Current status

The project has a solid baseline, not yet a longitudinal result.

| Item | Status |
| --- | --- |
| Core snapshot | August 23, 2026 |
| Published source records | 4,469 from eight City GIS layers |
| Normalized activities | 3,323, including 1,113 represented in multiple sources |
| Archived snapshots | 1 |
| Month-to-month comparisons | 0; the first will be generated after the next snapshot |
| Frozen manual-validation sample | 150 first reviews and 50 blind second reviews designed; 0 completed |
| Empirical accuracy estimate | Not available until the human reviews are complete |

The current release is `v0.9.0`. It is a bounded archive of what the named
layers returned, not a database of every permit, development, completion, or
dollar invested in Tampa.

## Start here

| Need | File |
| --- | --- |
| Every record returned by the eight layers | [`data/processed/bounded_census_records.csv`](data/processed/bounded_census_records.csv) |
| Consolidated activity-level view | [`data/processed/tampa_development_activity.csv`](data/processed/tampa_development_activity.csv) |
| Compact immutable snapshot archive | [`data/snapshots/`](data/snapshots/) |
| Snapshot and comparison index | [`data/monthly_changes/index.json`](data/monthly_changes/index.json) |
| Future record-level monthly changes | `data/monthly_changes/YYYY-MM.csv` |
| Future readable monthly updates | `reports/YYYY-MM.md` |
| Unfilled coverage gaps and source priorities | [`data/coverage/source_gap_registry.csv`](data/coverage/source_gap_registry.csv) |
| Human-review work queue | [`data/processed/manual_validation_development_sample.csv`](data/processed/manual_validation_development_sample.csv) |

## What it is useful for

Today, the release supports:

- reproducing the state of eight named public layers on August 23, 2026;
- mapping and filtering those published records;
- studying overlap between Tampa's public permit, planning, preservation, and
  capital-project layers; and
- tracing normalized activities back to source records and attributes.

After repeated snapshots, it will also support questions the live layers do
not answer conveniently, such as which records appeared, disappeared, or
changed status, description, phase, cost estimate, or planned date between two
observations.

For a current address-level permit lookup, use the City's
[Accela portal](https://aca.tampa.gov/). For the live state of a City layer,
use that layer directly. This repository is most useful when reproducibility,
cross-source comparison, or historical change matters.

## Monthly change tracker

The tracker does three things after a successful collection:

1. builds and validates the current bounded-source release;
2. archives a compact, immutable copy of the source-record state under
   `data/snapshots/YYYY-MM-DD/`; and
3. when a prior snapshot exists, writes a record-level CSV, summary JSON, and
   short Markdown update for the new month.

The tracker uses stable native record identifiers when available. Global IDs
and then object IDs are fallbacks. It refuses to overwrite an existing dated
snapshot with different contents.

Tracked change types include:

| Change type | Meaning |
| --- | --- |
| `new_record` | Returned in the later snapshot but not the earlier one |
| `record_disappeared` | Returned earlier but not later |
| `status_changed` | Source-reported status changed |
| `description_changed` | Source description changed |
| `estimated_cost_changed` | Source-reported capital estimate changed |
| `planned_date_changed` | Planned start or end changed |
| `capital_project_phase_changed` | Source-reported capital phase changed |
| `other_field_changed` | Another non-volatile source attribute changed |

Semantic flags identify a `permit_issued`, `planning_application_added`, or
`expected_completion_changed` where the source fields support that narrower
description. A newly observed record is not assumed to have been created
during the interval, and a disappearance is not treated as deletion,
cancellation, or completion.

The repository includes a GitHub Actions workflow that runs on the first day
of each month and can also be started manually. It collects the same eight
layers into the compact archive, tests, compares, and commits the new tracker
artifacts only after the checks pass. It does not regenerate the frozen August
validation sample against a changing population.

To run the same process locally:

```bash
python scripts/snapshot_tracker.py collect-live
python -m unittest discover -s tests -v
```

To rebuild the existing August 23 release without calling the live services:

```bash
python scripts/build_release.py --use-existing-raw
```

The snapshot tracker can also be run directly:

```bash
python scripts/snapshot_tracker.py update
python scripts/snapshot_tracker.py compare --from-date 2026-08-23 --to-date 2026-09-01
```

`update` archives the already built `data/processed/source_records.csv`.
`collect-live` is the monthly path: it refreshes only the compact core tracker,
leaving the validation release and its sampled rows unchanged.

## Core source boundary

The baseline contains every feature returned by `where=1=1` queries to these
eight layers at the recorded retrieval time:

| Source | Records | What a row generally represents |
| --- | ---: | --- |
| [Construction Inspections](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/30) | 2,619 | Published building-permit record, not an individual inspection result |
| [Single-Family Permits](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/32) | 1,023 | Single-family new-construction or addition permit record |
| [Development Coordination](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/31) | 271 | Active planning or land-development application |
| [Historic Preservation](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/33) | 169 | Historic-preservation application |
| [Capital Improvements](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjects/FeatureServer/0) | 192 | City capital-project record |
| [Citywide Capital Projects — points](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/0) | 57 | Point representation of a capital project |
| [Citywide Capital Projects — lines](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/1) | 101 | Linear representation of a capital project |
| [Citywide Capital Projects — polygons](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/2) | 37 | Area representation of a capital project |
| **Total** | **4,469** | **Published source records** |

The permit layers overlap heavily: 999 of the 1,023 Single-Family records link
to Construction Inspections records. The build preserves 4,469 source rows but
resolves strong identifier matches into 3,323 activities. An activity is still
not necessarily a unique real-world development; one development can generate
several permits, applications, and projects.

`source_universes.csv` records each endpoint, retrieval time, source count,
retained count, and coverage warning. The current release includes every
returned source row after configured contact and source-user fields are
removed.

## Coverage expansion

The eight-layer boundary is not permanent. New sources should fill a specific
analytical gap rather than inflate the row count.

The highest priorities are:

1. a fuller building-permit export;
2. certificates of occupancy;
3. inspection-level records with explicit final-inspection results;
4. complete demolition permits and planning decisions; and
5. repeated annual capital-budget records.

No verified public bulk endpoint for the first three was located in the
official interfaces checked on August 28, 2026. The repository therefore
includes a narrowly specified [public-records request and import workflow](docs/PUBLIC_RECORDS_REQUEST.md)
instead of scraping address-level Accela pages or inferring lifecycle events.

The [source-gap registry](data/coverage/source_gap_registry.csv) separates:

- core activity sources, such as permits and applications;
- lifecycle evidence, such as final inspections and occupancy certificates;
  and
- context and linkage sources, such as parcels, footprints, and budgets.

Context rows never inflate the activity count.

## Validation status

Automated checks verify that the release faithfully preserves the archived
source data and that keys, counts, schemas, privacy suppression, and
relationships are internally consistent. They do not prove that a building
was constructed or that every linkage is correct.

The frozen study draws 150 unique activities:

- 100 development/debugging rows;
- 50 untouched holdout rows; and
- 50 blind second-review assignments drawn from those rows.

The human reviews remain unfinished. Parcel links and building-footprint
matches remain proposed or heuristic, and the repository reports no measured
error rate. Start with the
[manual-validation guide](docs/MANUAL_VALIDATION_GUIDE.md). Completed labels
must cite evidence opened and confirmed by a human; AI output alone is not
evidence.

## Event and context tables

[`development_events.csv`](data/processed/development_events.csv) records
source observations and explicit filing, hearing, issuance, planning,
capital-phase, planned-date, and reported-actual-date events. It does not infer
final inspection, occupancy, or physical completion from a permit, footprint,
planned date, or `Closeout` label.

Separately dated context modules add:

- 228 Capital Projects Budget Book records and exact project-ID comparisons;
  and
- privacy-minimized attributes for 932 parcels already exposed through
  proposed building-footprint matches.

These modules are excluded from the eight-layer census count. Their financial
fields are reported levels or estimates, not an expenditure ledger, and every
activity-to-parcel link remains pending human review.

## What not to claim

Do not use the current dataset to claim:

- the total number of Tampa developments or permits;
- the total amount of public or private development investment;
- that permit issuance means construction started;
- that `Closeout` means physical completion;
- that a missing record was deleted or cancelled; or
- that the eight layers contain the City's complete administrative record.

Those limitations are part of the data, not boilerplate.

## Repository layout

```text
data/
  raw/             current privacy-minimized GeoJSON release snapshot
  processed/       analysis-ready current-release tables
  snapshots/       compact immutable source-record observations by date
  monthly_changes/ record-level comparisons and summary index
  coverage/        prioritized source and lifecycle gaps
  context/raw/     separately scoped context snapshots
  templates/       official-data import templates
reports/           readable monthly update reports
docs/              methodology, limitations, and validation instructions
scripts/           acquisition, transformation, comparison, and QA code
tests/             deterministic workflow tests
```

See [`scripts/README.md`](scripts/README.md) for the command index and
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) for the full limitation
register.

## Reproducibility and citation

The build uses Python's standard library. Run the source-fidelity and semantic
checks separately with:

```bash
python scripts/validate_release.py
python scripts/verify_data_accuracy.py
python scripts/verify_data_accuracy.py --live
```

A difference in the live check can mean the City changed a layer after the
archived retrieval; it does not by itself invalidate the archived release.

> Lenga, Jack. *Tampa Published Development Records: Source-Bounded
> Longitudinal Tracker*, version 0.9.0, 2026.

Code and original documentation are MIT-licensed. City records remain subject
to their source terms; see [`DATA_LICENSE.md`](DATA_LICENSE.md). OpenAI ChatGPT
and Codex assisted with code, testing, profiling, and documentation; see
[`docs/AI_USE_STATEMENT.md`](docs/AI_USE_STATEMENT.md).
