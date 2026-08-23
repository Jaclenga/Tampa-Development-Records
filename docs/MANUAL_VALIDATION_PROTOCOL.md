# Manual validation protocol

## Frozen protocol

- Protocol version: **1.0.0**
- Frozen before review of the new study sample: **2026-08-23**
- Reproducible random seed: **20260823**
- Unit sampled: one normalized activity in `tampa_development_activity.csv`
- First review: **150 activities**
- Independent second review: **50 activities**

The historical 12-row pilot is not forced into this sample and is not used to
estimate error rates. Any change to the definitions below creates a new
protocol version. Results used to develop or debug a changed rule belong to
the development phase; final performance must be calculated on the holdout
phase without tuning the rule again.

## Sampling design

Selection uses a SHA-256 pseudo-random ranking keyed by the frozen seed,
protocol version, phase, stratum, and activity ID. This is reproducible across
machines and is not based on evidence availability.

The strata are mutually exclusive. Activities represented in more than one
source layer enter `cross_source_merge`; remaining records enter the source
family that generated them.

| Stratum | Development | Holdout | Total | Second-reviewed |
|---|---:|---:|---:|---:|
| Permit | 33 | 17 | 50 | 16 |
| Planning | 13 | 7 | 20 | 6 |
| Historic preservation | 7 | 3 | 10 | 3 |
| Capital project | 34 | 16 | 50 | 19 |
| Cross-source merge | 13 | 7 | 20 | 6 |
| **Total** | **100** | **50** | **150** | **50** |

Each row records its stratum population, phase sample size, inclusion
probability, and inverse-probability weight. `validation_study.py` creates the
sample. Rebuilding with unchanged sampling context preserves populated reviewer
fields; it refuses to remap them if the activity or context changed. `--force`
explicitly discards reviews for a deliberately new versioned study.

## Blinding and phase order

1. Enter first-review results in `manual_validation_development_sample.csv`
   and review those 100 rows first. Use them to diagnose errors and,
   if necessary, revise dataset rules under a new protocol or release version.
2. Freeze all revised rules before opening or entering results in
   `manual_validation_holdout_sample.csv`.
3. The second reviewer works from `manual_validation_second_review.csv` and
   must not open the first-review result columns or receive the first
   reviewer's conclusions.
4. Preserve both original judgments when resolving disagreements. Resolution
   may be reported separately but must not replace agreement calculations.
5. Do not combine development and holdout performance into a final accuracy
   claim. `review_metrics.py` defaults to the holdout phase.

## Review preparation

Before searching, read the dataset values in the row and formulate each claim
being tested. Record evidence that existed at, or can reliably characterize,
the dataset snapshot date. Later evidence may establish what eventually
happened but must not silently be used as evidence of the earlier status.

Acceptable evidence includes:

- City source records, permit/inspection/occupancy records, and project pages;
- official City, county, or property-appraiser records;
- archived official pages with a recorded capture date;
- dated and geolocatable aerial or street imagery;
- official announcements, contract documents, or completion notices; and
- independent institutional or news sources that clearly identify the record.

Third-party aggregators and AI search output may locate candidate sources, but
they are not a substitute for reviewing the underlying evidence. Record all
source categories in `evidence_source_types` and at least one URL or stable
document reference. Set `manual_evidence_confirmed=yes` only after a human has
opened the cited material and confirmed that it supports the labels.

## Shared claim outcomes

Use these values for every `*_result` field:

- `supported`: the cited evidence affirmatively agrees with the dataset claim;
- `contradicted`: the cited evidence affirmatively conflicts with the claim;
- `inconclusive`: available evidence cannot resolve the claim; and
- `not_applicable`: the dataset makes no such claim for this row.

An unsuccessful search is `inconclusive`, never `contradicted` and never
evidence that physical work was absent.

## Field-level decision rules

### Source identity (`source_identity_result`)

`supported` requires a cited source that matches the native identifier, or a
combination of project name, address/location, record type, and relevant date
that uniquely identifies the same record. Use `contradicted` when authoritative
evidence shows the identifier or descriptive attributes refer to a materially
different record. Minor spelling or formatting differences are not
contradictions.

### Activity classification (`activity_classification_result`)

Compare `activity_class` with the work or administrative scope described by
the cited record. `supported` means the normalized class is substantively
correct; `contradicted` means a different class is affirmatively established.
Enter the evidence-based value in `reviewed_activity_class` for supported or
contradicted judgments. Use `inconclusive` when the scope is too vague.

### Cross-source linkage (`cross_source_linkage_result`)

For `cross_source_merge` rows, `supported` requires strong evidence that the
source memberships describe the same administrative activity or capital
project, normally a shared valid identifier or a uniquely matching official
project identity. Use `contradicted` when sources refer to different projects
or activities. Shared address alone is insufficient. For all other strata use
`not_applicable`; this study estimates the precision of applied merges, not
false-negative linkage recall.

### Status interpretation (`status_interpretation_result`)

Compare the normalized `activity_stage` with the meaning of the source status
at the snapshot date. `supported` requires evidence that the normalized stage
faithfully represents the procedural status. `contradicted` requires an
affirmative conflict, such as a withdrawn record labeled active. Enter the
evidence-based stage in `reviewed_activity_stage` for supported or contradicted
judgments. A capital-project `Closeout` label does not by itself establish
physical completion.

### Physical-work evidence (`physical_work_evidence`)

This is an evidence finding, not a generic accuracy label:

- `present`: dated, attributable evidence affirmatively shows physical work
  started by the relevant date;
- `absent`: affirmative evidence establishes that physical work had not
  started or could not occur by that date, such as a documented cancellation
  before mobilization;
- `unknown`: evidence does not resolve whether work started; and
- `not_applicable`: the record is purely administrative and makes no physical
  work claim.

Permit issuance, planning approval, a current footprint, administrative
closeout, or failure to find a source is not enough to code `present` or
`absent`.

### Building-footprint match (`building_footprint_match_result`)

Use `not_applicable` when the row has no match method. `supported` requires the
matched footprint to be the same physical building implicated by the activity,
using geometry, address, parcel context, and imagery or property records as
appropriate. `contradicted` requires evidence that a different building was
matched. Proximity alone does not establish correctness. Use `inconclusive`
when multi-building parcels or missing historical context prevent a decision.

## Completing a review row

A row is `complete` only when all claim outcomes, physical-evidence category,
reviewer ID, timestamps, evidence-source types, notes, AI-use disclosure, and
manual confirmation are populated, and at least one evidence URL or stable
document reference is recorded. `review_metrics.py` enforces these gates.

Use ISO 8601 UTC timestamps. Do not put personal contact information in notes.

## Analysis and reporting

Run development diagnostics only while rules may still change:

```bash
python review_metrics.py --phase development
```

After rules are frozen and holdout review is complete, run final validation:

```bash
python review_metrics.py --phase holdout
```

The report keeps source identity, activity classification, cross-source
linkage, status interpretation, physical-work evidence, and building-footprint
matching separate. It reports numerators, denominators, Wilson 95% confidence
intervals, approximate design-weighted intervals, classification/stage
confusion matrices, percent agreement, and Cohen's kappa. Inconclusive and
not-applicable results remain visible but are excluded from precision
denominators.

Until the human reviews are complete, the correct project statement is:

> External validation has a preregistered, reproducible stratified sample of
> 150 records, including a 50-record holdout and 50 independently assigned
> second reviews. Accuracy and agreement estimates remain pending human review.
