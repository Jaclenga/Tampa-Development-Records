# Accela dataset limitations

## Purpose

This document defines the principal limitations of the Building and Planning
records collected from Tampa's public Accela Citizen Access interface and added
to the expanded Tampa Development Records dataset. These limitations do not
make the data unusable. They determine which conclusions the data can support
and which conclusions require additional evidence.

The current Accela aggregate contains 56,245 unique records. Of these, 52,264
belong to the retrospective August 2025 through July 2026 backfill, and 3,981
belong to the prospectively monitored August 2026 cohort.

## Summary

| Limitation | Main analytical consequence | Defensible response |
| --- | --- | --- |
| Historical records were retrieved in 2026 | Older event dates are not historical snapshots | Separate event time from observation time |
| Public coverage may change | Count trends can reflect system coverage rather than development | Test comparability before interpreting trends |
| Building dominates Planning | Combined totals primarily describe Building records | Analyze modules separately or report their weights |
| Status is administrative | `Complete`, `Issued`, or `Closed` does not prove physical outcomes | Use inspections, certificates, or other outcome evidence |
| The dataset is not a citywide census | Records absent from the interface are outside the observed universe | Describe results as records returned by the named sources |
| Manual validation is unfinished | Real-world accuracy and error rates are not yet measured | Complete the frozen review sample before accuracy claims |

## 1. Retrospective records are not contemporaneous snapshots

The records opened from 2025-08-01 through 2026-07-31 were collected from the
public Accela system in August 2026. Tampa currently reports that those records
have older event dates, but Tampa Development Records did not observe the
public system when those events originally occurred.

For example, a record can report an April 2026 opening date while its first TDR
observation occurred in August 2026. The opening date is a source-reported
event date. It does not establish what fields, status, or public visibility the
record had in April.

The dataset preserves this distinction with:

- `event_date`: the selected date assigned to the underlying event by the
  source;
- `event_date_type`: the meaning of that selected event date;
- `first_observed_date`: the first UTC date the TDR collector observed the
  record;
- `snapshot_date`: the UTC date of the observation supplying the row;
- `last_observed_date`: the most recent UTC observation;
- `historical_reconstruction`: whether the event predates prospective
  monitoring; and
- `temporal_evidence`: the applicable evidence classification.

Backfilled record rows are labeled `retrospective_source_record`. Records from
the August 2026 monitoring boundary onward can be labeled
`prospective_snapshot`. The separate inspection table uses
`retrospective_event_history` only when Accela exposes an explicit dated
inspection result predating the monitoring boundary. That label means the
event is present in history retrieved later; it is not a contemporaneous
snapshot of the inspection page.

Appropriate claim:

> Tampa's currently available Accela records report 4,618 Building records
> opened in August 2025.

Unsupported claim:

> TDR observed 4,618 Building records in Tampa's public system during August
> 2025.

## 2. Public Accela coverage may change over time

The public interface is an administrative publication system, not a frozen
statistical series. Its apparent coverage can change because of system
migration, retention rules, newly digitized record types, module changes,
reclassification, altered public-access settings, or records that were never
migrated into Accela.

Consequently, a change in annual or monthly record counts can represent a
change in public-system coverage rather than a change in development activity.
This is especially important when extending the backfill farther into the
past, where migration-related sparsity or discontinuities may be larger.

Before interpreting a time trend:

1. compare counts separately by module, record type, and event-date type;
2. look for sudden changes in missingness or category composition;
3. document query boundaries and collection dates;
4. identify apparent system-adoption or migration breakpoints; and
5. avoid growth-rate claims across periods that do not appear comparable.

The 24 completed monthly queries have zero recorded collection gaps and zero
truncation. That establishes integrity for what the public interface returned
to those bounded queries. It does not establish that the interface exposed the
same share of underlying City records in every month.

## 3. Building and Planning are unevenly represented

The retrospective backfill contains 48,960 Building records and 3,304 Planning
records. Building therefore has approximately 14.8 times as many rows as
Planning. A combined count is dominated by Building activity and should not be
interpreted as a balanced measure of the two administrative processes.

The imbalance is not automatically a data defect. Building and Planning serve
different functions, use different record types, and can legitimately produce
very different volumes. The risk comes from pooling them without preserving
their meaning.

Recommended practice:

- analyze Building and Planning separately by default;
- always report module-specific counts alongside any combined total;
- do not treat rows as a representative sample of all Tampa development;
- stratify validation samples and models by module and major record type; and
- use rates or within-module proportions only when the denominator is clearly
  defined.

## 4. Administrative status does not prove physical completion

Fields such as `Issued`, `Approved`, `Complete`, `Closed`, or `Expired` describe
the source system's administrative state. They do not, by themselves, prove
that construction started, work was completed, an inspection passed, a
certificate of occupancy was issued, or the permitted improvement exists.

For that reason, the integration does not convert an Accela `Complete` status
into a physical-completion conclusion. Newly appended Accela activities receive
realization evidence grade `U` and the basis
`accela_administrative_record_only`.

Physical-outcome claims require stronger evidence such as:

- passed final inspections;
- temporary or final certificates of occupancy;
- dated completion or closure events with documented meaning;
- official project completion documentation;
- verified parcel/building change evidence; or
- a documented manual review of authoritative records.

`data/processed/accela_inspections.csv` preserves the explicit inspection type,
result/status, event date, source inspection number, parent record ID, and
observation dates. A passed inspection supports only the scope named by that
inspection. A non-final approval is not treated as final completion, and even
a passed final inspection is not automatically treated as a certificate of
occupancy.

## 5. The dataset is not a complete census of Tampa development

The Accela collection is complete only with respect to the records returned by
the named public Building and Planning queries at collection time. It does not
establish that Tampa publishes every permit, planning application, inspection,
certificate, code-enforcement matter, infrastructure project, private
development, or informal construction activity through those interfaces.

The integrated dataset also contains an eight-layer GIS bounded census. That
claim applies only to the features returned by those eight published layers at
their archived retrieval time. Combining the GIS and Accela records broadens
the observable universe but does not turn it into a citywide census.

Results should therefore use language such as:

> Among records returned by the specified City of Tampa public sources...

Avoid language such as:

> All Tampa development projects...

Counts should not be used as citywide permit totals, total development,
citywide construction starts, or total investment without an appropriate and
independently verified denominator.

## 6. Manual validation is unfinished

Automated checks currently establish schema integrity, date bounds,
relationships, identifier uniqueness, reproducibility, and fidelity to the
collected source files. They do not measure whether the underlying public
record is factually correct or whether an inferred real-world claim is true.

The repository contains a frozen 150-record manual-validation design: 100
development rows and a separate 50-row holdout. At present, 0 of 150 first
reviews and 0 of 50 blind second-review assignments are complete. Therefore:

- no empirical dataset-wide accuracy or error rate has been measured;
- reviewer agreement has not been measured;
- automated test success must not be reported as factual accuracy; and
- the older 12-row evidence pilot cannot be generalized to the full dataset.

The manual protocol requires reviewers to record claim-specific outcomes,
supporting evidence, source references, methods, timestamps, reviewer codes,
and independent second-review results. Accuracy claims should wait until the
documented completion and reporting rules are satisfied.

## Appropriate uses under these limitations

The dataset remains suitable for:

- discovering and filtering records published by the included sources;
- mapping available records while observing privacy guidance;
- describing module- and record-type-specific cohorts;
- examining dates currently reported by Accela;
- identifying possible coverage discontinuities;
- comparing record composition and missingness; and
- building prospective longitudinal evidence from August 2026 onward.

It is not sufficient by itself for claims about citywide development totals,
historical growth rates across incomparable coverage periods, physical
completion, investment totals, or measured real-world accuracy.

## Required reporting language

Analyses using the retrospective backfill should include a statement
substantially equivalent to:

> Records predating August 2026 are retrospective observations retrieved from
> currently available City of Tampa source systems. They should not be
> interpreted as contemporaneous snapshots of what those systems displayed at
> the time. Prospective Accela snapshots begin in August 2026. Results describe
> records returned by the specified public sources and are not a complete
> census of Tampa development.

## Related documentation

- [Accela collector methodology](ACCELA_COLLECTOR.md)
- [Temporal cohort methodology](TEMPORAL_COHORTS.md)
- [General known limitations](KNOWN_LIMITATIONS.md)
- [Manual-validation protocol](MANUAL_VALIDATION_PROTOCOL.md)
- [Manual-validation operator guide](MANUAL_VALIDATION_GUIDE.md)
- [Integrated dataset notes](../data/integrated/README.md)
- [Backfill validation report](../data/integrated/accela_backfill_report.json)
