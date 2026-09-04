# Context modules

Version 0.8.0 adds two City-hosted context modules without changing the
eight-layer bounded-census claim or its 4,469-feature count.

## Capital Budget Book

`data/context/raw/capital_budget_book.geojson` is a privacy-minimized snapshot
of the City's Capital Projects Budget Book layer. The build retains project,
budget-year, funding, phase, schedule, cost, contract, location, and provenance
fields. It excludes project-contact and source-user/editor fields.

Derived tables:

- `capital_budget_book_projects.csv` contains one normalized context row per
  Budget Book feature.
- `capital_budget_book_comparison.csv` compares Budget Book and core capital
  records using exact City project identifiers only. Names are retained for
  diagnosis but are not used as automatic matches. The snapshot contains 228
  source features but 220 distinct project IDs; all repeated source rows are
  preserved, and the comparison reports their count and context-row IDs rather
  than silently choosing one as unique.
- `public_finance_events.csv` records reported estimates, reported actual-cost
  values, and funded-status observations separately.

The Budget Book layer is a context source, not a reconstruction of every
appropriation or amendment. An estimated cost is not expenditure, a funded
label is not a payment, and a reported actual cost is not assumed final or
independently audited. Resolution-level events remain pending a separately
documented budget-resolution ingestion process.

Source:
https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjectsBudgetBook/FeatureServer/0

## Linked parcel context

The build takes folios already exposed by proposed City building-footprint
matches and queries the City Tax Parcel service only for those folios. It does
not download the complete parcel universe.

The raw context snapshot and processed table retain only analytical fields:

- folio and PIN;
- site address, city, and ZIP;
- parcel and land-use codes;
- year built and remodel year;
- building and parcel area;
- market and building values;
- sale date and sale amount;
- vacant/improved status, stories, and parcel geometry; and
- source identifiers and observation timestamps.

The build excludes owner names, owner mailing addresses, legal descriptions,
DBA fields, contact fields, source-user/editor fields, and free-text funding
comments.

`parcel_activity_links.csv` treats every link as
`pending_human_review`. Its `building_footprint_folio` method means that a
proposed building match supplied the folio; it is not a legal parcel
determination. A sale, assessment change, remodel year, or year built does not
prove that a particular permit was completed.

Source:
https://arcgis.tampagov.net/arcgis/rest/services/Parcels/TaxParcel/FeatureServer/0

## Reproducibility and dates

`data/context/raw/context_snapshot_metadata.json` records the separate context
observation time, source endpoints, requested fields, row counts, and file
hashes. Rebuild a frozen release with:

```bash
python scripts/build_release.py --use-existing-raw
```

Refresh only the context snapshots and tables with:

```bash
python scripts/context_modules.py
```

Context observation dates can differ from the core snapshot date and must be
reported separately. Context rows are excluded from the source-bounded census
record count and from the frozen 150-activity validation sampling frame.
