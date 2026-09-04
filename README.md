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
| Accela records | 338,789 unique Building/Planning records; 334,808 retrospective and 3,981 prospective |
| Expanded activities | 339,179; core bounded-census files remain unchanged |
| Source-date cohort view | 4,549 canonical records; 4,464 non-future monthly events; 84 forward-looking plans |
| Longitudinal snapshots | August 23 baseline; September 1 first follow-up |
| Latest observed records | 4,408 records from eight City GIS layers |
| Observed comparisons | 1; August 23 to September 1 (nine-day initial interval) |
| Regular month-end series | Begins September 30, 2026 |
| Manual validation | 10 of 150 first reviews completed (6.7%); development phase only |
| Empirical accuracy | Not yet measured |
| Release | Version 0.9.0 prepared; Git tag not yet published |

The dataset is complete only with respect to the records returned by the eight
named layers at the recorded retrieval time. It is not a complete inventory of
Tampa permits, developments, construction outcomes, or investment.

### Archived core observations

| Snapshot | Retrieved (UTC) | Records | Role | Documentation |
| --- | --- | ---: | --- | --- |
| [`2026-08-23`](data/snapshots/2026-08-23/) | 2026-08-23 02:06:02 | 4,469 | Original baseline | [Metadata](data/snapshots/2026-08-23/metadata.json) |
| [`2026-09-01`](data/snapshots/2026-09-01/) | 2026-09-01 07:15:12 | 4,408 | Reconciled first follow-up | [Metadata](data/snapshots/2026-09-01/metadata.json) |

The first observed comparison covers August 23 to September 1 and is a
nine-day initial interval, not a full monthly interval. Its
[`change summary`](data/monthly_changes/2026-09.json) and
[`readable report`](reports/changes/2026-09.md) are archived with the snapshots. The
[`change dashboard`](reports/dashboard/index.html) and
[`analysis documentation`](docs/methodology/CHANGE_DASHBOARD.md) flag unusually large
source shifts before they are interpreted substantively.

The accepted September 1 observation passed repeated count-only, ID-only,
chunked-feature, and final-count reconciliation for all eight sources. It
supersedes an incomplete same-day capture containing only 280 permit records;
the replacement provenance and prior content hash remain documented in the
snapshot metadata.

## Verification Status — 2026-08-23 snapshot

<!-- verification-scorecard:start -->
Validation results apply only to the stated sampling universe and validation
layer. Source fidelity, transformation validity, and real-world outcome validity
are separate claims. No composite verification score is calculated.

### Core eight-layer verification

The frozen 150-row core sample was selected before the Accela expansion and has
not been redrawn from the expanded dataset.

| Validation layer | Coverage / progress | Result among evaluated | What it establishes |
| --- | ---: | --- | --- |
| Automated QA — core release | 4,469 / 4,469 (100.0%) | 14 checks passed; 0 checks flagged | Structural and release-integrity checks |
| Core source traceability | 4,469 / 4,469 (100.0%) | 4,469 reconciled; 0 conflicting | Fidelity to the eight archived City layers, not real-world outcomes |
| Core eight-layer manual validation | 10 / 150 (6.7%) | Exploratory partial results only | Claim-specific review of the original normalized/core universe only |
| Core external outcome verification | 12 / 12 historical pilot rows | 1 documented; 3 partial; 7 not established; 1 not applicable | Evidence-selected pilot, not a population estimate |
| Core reviewer reliability | 0 / 25 (0.0%) | Not measured | Independent blinded review of the active 25-row subset |

### Expanded Accela verification

| Validation layer | Coverage / progress | Result among evaluated | What it establishes |
| --- | ---: | --- | --- |
| Accela collection integrity | 158 / 158 (100.0%) | 158 module-month partitions passed | Retrieval completeness and reconciliation, not semantic or outcome accuracy |
| Targeted Accela manual audit | 0 / 75 (0.0%) | Not measured | Risk-focused source fidelity, normalization, and linkage checks; no global accuracy estimate |
| Expanded external outcome verification | Not measured | Not measured | Whether external evidence establishes real-world activity |

### Longitudinal verification

| Validation layer | Coverage / progress | Result among evaluated | What it establishes |
| --- | ---: | --- | --- |
| Initial longitudinal change audit | 0 / 30 (0.0%) | Not measured | High-impact changes plus controls; source-publication changes rather than physical outcomes |
<!-- verification-scorecard:end -->

The active plan retains the frozen, seeded 150-row core probability sample and
pools its historical development and holdout phases for final analysis. Ten
first reviews are complete; the other 140 first reviews and all 25 active blind
reliability reviews remain unfinished. A separate 75-case targeted Accela audit
and 30-case initial longitudinal audit also remain unreviewed. These partial
results are exploratory only, so the repository still supports no empirical
accuracy estimate. The older 12-row pilot was selected partly because evidence
was available and remains descriptive only.

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
| Explore the data in a public notebook | [`notebooks/tampa_development_exploration.ipynb`](notebooks/tampa_development_exploration.ipynb) |
| Audit all upstream sources and provenance | [`docs/reference/SOURCES.md`](docs/reference/SOURCES.md) |
| Analyze every published source record | [`data/processed/bounded_census_records.csv`](data/processed/bounded_census_records.csv) |
| Use the consolidated activity view | [`data/processed/tampa_development_activity.csv`](data/processed/tampa_development_activity.csv) |
| Use the expanded activity view with Accela data | [`data/integrated/tampa_development_activity_with_accela.csv.gz`](data/integrated/tampa_development_activity_with_accela.csv.gz) |
| Verify expanded-edition hashes and counts | [`data/integrated/manifest.json`](data/integrated/manifest.json) |
| Use linked Accela inspection events | `data/processed/accela_inspections.csv` (generated one-to-many table) |
| Analyze the canonical source-date table | [`data/processed/activity_by_month.csv`](data/processed/activity_by_month.csv) |
| Analyze non-future monthly events | [`data/monthly_events/`](data/monthly_events/) |
| Analyze forward-looking source plans | [`data/planned_events/`](data/planned_events/) |
| Inspect source coverage | [`data/processed/source_universes.csv`](data/processed/source_universes.csv) |
| Review the latest core snapshot | [`data/snapshots/2026-09-01/`](data/snapshots/2026-09-01/) |
| Review the initial observed comparison | [`reports/changes/2026-09.md`](reports/changes/2026-09.md) |
| Explore snapshot differences | [`reports/dashboard/index.html`](reports/dashboard/index.html) |
| Understand change metrics and alerts | [`docs/methodology/CHANGE_DASHBOARD.md`](docs/methodology/CHANGE_DASHBOARD.md) |
| Complete manual validation | [`docs/guides/MANUAL_VALIDATION_GUIDE.md`](docs/guides/MANUAL_VALIDATION_GUIDE.md) |
| Review the bounded agent evidence experiment | [`docs/validation/AGENTIC_VALIDATION.md`](docs/validation/AGENTIC_VALIDATION.md) |
| Collect bounded public Accela records | [`docs/guides/ACCELA_COLLECTOR.md`](docs/guides/ACCELA_COLLECTOR.md) |
| Understand Accela analytical limitations | [`docs/reference/ACCELA_LIMITATIONS.md`](docs/reference/ACCELA_LIMITATIONS.md) |
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
  observations. The first comparison spans August 23 through September 1,
  2026 and is treated as a short baseline follow-up rather than a full monthly
  interval. Regular month-end observations begin September 30, 2026.

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
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python scripts/build_release.py --use-existing-raw
python -m pytest -q
python scripts/validate_release.py
```

For the publication-grade, offline reproducibility workflow—including frozen
input protection, versioned rule traceability, environment and command capture,
output hashes, and an automatic repeat-run comparison—use:

```bash
python scripts/run_automated_validation.py --all --offline
```

The validator was developed with AI assistance, but no AI model is called by
this automated validation command. The complete implementation prompt and
available AI-development metadata are archived in
[`reproducibility/`](reproducibility/README.md). Reported automated results are
reproduced from the code, rules, frozen evidence, and dependencies rather than
by asking an AI system to regenerate or rejudge them. Live-source checks remain
mutable and are explicitly separate from the preferred offline workflow.

A separate experimental agentic layer has investigated an 18-case benchmark
and archived candidate evidence without changing the dataset or human-review
fields. Reproduce its deterministic audit with `python
scripts/run_agentic_validation.py --study core --repeat 3
--allow-recorded-live`; see the [agentic validation
guide](docs/validation/AGENTIC_VALIDATION.md) and the separate
[`AGENTIC_VALIDATION_REPORT`](reports/AGENTIC_VALIDATION_REPORT.md). Its metrics
measure the evidence investigator, not dataset accuracy.

Plan or run a bounded anonymous Accela collection with:

```bash
python -m pip install -r requirements.txt
python scripts/collect_accela.py --module Building --from-date 2026-08-13 --to-date 2026-08-13 --dry-run
python scripts/collect_accela.py --module Building --from-date 2026-08-13 --to-date 2026-08-13 --max-records 25
python scripts/collect_accela.py --module Building --from-date 2026-08-01 --to-date 2026-08-31 --use-export
python scripts/backfill_accela.py --from-month 2020-01 --to-month 2025-07
python scripts/validate_accela_backfill.py --from-month 2020-01 --to-month 2026-07
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

The January 2020 through July 2026 backfill is retrospective: Tampa currently
reports those older event dates, but TDR did not take contemporaneous snapshots
in those months. The dataset boundary prevents record backfills before January
2020. Prospective Accela observation begins in August 2026. The
August 31 Accela day-freeze is preserved separately from the core GIS
observation retrieved at 3:15 a.m. Tampa time on September 1; neither is
relabeled.

See [`data/integrated/README.md`](data/integrated/README.md) for duplicate rules
and the boundary between the expanded view and the eight-layer bounded census.

Collect the next live snapshot with:

```bash
python scripts/snapshot_tracker.py collect-live
```

See [`scripts/README.md`](scripts/README.md) for the complete command index and
[`docs/methodology/LONGITUDINAL_TRACKER.md`](docs/methodology/LONGITUDINAL_TRACKER.md) for snapshot and
comparison semantics. See [`docs/methodology/TEMPORAL_COHORTS.md`](docs/methodology/TEMPORAL_COHORTS.md)
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
[`release checklist`](docs/guides/RELEASE_CHECKLIST.md). Until the first item is
complete, do not claim a measured error rate. Until the second is complete,
describe August 23 to September 1 only as an initial short-interval comparison,
not a full monthly result.

## Repository layout

```text
config/               machine-readable pipeline and validation rules
data/                 source archives, derived tables, snapshots, and cohorts
docs/guides/          task-oriented operating and review instructions
docs/methodology/     analytical scope, semantics, and methods
docs/reference/       dictionaries, limitations, licensing, and provenance
docs/validation/      protocols and validation interpretation
prompts/              versioned prompts used by the agent experiment
notebooks/            public, reproducible data explorations
reports/              generated dashboards, comparisons, and validation output
reproducibility/      frozen runs, manifests, prompts, and environment records
scripts/              command-line acquisition, build, analysis, and QA tools
src/                  reusable Accela and validation packages
tests/                deterministic workflow tests
verification/         study register, assignments, and summary tables
```

## Citation and license

> Lenga, Jack. *Tampa Published Development Records: Source-Bounded
> Longitudinal Tracker*, version 0.9.0, 2026.

Code and original documentation are MIT-licensed. City records remain subject
to their source terms; see [`DATA_LICENSE.md`](DATA_LICENSE.md). AI-assistance
details are recorded in [`docs/reference/AI_USE_STATEMENT.md`](docs/reference/AI_USE_STATEMENT.md).
