# Source inventory and provenance

This is the human-readable inventory of upstream data sources used by Tampa
Published Development Records (TDR) version 0.9.0. It identifies what each
source contributes, how and when it was retrieved, and which dataset boundary
it belongs to. [`manifest.json`](../../manifest.json) remains the
machine-readable release record for exact bundled-file paths and SHA-256
hashes; snapshot- and collector-specific metadata provide the finer-grained
audit trail.

## Source classes

| Class | Included in the eight-layer bounded-census claim? | Purpose |
| --- | --- | --- |
| Core GIS | Yes | Preserve every feature returned by eight named City of Tampa ArcGIS layers at each recorded observation time. |
| Accela expansion | No | Add a separately bounded view of public Building and Planning administrative records. |
| Context and spatial enrichment | No | Add budget, parcel, and building-footprint attributes or links without enlarging the core census. |
| Optional local enrichment | No; excluded from the public City-only edition | Supply a research-only parcel-centroid fallback when explicitly requested. |

The source feature is the core unit of observation. A feature or Accela row is
not necessarily a unique development, and an administrative status is not
proof of a physical start, completion, inspection result, or certificate of
occupancy.

## Core bounded census: eight City GIS layers

For the baseline release, each ArcGIS layer was queried with `where=1=1` and
all fields and geometry were retained after documented privacy suppression.
The initial downloader used ordered result-offset pagination. The hardened
collector used for the reconciled follow-up performs repeated count-only
queries, obtains the complete object-ID inventory, retrieves features in
ID-bounded chunks, and requires the initial counts, ID inventory, retrieved
IDs, and final count to agree.

The first archived observation was retrieved at
`2026-08-23T02:06:02+00:00`; the reconciled follow-up was retrieved at
`2026-09-01T07:15:12+00:00`. These are observation times, not a common
historical coverage period for dates reported inside the source rows.

| Source | ArcGIS endpoint | Role | Records on 2026-08-23 | Records on 2026-09-01 |
| --- | --- | --- | ---: | ---: |
| Construction Inspections | [MapServer/30](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/30) | Published building-permit records; despite the layer name, rows are not inspection results | 2,619 | 2,573 |
| Development Coordination | [MapServer/31](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/31) | Active planning or land-development applications | 271 | 273 |
| Single-Family Permits | [MapServer/32](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/32) | Single-family construction or addition permits | 1,023 | 1,016 |
| Historic Preservation | [MapServer/33](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Planning/MapServer/33) | Historic-preservation applications | 169 | 164 |
| Capital Improvements | [FeatureServer/0](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjects/FeatureServer/0) | City capital-project records | 192 | 190 |
| Citywide Capital Projects: points | [FeatureServer/0](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/0) | Point representations of capital projects | 57 | 57 |
| Citywide Capital Projects: lines | [FeatureServer/1](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/1) | Linear representations of capital projects | 101 | 101 |
| Citywide Capital Projects: polygons | [FeatureServer/2](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CityWideProjectsPublic/FeatureServer/2) | Area representations of capital projects | 37 | 34 |
| **Total** |  | **All returned source features** | **4,469** | **4,408** |

The public baseline GeoJSON files are under [`data/raw/`](../../data/raw/).
Compact immutable observations and their content/state hashes are under
[`data/snapshots/`](../../data/snapshots/). Per-layer baseline endpoints,
retrieval times, raw counts, and retained counts are also recorded in
[`source_universes.csv`](../../data/processed/source_universes.csv).

The September 1 metadata records and supersedes an incomplete earlier
same-day capture. Only the reconciled 4,408-record observation is used as the
accepted follow-up. See its
[`metadata.json`](../../data/snapshots/2026-09-01/metadata.json).

## Accela expanded edition

The expanded edition uses the City of Tampa's anonymous Accela Citizen Access
(ACA) portal at <https://aca-prod.accela.com/TAMPA/>. It is separate from, and
does not alter, the eight-layer bounded census.

| Source module | Public search endpoint | Current role and temporal coverage | Retrieval method |
| --- | --- | --- | --- |
| Building | [Building CapHome](https://aca-prod.accela.com/TAMPA/Cap/CapHome.aspx?module=Building&TabName=Building) | Building administrative records with source-reported opened dates from 2020-01-01 onward | Bounded opened-date searches through the public ACA WebForms interface; the historical backfill uses the public **Download results** CSV control |
| Planning | [Planning CapHome](https://aca-prod.accela.com/TAMPA/Cap/CapHome.aspx?module=Planning&TabName=Planning) | Planning administrative records with source-reported opened dates from 2020-01-01 onward | Same bounded public-search and export workflow |

The current aggregate contains 338,789 unique Building/Planning records. Its
334,808 rows dated from 2020-01-01 through 2026-07-31 were retrieved
retrospectively in August and September 2026; they are not contemporaneous
historical snapshots. Prospective monitoring starts at 2026-08-01 and accounts
for 3,981 records in the current aggregate. A separate completed-day freeze
for 2026-08-31 is stored under
[`data/frozen/accela/2026-08-31/`](../../data/frozen/accela/2026-08-31/).

The 158 Building/Planning module-month partitions passed recorded gap,
truncation, identity, and aggregate reconciliation checks. This establishes
collection integrity for what the public queries returned, not completeness
of the City's underlying administrative systems or real-world accuracy.
Exact run times, query bounds, request metadata, response hashes, gaps, and
counts live in the raw metadata, checkpoints, snapshot summaries, the
[`Accela backfill report`](../../data/integrated/accela_backfill_report.json),
and the [`expanded-edition manifest`](../../data/integrated/manifest.json).

ACA responses are collected through public HTML/WebForms pages because the
verified Tampa v4 API route required an application ID or access token. The
collector can optionally follow public detail and inspection panels; inspection
events are a one-to-many enrichment of their parent Accela records. Raw HTML is
token-redacted, and normalized public outputs exclude phone, email, and mailing
fields. The complete method is in the
[`Accela collector guide`](../guides/ACCELA_COLLECTOR.md), with interpretation
limits in [`ACCELA_LIMITATIONS.md`](ACCELA_LIMITATIONS.md).

RightOfWay and Enforcement are supported by the collector but are not inputs
to the current 338,789-record expanded edition. An official City-provided
export can also be staged by the repository, but no such export is part of the
current release.

## Context and spatial-enrichment sources

These sources add attributes or comparison tables. Their rows are excluded
from the eight-layer counts, completeness claim, and frozen core validation
sampling frame.

| Source | Endpoint | Role and bounded coverage | Retrieval method and observation time |
| --- | --- | --- | --- |
| Capital Projects Budget Book | [FeatureServer/0](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjectsBudgetBook/FeatureServer/0) | Budget, funding, phase, schedule, cost, contract, and location context; 228 returned features representing 220 distinct project IDs | Complete ArcGIS layer query with an analytical field whitelist; observed `2026-08-28T04:55:51+00:00` |
| Linked City tax parcels | [FeatureServer/0](https://arcgis.tampagov.net/arcgis/rest/services/Parcels/TaxParcel/FeatureServer/0) | Parcel context for folios already exposed by proposed building-footprint matches; 932 returned parcels from 936 requested folios, not the citywide parcel universe | ArcGIS queries limited to the requested folio set and an analytical field whitelist; observed `2026-08-28T04:55:51+00:00` |
| City building footprints | [MapServer/0](https://arcgis.tampagov.net/arcgis/rest/services/OpenData/Location/MapServer/0) | Candidate footprint, folio, assessment-year, area, unit, and floor attributes used for spatial matching; 8,223 distinct nearby features are bundled | Spatial ArcGIS queries for buildings within 100 metres of relevant core activity points; bundled with the baseline release, whose core retrieval time is 2026-08-23. The GeoJSON has no independent retrieval timestamp; this is a provenance limitation |

Budget Book and tax-parcel snapshot endpoints, requested fields, counts,
observation time, and hashes are recorded in
[`context_snapshot_metadata.json`](../../data/context/raw/context_snapshot_metadata.json).
Their raw files are under [`data/context/raw/`](../../data/context/raw/), and
their transformations are described in
[`CONTEXT_MODULES.md`](../methodology/CONTEXT_MODULES.md).

The building-footprint extract is bundled at
[`matched_building_footprints.geojson`](../../data/raw/matched_building_footprints.geojson).
It is a spatial-enrichment source, not a ninth census layer. Matches are
heuristic and remain separately auditable in
[`parcel_building_matches.csv`](../../data/processed/parcel_building_matches.csv).

## Optional source excluded from the public edition

With `python scripts/build_release.py --include-hcpa`, a local research build
may download the Hillsborough County Property Appraiser (HCPA) LatLon table
from <https://downloads.hcpafl.org/Default.aspx> and use the nearest parcel
centroid within 150 metres as a low-confidence fallback. The v0.9.0 public
City-only archive excludes the HCPA archive, extracted DBF, and all
HCPA-derived fallback rows. Therefore HCPA has no fixed observation time or
hash in the current public manifest. A local HCPA-enabled manifest records the
downloaded archive and hash. Redistribution restrictions are summarized in
[`LICENSE_NOTES.md`](LICENSE_NOTES.md).

## Temporal and provenance rules

- **Observation time** is when TDR retrieved a public source. **Event time** is
  a date reported inside that source. They are not interchangeable.
- The canonical analytical cohort begins on 2020-01-01. Older attributes may
  remain in immutable source snapshots, while known pre-boundary events are
  excluded from researcher-facing monthly cohorts.
- Forward-looking dates are kept in `data/planned_events/`; they are not
  relabeled as observed events.
- Record-level links found in source rows may point to ACA details or City
  project pages. Unless a collector artifact says otherwise, those links are
  attribution or review targets, not additional bulk inputs.
- Hashes should be taken from the applicable machine manifest or snapshot
  metadata rather than copied from this document, so refreshed releases have
  one authoritative integrity record.

For the exact boundary and nonclaims, see
[`BOUNDED_CENSUS_SCOPE.md`](../methodology/BOUNDED_CENSUS_SCOPE.md). For date
selection and cohort construction, see
[`TEMPORAL_COHORTS.md`](../methodology/TEMPORAL_COHORTS.md).
