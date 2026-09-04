# Documentation

Documentation is organized by what a reader is trying to do. Generated JSON
and HTML are kept in [`reports/`](../reports/README.md), separate from the
hand-maintained explanations in this directory.

## Start here

| Need | Document |
| --- | --- |
| Audit source endpoints, roles, dates, and retrieval methods | [Source inventory and provenance](reference/SOURCES.md) |
| Understand what the dataset includes | [Bounded census scope](methodology/BOUNDED_CENSUS_SCOPE.md) |
| Use the longitudinal outputs correctly | [Longitudinal tracker](methodology/LONGITUDINAL_TRACKER.md) |
| Collect public Accela records | [Accela collector guide](guides/ACCELA_COLLECTOR.md) |
| Complete a manual review | [Manual-validation guide](guides/MANUAL_VALIDATION_GUIDE.md) |
| Interpret the validation evidence | [Verification report](validation/VERIFICATION_REPORT.md) |
| Understand the active review design | [Lean validation plan](validation/LEAN_VALIDATION_PLAN.md) |
| Prepare a release | [Release checklist](guides/RELEASE_CHECKLIST.md) |
| Look up fields | [Data dictionary](reference/data_dictionary.csv) |
| Review limitations | [Known limitations](reference/KNOWN_LIMITATIONS.md) and [Accela limitations](reference/ACCELA_LIMITATIONS.md) |

## Sections

### `guides/`

Task-oriented instructions for collection, manual review, records requests,
and release publication.

- [Accela collector](guides/ACCELA_COLLECTOR.md)
- [Manual-validation operator guide](guides/MANUAL_VALIDATION_GUIDE.md)
- [Public-records request](guides/PUBLIC_RECORDS_REQUEST.md)
- [Release checklist](guides/RELEASE_CHECKLIST.md)

### `methodology/`

Definitions, analytical boundaries, temporal semantics, and transformation
methods.

- [Bounded census scope](methodology/BOUNDED_CENSUS_SCOPE.md)
- [Change dashboard](methodology/CHANGE_DASHBOARD.md)
- [Context modules](methodology/CONTEXT_MODULES.md)
- [Ground-truth methodology](methodology/GROUND_TRUTH_METHODOLOGY.md)
- [Longitudinal tracker](methodology/LONGITUDINAL_TRACKER.md)
- [Temporal cohorts](methodology/TEMPORAL_COHORTS.md)

### `reference/`

Field definitions, known limitations, licensing notes, and disclosure
statements.

- [Accela limitations](reference/ACCELA_LIMITATIONS.md)
- [AI use statement](reference/AI_USE_STATEMENT.md)
- [Data dictionary](reference/data_dictionary.csv)
- [Known limitations](reference/KNOWN_LIMITATIONS.md)
- [License notes](reference/LICENSE_NOTES.md)
- [Source inventory and provenance](reference/SOURCES.md)

### `validation/`

Validation protocols, evidence-layer documentation, and interpretation of
completed checks.

- [Agentic evidence validation](validation/AGENTIC_VALIDATION.md)
- [Lean manual-validation plan](validation/LEAN_VALIDATION_PLAN.md)
- [Manual-validation protocol](validation/MANUAL_VALIDATION_PROTOCOL.md)
- [Verification report](validation/VERIFICATION_REPORT.md)

## Current release blockers

1. Manual validation is incomplete: 10 of 150 core first reviews are complete;
   the 25 reliability, 75 targeted Accela, and 30 longitudinal cases remain.
2. The tracker has a nine-day initial comparison, not yet a full
   month-end-to-month-end interval.
3. Version 0.9.0 metadata is prepared, but the annotated release tag has not
   been published.

See the [release checklist](guides/RELEASE_CHECKLIST.md) for the controlling
sequence and gates.
