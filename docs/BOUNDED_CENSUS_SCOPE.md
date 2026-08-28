# Source scope

## Included records

The release includes every feature returned by `where=1=1` queries to eight
City of Tampa ArcGIS layers. The downloader requests successive pages until
each service returns no additional full page.

`source_universes.csv` records the endpoint, download time, raw feature count,
and retained count for each layer. `bounded_census_records.csv` contains one
row per returned feature.

## Coverage check

Coverage passes when:

1. Each raw GeoJSON count matches its normalized source-record count.
2. Every `source_record_key` occurs once in the census table.
3. Each layer's retained count matches its downloaded count.
4. No downloaded feature is excluded.

All four checks pass for version 0.8.0. Contact and source-user/editor fields
are removed from both the bundled GeoJSON and the processed properties, but no
source rows are removed. `snapshot_metadata.json` records the suppression
scope.

The Budget Book and linked-parcel modules added in version 0.8.0 are context
sources. They are separately dated and excluded from the eight-layer bounded-
census feature count and completeness claim.

## Boundary of the dataset

The dataset describes the contents of the eight layers at one point in time.
It does not establish that the layers contain every record held by the City.
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

## Dates

Dates within a row may refer to an application, status update, planned
schedule, or source edit. They do not define a common observation period for
all eight layers.

The archived, privacy-minimized GeoJSON and `snapshot_metadata.json` preserve
the released snapshot. Running the downloader again may produce different
counts as the City updates its services.
