# Documentation guide

The root README is intentionally brief. Use this index to find the detailed
scope, methodology, validation, and release material.

## Current blockers

1. **Manual validation is incomplete.** None of the 150 first-review rows or 50
   blind second-review assignments has been completed. Start with the
   [operator guide](MANUAL_VALIDATION_GUIDE.md).
2. **The tracker does not yet have a full monthly interval.** The August 23 to
   September 1 comparison is a nine-day initial interval. The canonical
   month-end series begins September 30. See the [tracker methodology](LONGITUDINAL_TRACKER.md).
3. **Version 0.9.0 is not tagged.** The metadata is prepared, but the repository
   does not yet have an annotated release tag. See the
   [release checklist](RELEASE_CHECKLIST.md).

## Dataset scope

- [Accela limitations](ACCELA_LIMITATIONS.md) - retrospective timing,
  coverage comparability, module imbalance, administrative outcomes, census
  boundaries, and unfinished manual validation.

- [Source scope](BOUNDED_CENSUS_SCOPE.md) — included layers, record counts,
  completeness boundary, and priority coverage gaps.
- [Data dictionary](data_dictionary.csv) — field-level definitions for the
  processed outputs.
- [Known limitations](KNOWN_LIMITATIONS.md) — claims the data cannot support.
- [Source and redistribution notes](LICENSE_NOTES.md) — provenance and source
  licensing considerations.
- [Public-records request](PUBLIC_RECORDS_REQUEST.md) — request specification
  for missing official lifecycle records.

## Methods

- [Tampa Accela collector](ACCELA_COLLECTOR.md) — verified anonymous search
  flow, safe operating commands, provenance, limitations, and GIS crosswalk.

- [Longitudinal tracker](LONGITUDINAL_TRACKER.md) — snapshot identity,
  comparison semantics, outputs, and operating commands.
- [Snapshot-change dashboard](CHANGE_DASHBOARD.md) — metrics, alert thresholds,
  interval classification, trend eligibility, static outputs, and limitations.
- [Source-date monthly events and plans](TEMPORAL_COHORTS.md) — canonical dates,
  non-future monthly extracts, forward-looking plans, observation months,
  source-specific date rules, and valid uses.
- [Ground-truth methodology](GROUND_TRUTH_METHODOLOGY.md) — evidence grades and
  restrictions on inferred outcomes.
- [Context modules](CONTEXT_MODULES.md) — capital-budget, parcel, and building
  context kept outside the bounded-census count.

## Validation

- [Manual-validation operator guide](MANUAL_VALIDATION_GUIDE.md) — the shortest
  path for reviewers completing the frozen sample.
- [Manual-validation protocol](MANUAL_VALIDATION_PROTOCOL.md) — controlling
  definitions, sampling design, and decision rules.
- [Verification notes](VERIFICATION_REPORT.md) — automated and external checks
  already performed.
- [`validation_report.json`](validation_report.json) — machine-readable release
  integrity results.
- [`validation_study_design.json`](validation_study_design.json) — frozen sample
  design and phase allocation.

## Operations and publication

- [Release checklist](RELEASE_CHECKLIST.md) — validation gates, tagging, and
  publication steps.
- [Script command index](../scripts/README.md) — build, tracking, verification,
  and review-metric commands.
- [AI use statement](AI_USE_STATEMENT.md) — where AI assisted and which work
  still requires human judgment.
