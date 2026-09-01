# Tampa Published Development Records

A reproducible archive of development-related records published by the City
of Tampa, with tools for tracking changes in those records over time.

## Status

This is a strong baseline with an initial observed comparison, not yet a
validated full-month longitudinal result.

| Item | Current state |
| --- | --- |
| Core release snapshot | August 23, 2026 |
| Core release records | 4,469 records from eight City GIS layers |
| Normalized activities | 3,323 |
| Accela records | 56,245 unique Building/Planning records; 52,264 retrospective and 3,981 prospective |
| Expanded activities | 57,677; core bounded-census files remain unchanged |
| Source-date cohort view | 4,469 source records; 4,387 non-future monthly events; 81 forward-looking plans |
| Longitudinal snapshots | August 23 baseline; September 1 first follow-up |
| Latest observed records | 3,701 records from eight City GIS layers |
| Observed comparisons | 1; August 23 to September 1 (nine-day initial interval) |
| Regular month-end series | Begins September 30, 2026 |
| Manual validation | 0 of 150 first reviews completed |
| Empirical accuracy | Not yet measured |
| Release | Version 0.9.0 prepared; Git tag not yet published |

The dataset is complete only with respect to the records returned by the eight
named layers at the recorded retrieval time. It is not a complete inventory of
Tampa permits, developments, construction outcomes, or investment.

### Archived core observations

| Snapshot | Retrieved (UTC) | Records | Role | Documentation |
| --- | --- | ---: | --- | --- |
| [`2026-08-23`](data/snapshots/2026-08-23/) | 2026-08-23 02:06:02 | 4,469 | Original baseline | [Metadata](data/snapshots/2026-08-23/metadata.json) |
| [`2026-09-01`](data/snapshots/2026-09-01/) | 2026-09-01 04:34:12 | 3,701 | First follow-up | [Metadata](data/snapshots/2026-09-01/metadata.json) |

The first observed comparison covers August 23 to September 1 and is a
nine-day initial interval, not a full monthly interval. Its
[`change summary`](data/monthly_changes/2026-09.json) and
[`readable report`](reports/2026-09.md) are archived with the snapshots.

## Verification Status — 2026-08-23 snapshot

<!-- verification-scorecard:start -->
Coverage says how many eligible records were evaluated. Results describe only
those evaluated records; they are not a dataset-wide accuracy percentage.

| Verification layer | Coverage / progress | Result among evaluated | What it establishes |
| --- | ---: | --- | --- |
| Automated QA | 4,469 / 4,469 (100.0%) | 14 checks passed; 0 checks flagged | Structural, relationship, range, consistency, privacy, and release-integrity checks |
| Source traceability | 4,469 / 4,469 (100.0%) | 4,469 reconciled; 0 conflicting | Fidelity to the eight archived City source layers, not necessarily real-world truth |
| Automated evidence checks | Not measured | Not measured | No separate software system currently checks external supporting evidence |
| Manual validation sample | 0 / 150 (0.0%) | No claim outcomes yet | Human application of the frozen, documented validation protocol |
| External outcome verification | 12 / 12 historical pilot rows | 1 work documented; 3 partial; 7 not established; 1 not applicable | Limited cited evidence about physical realization; not a representative estimate |
| Double review | 0 / 50 (0.0%) | No agreement result yet | Independent, blinded second-review coverage |

**Release-level status:** Automated QA 4,469 / 4,469; source traceability
4,469 / 4,469; automated evidence `Not measured`; manual validation 0 / 150;
external outcome pilot 12 / 12; double-reviewed 0 / 50; validation study
`IN PROGRESS`.

```text
Manual validation sample
150 selected
|
+-- Reviewed ............... 0
|   `-- Claim outcomes ..... Not measured
|
`-- Awaiting review ....... 150
```
<!-- verification-scorecard:end -->

The manual study is a frozen, seeded stratified probability sample of normalized
activities: 100 development rows and a separately drawn 50-row holdout. It was
not selected based on evidence availability. However, no reviews are complete,
so it currently supports no accuracy estimate. The older 12-row pilot was
selected partly because evidence was available. Its coverage and outcomes are
verification progress only and must not be interpreted as dataset-wide
accuracy. Even after partial review, outcomes must not be generalized until the
documented sampling design and completion rules support that inference.

Definitions and reproducible counts are in
[`verification/verification_summary.csv`](verification/verification_summary.csv)
and [`verification/README.md`](verification/README.md). Record-level assignments,
outcomes, evidence URLs or document references, methods, timestamps, reviewer
codes, and second-review status remain in the
[`data/processed/manual_validation_*.csv`](data/processed/) files.

### What each layer means

- **Automated QA** tests machine-checkable schema, identifiers, relationships,
  dates, coordinates, counts, transformations, hashes, and privacy rules. A pass
  does not prove a project exists physically, started, finished, or is factually
  correct in every source field.
- **Source traceability / reconciliation** connects a retained TDR row to its
  identified published source and checks snapshot fidelity. It establishes
  fidelity to that source, not real-world truth.
- **Automated evidence verification** would reproducibly test claims against
  supporting evidence. The repository has no distinct check of this kind, and
  automated QA passes are not called external verification.
- **Manual review** means a human completed the documented protocol, cited
  evidence, and recorded claim-specific outcomes. Empty assignments are not
  reviewed records.
- **External outcome verification** examines real-world claims such as work
  started or completed, certificates of occupancy, final inspections,
  cancellation, and completion dates. `unknown` and `not_applicable` remain
  valid outcomes rather than being forced to yes/no.
- **Double review** means an independent second reviewer completed the same
  blinded protocol. Ordinary automated checks never count as a second review.

## Start here

| Goal | File |
| --- | --- |
| Analyze every published source record | [`data/processed/bounded_census_records.csv`](data/processed/bounded_census_records.csv) |
| Use the consolidated activity view | [`data/processed/tampa_development_activity.csv`](data/processed/tampa_development_activity.csv) |
| Use the expanded activity view with Accela data | [`data/integrated/tampa_development_activity_with_accela.csv`](data/integrated/tampa_development_activity_with_accela.csv) |
| Use linked Accela inspection events | `data/processed/accela_inspections.csv` (generated one-to-many table) |
| Analyze the canonical source-date table | [`data/processed/activity_by_month.csv`](data/processed/activity_by_month.csv) |
| Analyze non-future monthly events | [`data/monthly_events/`](data/monthly_events/) |
| Analyze forward-looking source plans | [`data/planned_events/`](data/planned_events/) |
| Inspect source coverage | [`data/processed/source_universes.csv`](data/processed/source_universes.csv) |
| Review the latest core snapshot | [`data/snapshots/2026-09-01/`](data/snapshots/2026-09-01/) |
| Review the initial observed comparison | [`reports/2026-09.md`](reports/2026-09.md) |
| Complete manual validation | [`docs/MANUAL_VALIDATION_GUIDE.md`](docs/MANUAL_VALIDATION_GUIDE.md) |
| Collect bounded public Accela records | [`docs/ACCELA_COLLECTOR.md`](docs/ACCELA_COLLECTOR.md) |
| Understand Accela analytical limitations | [`docs/ACCELA_LIMITATIONS.md`](docs/ACCELA_LIMITATIONS.md) |
| Navigate all documentation | [`docs/README.md`](docs/README.md) |

## What the dataset supports

- Reproducing the state of eight City GIS layers on August 23 and September 1,
  2026.
- Mapping and filtering the published records.
- Studying overlap among permit, planning, preservation, and capital-project
  layers.
- Tracing normalized activities back to source records and attributes.
- Analyzing source-reported event months separately from TDR observation
  months, with explicit date-type and planned-date flags.
- Identifying records and source fields that changed between archived
  observations. Prospective longitudinal tracking began August 23, 2026; the
  first observed comparison is August 23 to September 1. Regular month-end
  observations begin September 30, 2026.

Snapshot differences describe changes in public-layer publication. They do not
by themselves prove that construction started, a project finished, a permit
was cancelled, or a record was deleted.

## Reproduce and validate

The core release pipeline uses Python's standard library. The optional Accela
collector requires `requests` from `requirements.txt`.

The historical analytical scope begins on January 1, 2020. Automated Accela
date-range collection and monthly backfills reject earlier start dates, and
the temporal cohort outputs exclude known event dates before the boundary.
Immutable source snapshots remain intact as provenance and may therefore carry
older source attributes that are not published as in-scope monthly events.

```bash
python scripts/build_release.py --use-existing-raw
python -m unittest discover -s tests -v
python scripts/validate_release.py
```

Plan or run a bounded anonymous Accela collection with:

```bash
python -m pip install -r requirements.txt
python scripts/collect_accela.py --module Building --from-date 2026-08-13 --to-date 2026-08-13 --dry-run
python scripts/collect_accela.py --module Building --from-date 2026-08-13 --to-date 2026-08-13 --max-records 25
python scripts/collect_accela.py --module Building --from-date 2026-08-01 --to-date 2026-08-31 --use-export
python scripts/backfill_accela.py --from-month 2025-08 --to-month 2026-07
python scripts/validate_accela_backfill.py
```

Collect the linked inspection history for the August 2025–August 2026 cohorts
with `python scripts/backfill_accela_inspections.py --from-month 2025-08
--to-month 2026-08`. The job is monthly, resumable, rate-limited, and stores
raw HTML with gzip compression. Validate identity, parent links, duplicates,
and checkpoint coverage with `python scripts/validate_accela_inspections.py
--require-complete`.

Integrate the collected Accela snapshot without duplicating exact public record
numbers:

```bash
python scripts/integrate_accela.py
```

The August 2025 through July 2026 backfill is retrospective: Tampa currently
reports those older event dates, but TDR did not take contemporaneous snapshots
in those months. Prospective Accela observation begins in August 2026. The
August 31 Accela day-freeze is preserved separately from the core GIS
observation retrieved just after midnight on September 1; neither is relabeled.

See [`data/integrated/README.md`](data/integrated/README.md) for duplicate rules
and the boundary between the expanded view and the eight-layer bounded census.

Collect the next live snapshot with:

```bash
python scripts/snapshot_tracker.py collect-live
```

See [`scripts/README.md`](scripts/README.md) for the complete command index and
[`docs/LONGITUDINAL_TRACKER.md`](docs/LONGITUDINAL_TRACKER.md) for snapshot and
comparison semantics. See [`docs/TEMPORAL_COHORTS.md`](docs/TEMPORAL_COHORTS.md)
before combining monthly records across sources or date types.

## Before treating v0.9.0 as a public release

The repository still has one evidence gap, one longitudinal maturity gap, and
one distribution gap:

1. Complete the frozen manual-validation sample and publish the resulting
   claim-specific accuracy and reviewer-agreement metrics.
2. Collect the September 30 snapshot to establish the first canonical
   month-end observation; the first full month-end-to-month-end interval will
   be September 30 to October 31.
3. Run the release checks and publish an annotated `v0.9.0` Git tag.

The detailed sequence is in the
[`release checklist`](docs/RELEASE_CHECKLIST.md). Until the first item is
complete, do not claim a measured error rate. Until the second is complete,
describe August 23 to September 1 only as an initial short-interval comparison,
not a full monthly result.

## Repository layout

```text
data/raw/             archived privacy-minimized source files
data/processed/       analysis-ready tables and review queues
data/integrated/      optional duplicate-safe expanded activity editions
data/snapshots/       compact immutable observations by date
data/monthly_changes/ machine-readable comparisons and index
data/monthly_events/ non-future source-date extracts and index
data/planned_events/ forward-looking source-plan extracts and index
docs/                 scope, methods, validation, and release guidance
scripts/              acquisition, transformation, tracking, and QA
src/tampa_accela/     optional public ACA collector package
tests/                deterministic workflow tests
```

## Citation and license

> Lenga, Jack. *Tampa Published Development Records: Source-Bounded
> Longitudinal Tracker*, version 0.9.0, 2026.

Code and original documentation are MIT-licensed. City records remain subject
to their source terms; see [`DATA_LICENSE.md`](DATA_LICENSE.md). AI-assistance
details are recorded in [`docs/AI_USE_STATEMENT.md`](docs/AI_USE_STATEMENT.md).
