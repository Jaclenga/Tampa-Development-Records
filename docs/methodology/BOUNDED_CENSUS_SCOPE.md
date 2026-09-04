# Source scope

## Included records

The release includes every feature returned by `where=1=1` queries to eight
City of Tampa ArcGIS layers. The downloader requests successive pages until
each service returns no additional full page.

`source_universes.csv` records the endpoint, download time, raw feature count,
and retained count for each layer. `bounded_census_records.csv` contains one
row per returned feature.

| Source | Records | Typical source row |
| --- | ---: | --- |
| [Construction Inspections](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/30) | 2,619 | Published building-permit record, not an inspection result |
| [Single-Family Permits](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/32) | 1,023 | Single-family construction or addition permit |
| [Development Coordination](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/31) | 271 | Active planning or land-development application |
| [Historic Preservation](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/33) | 169 | Historic-preservation application |
| [Capital Improvements](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjects/FeatureServer/0) | 192 | City capital-project record |
| [Citywide Capital Projects: points](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/0) | 57 | Point representation of a capital project |
| [Citywide Capital Projects: lines](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/1) | 101 | Linear representation of a capital project |
| [Citywide Capital Projects: polygons](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/2) | 37 | Area representation of a capital project |
| **Total** | **4,469** | **Published source records** |

The permit layers overlap heavily: 999 of 1,023 Single-Family records link to
Construction Inspections records. The build preserves every source row while
resolving strong identifier matches into 3,323 normalized activities. An
activity is still not necessarily a unique real-world development.

## Coverage check

Coverage passes when:

1. Each raw GeoJSON count matches its normalized source-record count.
2. Every `source_record_key` occurs once in the census table.
3. Each layer's retained count matches its downloaded count.
4. No downloaded feature is excluded.

All four checks pass for version 0.9.0. Contact and source-user/editor fields
are removed from both the bundled GeoJSON and the processed properties, but no
source rows are removed. `snapshot_metadata.json` records the suppression
scope.

The Budget Book and linked-parcel modules added in version 0.8.0 are context
sources. They are separately dated and excluded from the eight-layer bounded-
census feature count and completeness claim.

## Boundary of the dataset

Each snapshot describes the contents of the eight layers at one point in time.
The first archived observation is August 23, 2026, followed by an actual
September 1 observation. Regular month-end observations begin September 30;
the September 1 retrieval is not backdated to August 31. Repeated snapshots can
show publication changes between observations, but they do not establish that
the layers contain every record held by the City.
For example, a layer may show only active projects, selected permit types, or
records that meet an unpublished display rule.

The source feature is the unit of observation. A source feature is not always
a permit or a unique project, and several features may refer to the same
development.

The release therefore should not be described as a census of:

- Tampa's full Accela permit database;
- unique developments;
- construction starts or completions;
- certificates of occupancy or final inspections; or
- public and private investment.

## Priority coverage gaps

The highest-priority additions are a fuller building-permit export,
certificates of occupancy, inspection-level records with explicit final
results, complete demolition permits and planning decisions, and repeated
annual capital-budget records.

No verified public bulk endpoint for the first three was located in the
official interfaces checked on August 28, 2026. The
[`source_gap_registry.csv`](../../data/coverage/source_gap_registry.csv) records
the desired universes, analytical value, current evidence, and next action.
The [public-records request](../guides/PUBLIC_RECORDS_REQUEST.md) provides a reproducible
path to the missing official records without scraping address-level pages.

## Dates

Dates within a row may refer to an application, status update, planned
schedule, or source edit. They do not define a common observation period for
all eight layers.

The archived, privacy-minimized GeoJSON and `snapshot_metadata.json` preserve
the current full release snapshot. `data/snapshots/` preserves compact
source-record states for comparison without duplicating geometry. Running the
downloader again may produce different counts as the City updates its services.
