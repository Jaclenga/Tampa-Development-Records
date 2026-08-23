# Tampa Published Development Records

This repository contains a snapshot of eight development-related GIS layers
published by the City of Tampa. Version 0.6.1 includes all 4,469 features
returned by those layers when they were downloaded on August 23, 2026.

The dataset is complete for the named layer snapshots. It is not a complete
export of Tampa's permitting system or an inventory of every development in
the city.

## Contents

The main files are:

- `source_universes.csv` — layer names, endpoints, download time, record
  counts, and coverage notes.
- `bounded_census_records.csv` — one row per feature returned by the eight
  layers, including geometry and selected source attributes.
- `bounded_census_summary.csv` — release-level counts and scope.
- `source_records.csv` — source attributes in relational form.
- `activity_locations.csv` — one row per source geometry.

The repository also includes derived tables for normalized activities,
possible project relationships, building-footprint matches, reported costs,
and evidence status. These are analytical outputs rather than source-census
units.

## Source layers

The release contains eight City layers. A feature is one row returned by a
layer, not necessarily one development. The layers contain 4,469 features but
produce 3,323 normalized activities after documented cross-layer connections.

| Layer | Features | Unit represented by one feature |
|---|---:|---|
| Construction Inspections | 2,619 | Published building-permit record |
| Single-Family Permits | 1,023 | Published single-family permit record |
| Development Coordination | 271 | Planning or development-review application |
| Historic Preservation | 169 | Historic-preservation application |
| Capital Improvements | 192 | City capital project represented by a point |
| Citywide Capital Projects — points | 57 | Point-shaped capital-project location |
| Citywide Capital Projects — lines | 101 | Line-shaped capital-project location |
| Citywide Capital Projects — polygons | 37 | Area-shaped capital-project location |
| **Total** | **4,469** | **Published features, not unique developments** |

### Construction Inspections

This point layer contains selected building-permit records. Despite the layer
name, its features are not individual inspection results. The snapshot has
1,813 records with an `Issued` status and 806 with a `Revision` status.

Available fields include permit number, record type, project name and
description, address, reported new-construction square footage, reported
units, neighborhood, CRA, council district, status dates, and an Accela URL.
The layer covers residential and commercial new construction, additions,
alterations, and demolitions.

A feature establishes that the City published the permit record and its
reported status. It does not establish that an inspection passed, construction
started, or construction finished. It is also not a complete historical export
of every Tampa permit.

Source: [City of Tampa Construction Inspections layer](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/30)

### Single-Family Permits

This point layer contains residential new-construction and addition permits for
one- and two-family properties. It includes application status, workflow task
fields, opened and task dates, address, neighborhood, CRA, council district,
and Accela identifier components.

The layer substantially overlaps Construction Inspections: 999 of its 1,023
features connect to records in that layer, while 24 normalized activities come
only from this layer. These features must not be added to the Construction
Inspections count as if they were independent developments. The record type
also combines new construction and additions, so a feature does not necessarily
represent a new house or a net new housing unit.

Source: [City of Tampa Single-Family Permits layer](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/32)

### Development Coordination

This point layer contains active planning and land-development applications.
The snapshot has 206 `In Process`, 51 `Awaiting Client Reply`, and 14 `Open`
records. Available fields include the planning record identifier, application
type, address, tentative hearing information, neighborhood, CRA, council
district, status, and source URL.

These records describe regulatory review rather than construction. An
application can be revised, withdrawn, denied, approved but never built, or
followed by separate permits. The layer should not be counted as completed
development or investment without additional evidence.

Source: [City of Tampa Development Coordination layer](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/31)

### Historic Preservation

This point layer contains applications handled through Tampa's
historic-preservation process. The snapshot has 110 `Awaiting Client Reply`,
51 `In Process`, and 8 `Open` records. Fields include the record identifier,
application type, address, tentative hearing information, neighborhood, CRA,
council district, status, and source URL.

These features are evidence of regulatory activity affecting a historic
resource. They are not evidence that alteration, demolition, or other physical
work occurred, and they may be followed by separate building permits.

Source: [City of Tampa Historic Preservation layer](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/33)

### Capital Improvements

This point layer contains 192 public-facing City capital projects. Project
types include transportation, water, wastewater, stormwater, parks, facilities,
and contract administration. Status and phase fields distinguish planning,
design, procurement, construction, and closeout.

Available fields include project identifier, name, description, rationale,
type, funding source, planned dates, estimated cost, reported actual cost,
status, phase, neighborhood, council district, contract number, and project
website. This is the release's main source for public-project cost estimates.

The layer is not a complete adopted capital program. Estimated cost is not
expenditure, contract value, or final cost, and `Closeout` is an administrative
status rather than proof of physical completion. Its points may be map markers
rather than complete project footprints.

Source: [City of Tampa Capital Projects layer](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjects/FeatureServer/0)

### Citywide Capital Projects — points

This layer contains 57 point-shaped project locations, including discrete
facilities, intersections, utility sites, and similar projects. It repeats many
attributes from the main Capital Improvements layer. Twenty-eight normalized
activities connect to that layer, one also connects to the polygon layer, and
28 remain represented only by the point layer.

An unmatched feature is not necessarily a different project; inconsistent
identifiers and names can prevent an automatic connection.

Source: [Citywide Projects Public service](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/0)

### Citywide Capital Projects — lines

This layer contains 101 line or multiline geometries. Linear projects include
transportation corridors, water and sewer lines, and similar infrastructure.
Sixty-three normalized activities connect to the main Capital Improvements
layer and 38 remain represented only by the line layer.

The original geometry should be used for mapping and spatial analysis. The
derived latitude and longitude are representative coordinates calculated from
the geometry's vertices, not an authoritative project address or a true
length-weighted geographic centroid.

Source: [Citywide Projects Public line layer](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/1)

### Citywide Capital Projects — polygons

This layer contains 37 polygon or multipolygon geometries, primarily stormwater
and parks projects. Twenty-two normalized activities connect to the main
Capital Improvements layer, one also connects to the point layer, and 14 remain
represented only by the polygon layer.

The polygon describes a published project area. The derived latitude and
longitude are representative vertex averages, not area-weighted centroids.
Use the retained GeoJSON geometry for spatial analysis.

Source: [Citywide Projects Public polygon layer](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/2)

### Overlap and interpretation

Across the eight layers, 1,113 normalized activities have records from more
than one source. The build connects exact shared permit identifiers and some
capital records with exact normalized project names. These connections reduce
4,469 source features to 3,323 normalized activities.

That activity count is still not a count of real-world developments. One large
development can require several permits, while two unrelated projects can
share an address or parcel. Capital projects can also appear in more than one
geometry layer. Candidate project connections that lack a sufficiently strong
rule remain unmerged for later review.

## Derived tables

The remaining tables are created from the eight source layers; they are not
additional City datasets.

- `bounded_census_records.csv` preserves one row per published source feature.
- `source_records.csv` stores retained source attributes and provenance.
- `activity_locations.csv` stores source geometry and representative
  coordinates.
- `activity_source_links.csv` connects source features to normalized
  activities.
- `tampa_development_activity.csv` is the consolidated activity-level view.
- `activity_id_aliases.csv` records identifiers replaced during documented
  capital-project consolidation.
- `master_projects.csv` and `master_project_activity_links.csv` provide a
  provisional project layer that currently treats each activity as a
  singleton unless a reviewed relationship is available.
- `master_project_candidates.csv` contains possible project connections that
  have not been applied automatically.
- `development_events.csv` represents application, permit, status, and project
  events derivable from the available records.
- `activity_truth_status.csv` stores conservative construction and completion
  evidence fields; unknown is not converted to no.
- `investment_amounts.csv` separates estimated and reported actual City
  capital-project amounts. It does not contain broad private permit valuation.
- `parcel_building_matches.csv`, `building_match_audit.csv`, and
  `building_match_diagnostics.csv` contain proposed City-building-footprint
  connections and their pending review fields.
- The verification queue, manual samples, pilot, and second-review tables are
  research-audit materials rather than verified development observations.

## Build

Download the current City layers and build a new release:

```bash
python build_release.py
```

Rebuild version 0.6.1 from the archived source files:

```bash
python build_release.py --use-existing-raw
```

Run the checks separately:

```bash
python validate_release.py
python verify_data_accuracy.py
```

The build retrieves every page returned by each ArcGIS service, preserves the
source-derived GeoJSON after removing configured contact and source-user
fields, generates the relational tables and data dictionary, checks row counts
and keys, and packages the public release. `snapshot_metadata.json` lists every
suppressed field and the scope of the privacy-minimized snapshot.

`verify_data_accuracy.py` traces every census row back to the bundled raw
GeoJSON and checks source attributes, geometries, identifiers, counts, dates,
amount extraction, and file hashes. Add `--live` to compare the archived
OBJECTIDs with the City layers as they exist when the check is run. A live
change means the published layer changed after the snapshot; it does not make
the archived snapshot inaccurate.

These checks establish source fidelity, not real-world completion. Completion,
project grouping, and building matches still require independent review.

## Uses

The dataset supports:

- Maps of records published through the selected City layers.
- Comparisons of record types, statuses, dates, and locations within a layer.
- Analysis of overlap and field availability across City data products.
- Sampling frames for permit and building-match validation.
- Comparison of future snapshots to track additions, removals, and status
  changes.

The current release does not support estimates of total Tampa investment,
permit recall, construction completion rates, or the number of unique
developments citywide.

## Methods and limitations

- [Source scope](docs/BOUNDED_CENSUS_SCOPE.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Evidence fields](docs/GROUND_TRUTH_METHODOLOGY.md)
- [Manual validation protocol](docs/MANUAL_VALIDATION_PROTOCOL.md)
- [Data dictionary](docs/data_dictionary.csv)
- [Validation results](docs/validation_report.json)
- [Source-fidelity verification](docs/accuracy_verification_report.json)

## Citation

> Lenga, Jack. *Tampa Published Development Records: Source-Bounded Census*,
> version 0.6.1, 2026.

The code and original documentation are licensed under MIT. City records
remain subject to their source terms; see `DATA_LICENSE.md`.
