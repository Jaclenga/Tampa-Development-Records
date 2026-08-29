# Tampa Published Development Records

A reproducible archive of development-related records published by the City
of Tampa, with tools for tracking changes in those records over time.

## Status

This is a strong baseline, not yet a validated longitudinal result.

| Item | Current state |
| --- | --- |
| Core snapshot | August 23, 2026 |
| Published records | 4,469 records from eight City GIS layers |
| Normalized activities | 3,323 |
| Archived snapshots | 1 |
| Monthly comparisons | 0; requires a second snapshot |
| Manual validation | 0 of 150 first reviews completed |
| Empirical accuracy | Not yet measured |
| Release | Version 0.9.0 prepared; Git tag not yet published |

The dataset is complete only with respect to the records returned by the eight
named layers at the recorded retrieval time. It is not a complete inventory of
Tampa permits, developments, construction outcomes, or investment.

## Start here

| Goal | File |
| --- | --- |
| Analyze every published source record | [`data/processed/bounded_census_records.csv`](data/processed/bounded_census_records.csv) |
| Use the consolidated activity view | [`data/processed/tampa_development_activity.csv`](data/processed/tampa_development_activity.csv) |
| Inspect source coverage | [`data/processed/source_universes.csv`](data/processed/source_universes.csv) |
| Review the immutable snapshot | [`data/snapshots/2026-08-23/`](data/snapshots/2026-08-23/) |
| Complete manual validation | [`docs/MANUAL_VALIDATION_GUIDE.md`](docs/MANUAL_VALIDATION_GUIDE.md) |
| Navigate all documentation | [`docs/README.md`](docs/README.md) |

## What the dataset supports

- Reproducing the state of eight City GIS layers on August 23, 2026.
- Mapping and filtering the published records.
- Studying overlap among permit, planning, preservation, and capital-project
  layers.
- Tracing normalized activities back to source records and attributes.
- After a second snapshot, identifying records and source fields that changed
  between observations.

Snapshot differences describe changes in public-layer publication. They do not
by themselves prove that construction started, a project finished, a permit
was cancelled, or a record was deleted.

## Reproduce and validate

The pipeline uses Python's standard library.

```bash
python scripts/build_release.py --use-existing-raw
python -m unittest discover -s tests -v
python scripts/validate_release.py
```

Collect the next live snapshot with:

```bash
python scripts/snapshot_tracker.py collect-live
```

See [`scripts/README.md`](scripts/README.md) for the complete command index and
[`docs/LONGITUDINAL_TRACKER.md`](docs/LONGITUDINAL_TRACKER.md) for snapshot and
comparison semantics.

## Before treating v0.9.0 as a public release

The repository still has two evidence gaps and one distribution gap:

1. Complete the frozen manual-validation sample and publish the resulting
   claim-specific accuracy and reviewer-agreement metrics.
2. Collect a second comparable snapshot to demonstrate the longitudinal
   workflow with an actual comparison.
3. Run the release checks and publish an annotated `v0.9.0` Git tag.

The detailed sequence is in the
[`release checklist`](docs/RELEASE_CHECKLIST.md). Until the first item is
complete, do not claim a measured error rate. Until the second is complete, do
not describe the project as having observed longitudinal results.

## Repository layout

```text
data/raw/             archived privacy-minimized source files
data/processed/       analysis-ready tables and review queues
data/snapshots/       compact immutable observations by date
data/monthly_changes/ machine-readable comparisons and index
docs/                 scope, methods, validation, and release guidance
scripts/              acquisition, transformation, tracking, and QA
tests/                deterministic workflow tests
```

## Citation and license

> Lenga, Jack. *Tampa Published Development Records: Source-Bounded
> Longitudinal Tracker*, version 0.9.0, 2026.

Code and original documentation are MIT-licensed. City records remain subject
to their source terms; see [`DATA_LICENSE.md`](DATA_LICENSE.md). AI-assistance
details are recorded in [`docs/AI_USE_STATEMENT.md`](docs/AI_USE_STATEMENT.md).
