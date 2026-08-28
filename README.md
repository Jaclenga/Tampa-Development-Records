# Tampa Published Development Records

This repository collects development-related records published by the City of Tampa and puts them into a format that's easier to explore, map, and analyze.

The current release (`v0.8.0`) contains **4,469 records from eight City GIS layers**, downloaded on August 23, 2026. Separately dated capital-budget and linked-parcel context modules are excluded from that core count.

This is **not a database of every development in Tampa**. It's a snapshot of the records available through these eight public layers at the time of download.

## What's in the dataset?

The repository starts with eight City of Tampa datasets covering building permits, planning applications, historic-preservation applications, and public capital projects.

| Source | Records | What a record generally represents |
| --- | ---: | --- |
| Construction Inspections | 2,619 | Published building-permit record |
| Single-Family Permits | 1,023 | Single-family permit record |
| Development Coordination | 271 | Planning/development application |
| Historic Preservation | 169 | Historic-preservation application |
| Capital Improvements | 192 | City capital project |
| Citywide Capital Projects — points | 57 | Point location for a capital project |
| Citywide Capital Projects — lines | 101 | Linear capital project |
| Citywide Capital Projects — polygons | 37 | Project area |
| **Total** | **4,469** | **Published source records** |

These records overlap. For example, the same permit can appear in both the Construction Inspections and Single-Family Permits layers.

Where there is a strong identifier connecting records, the build links them together. The 4,469 source records currently resolve to **3,323 normalized activities**, 1,113 of which are represented in more than one source.

Even 3,323 should **not** be interpreted as "3,323 developments." A large development can generate several permits, applications, or projects.

## Why I made this

Tampa publishes useful development information, but it is spread across several GIS services with different schemas and different definitions of what a record represents.

This project brings those sources together while keeping enough provenance to trace records back to where they came from.

The goal is to make it easier to:

- map publicly available development records;
- compare activity across neighborhoods and record types;
- study how Tampa's different development datasets overlap;
- track changes between future snapshots; and
- build better methods for connecting permits, projects, and physical buildings.

The repository deliberately avoids turning uncertain information into facts. A permit does not necessarily mean construction happened, an application does not necessarily mean a project was approved or built, and an estimated project cost is not the same thing as money actually spent.

## Source layers

### Construction Inspections

Despite the name, this layer mainly contains **building-permit records**, not individual inspection results.

The snapshot contains 2,619 records: 1,813 with an `Issued` status and 806 with a `Revision` status. Fields include permit number, project name and description, address, square footage, reported units, neighborhood, status dates, and an Accela link.

A record tells us that the City published a permit with that information. It does not, by itself, prove that construction started or finished.

Source: [City of Tampa Construction Inspections layer](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/30)

### Single-Family Permits

This layer contains permits for new construction and additions involving one- and two-family properties.

It overlaps heavily with Construction Inspections: **999 of its 1,023 records** connect to records in that layer. The remaining 24 currently appear only here.

Because of that overlap, simply adding the two layer counts together would double-count many records.

Source: [City of Tampa Single-Family Permits layer](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/32)

### Development Coordination

This layer contains 271 active planning and land-development applications.

These are records of the **review process**, not necessarily construction. A project can be revised, withdrawn, denied, approved but never built, or eventually appear under separate building permits.

Source: [City of Tampa Development Coordination layer](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/31)

### Historic Preservation

This layer contains 169 applications handled through Tampa's historic-preservation process.

Like Development Coordination, these records show regulatory activity. They do not necessarily mean that demolition, alteration, or other physical work actually occurred.

Source: [City of Tampa Historic Preservation layer](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/33)

### Capital Improvements

This layer contains 192 City capital projects covering areas such as transportation, water, wastewater, stormwater, parks, and public facilities.

It is particularly useful because it includes fields such as project descriptions, funding sources, planned dates, estimated costs, reported actual costs, project phases, and contract numbers.

Estimated cost should not be treated as actual spending or final project cost.

Source: [City of Tampa Capital Projects layer](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjects/FeatureServer/0)

### Citywide Capital Projects

The City also publishes capital projects using separate point, line, and polygon layers.

Those geometries are useful because different projects have different shapes: an intersection improvement might make sense as a point, a road or pipeline as a line, and a park or stormwater project as a polygon.

Some of these records connect to projects in the main Capital Improvements layer, while others currently stand on their own. An unmatched record does not necessarily represent a completely different project—it may simply lack a reliable identifier or matching name.

Sources:

- [Citywide Capital Projects — points](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/0)
- [Citywide Capital Projects — lines](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/1)
- [Citywide Capital Projects — polygons](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/2)

## Main files

If you just want to work with the data, these are the most useful places to start:

- `data/processed/bounded_census_records.csv` — one row for every record downloaded from the eight source layers.
- `data/processed/tampa_development_activity.csv` — consolidated activity-level view after strong cross-source matches are applied.
- `data/processed/source_universes.csv` — source layers, endpoints, download times, record counts, and coverage notes.
- `data/processed/source_records.csv` — retained source attributes and provenance.
- `data/processed/activity_locations.csv` — source geometries and representative coordinates.
- `data/processed/investment_amounts.csv` — estimated and reported actual amounts available for City capital projects.
- `data/processed/development_events.csv` — source observations and explicitly dated lifecycle events, with evidence strength and inference flags.
- `data/processed/capital_budget_book_projects.csv` — separately scoped Budget Book capital-project context.
- `data/processed/capital_budget_book_comparison.csv` — exact project-ID comparison between Budget Book and core capital sources.
- `data/processed/public_finance_events.csv` — typed estimate, actual-cost, and funded-status observations; not an expenditure ledger.
- `data/processed/parcel_activity_links.csv` — proposed activity-to-folio links pending human review.
- `data/processed/parcel_context.csv` — privacy-minimized attributes for linked parcels only.
- `data/processed/master_project_candidates.csv` — possible relationships between activities that have **not** been automatically merged.

There are additional audit and validation tables for building matches, evidence status, manual review, and identifier consolidation.

## Repository layout

```text
data/
  raw/          Archived, privacy-minimized source snapshots
  context/raw/  Separately dated, whitelisted context snapshots
  processed/    Analysis-ready tables and validation samples
  templates/    Input templates for external validation
docs/           Methodology, limitations, dictionaries, and reports
scripts/        Build, import, validation, and analysis commands
tests/          Automated tests for the validation workflow
.cache/         Ignored local download cache (created as needed)
dist/           Ignored release archives (created by the release build)
```

See [`scripts/README.md`](scripts/README.md) for a command-by-command index.

## Rebuilding the dataset

Download the current City data and create a new release:

```bash
python scripts/build_release.py
```

Rebuild `v0.8.0` using the archived raw files:

```bash
python scripts/build_release.py --use-existing-raw
```

Run the validation tools separately:

```bash
python scripts/validate_release.py
python scripts/verify_data_accuracy.py
python scripts/validation_study.py
```

The build downloads every page returned by the configured ArcGIS services, preserves the source geometry, removes configured contact/source-user fields, creates the derived tables, validates keys and counts, and packages the release.

`scripts/verify_data_accuracy.py` goes a step further by tracing census rows back to the archived GeoJSON and checking attributes, geometry, identifiers, dates, extracted amounts, counts, and hashes.

Running it with `--live` also compares the archived record IDs with what the City publishes now:

```bash
python scripts/verify_data_accuracy.py --live
```

A difference in the live check doesn't necessarily mean the archived dataset is wrong. It can simply mean the City's public layer has changed since the snapshot was downloaded.

These checks answer:

> **Did this repository accurately preserve what the source published?**

They do not answer:

> **Did this development actually happen?**

That requires independent evidence.

## Event and context model

Version 0.8.0 makes `development_events.csv` the central longitudinal table.
Every source feature contributes a `source_record_observed` event, and explicit
source fields can contribute filing, hearing, issuance, planning, capital-phase,
planned-date, and reported actual-date events. The table preserves
`activity_id`, source-record lineage, the raw status, normalized stage,
observation time, evidence strength, and whether an interpretation was inferred.

The build does not create final-inspection, occupancy, or construction-
completion events from permits, footprints, planned dates, or capital
`Closeout` labels. Those event types remain reserved for stronger official
lifecycle data.

Two separately scoped context modules add:

- a privacy-minimized Capital Projects Budget Book snapshot and exact-ID
  comparison with core capital records; and
- privacy-minimized parcel attributes for folios already exposed through
  proposed City building-footprint matches.

They do not increase the eight-layer census count. Owner, mailing, contact,
editor, legal-description, and unnecessary free-text fields are excluded. See
[Context modules](docs/CONTEXT_MODULES.md).

## Designed external-validation study

Version 0.8.0 preserves the frozen validation design introduced in the previous
release while extending the event and context tables. Seed `20260823` draws
150 unique activities:
50 permit records, 20 planning records, 10 historic-preservation records, 50
capital projects, and 20 records involved in cross-source merges. One hundred
rows form the development/debugging phase and 50 separately randomized rows
form an untouched final holdout. Fifty assignments are independently reviewed
from a blinded second-review file.

The new review fields test source identity, activity classification,
cross-source linkage, status interpretation, physical-work evidence, and
building-footprint matching separately. Every completed label requires a cited
URL or document and manual confirmation; AI may only help locate candidate
sources.

Human review is still pending, so the repository does not yet report an error
rate. After reviews are entered, development diagnostics and final holdout
metrics are generated separately:

```bash
python scripts/review_metrics.py --phase development
python scripts/review_metrics.py --phase holdout
```

The reports include claim-specific confidence intervals, confusion matrices,
percent agreement, and Cohen's kappa. Start with the
[step-by-step manual validation guide](docs/MANUAL_VALIDATION_GUIDE.md); the
[frozen protocol](docs/MANUAL_VALIDATION_PROTOCOL.md) controls definitions and
statistical design.

## AI use

OpenAI ChatGPT and Codex assisted with code, tests, data profiling, debugging,
and documentation. They did not create the City source records and are not
called by the release build. AI-assisted review is not treated as independent
ground-truth evidence; completed manual-validation rows require a human to open
and confirm the cited evidence. See the full
[AI use statement](docs/AI_USE_STATEMENT.md).

## What you can use it for

Good uses include:

- mapping the records contained in these City datasets;
- comparing permits or applications by type, status, date, or location;
- studying overlap between Tampa's public development datasets;
- creating samples for manual validation;
- analyzing City capital-project information; and
- comparing releases over time to see what was added, removed, or changed.

You should **not** use the current dataset to claim:

- the total amount of development investment in Tampa;
- the total number of developments in Tampa;
- that every issued permit resulted in construction;
- that every project marked `Closeout` is physically complete; or
- that these eight layers contain every relevant City permit or project.

Those questions require additional data and verification.

## Documentation

More detailed methodology is available in `docs/`:

- [Source scope](docs/BOUNDED_CENSUS_SCOPE.md) — exactly what is and isn't included.
- [Known limitations](docs/KNOWN_LIMITATIONS.md) — known weaknesses and interpretation issues.
- [Evidence fields](docs/GROUND_TRUTH_METHODOLOGY.md) — how evidence fields are defined.
- [Context modules](docs/CONTEXT_MODULES.md) — Budget Book and linked-parcel scope, privacy, and interpretation.
- [AI use statement](docs/AI_USE_STATEMENT.md) — scope, limits, validation policy, and accountability for AI assistance.
- [Manual validation guide](docs/MANUAL_VALIDATION_GUIDE.md) — exact review order, data-entry steps, and use of results.
- [Manual validation protocol](docs/MANUAL_VALIDATION_PROTOCOL.md) — process for reviewing uncertain records.
- [Data dictionary](docs/data_dictionary.csv) — field definitions.
- [Validation results](docs/validation_report.json) — automated validation results.
- [Source-fidelity verification](docs/accuracy_verification_report.json) — detailed verification results.

## Citation

> Lenga, Jack. *Tampa Published Development Records: Source-Bounded Census*, version 0.8.0, 2026.

The code and original documentation are licensed under MIT. City records remain subject to their source terms; see [`DATA_LICENSE.md`](DATA_LICENSE.md).
