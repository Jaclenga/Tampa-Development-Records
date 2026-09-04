# Submission-ready request for the remaining Accela data

This request covers records needed for a longitudinal permit dataset. It has
not been submitted.

Submit this through the City Clerk's official public-records request service:
https://www.tampa.gov/city-clerk (the page links to the City's GovQA portal).
The City also lists publicrecords@tampagov.net and 813-274-8030 for questions.

Suggested request text:

> Please provide the ordinary-course machine-readable database export—CSV,
> relational database tables, newline-delimited JSON, or JSON—of all City of
> Tampa Accela building, trade, site, and planning records from
> January 1, 2010 through the most recent available date. Please include, where
> available: Accela record and CAP identifiers; parent, child, revision, and
> related-record identifiers; record type, subtype, work class, status and
> status history; application/opened, issued, expiration, withdrawn, closed,
> finaled, TCO and CO dates; site address, parcel folio and coordinates;
> description; declared construction valuation; new/addition/alteration/
> demolition square footage; existing and proposed units; occupancy; inspection
> type, date and result; final-inspection indicator; certificates of occupancy;
> and fees assessed and paid. Please also include every inspection identifier,
> type, scheduled/completed date, result, final indicator, and related permit;
> every certificate-of-occupancy or certificate-of-completion identifier, type,
> status and date; and all parent/child, revision, phase and related-record keys.
> Separate relational tables are preferred. Please include a field dictionary,
> primary/foreign-key documentation, table row counts, and record counts by
> year and record type. Please provide the existing export in its native form
> rather than converting it to PDF. Owner
> names, personal contacts, uploaded plans and other personal information are
> not requested.

Record the request number, fulfillment date, correspondence, file checksums,
and any excluded fields or tables. Review delivered files for personal contact
information before adding them to the repository.

Stage a delivered machine-readable export with:

```bash
python scripts/import_accela_export.py path/to/export.csv
```

The importer maps explicit record, relationship, inspection, final, TCO, and
CO fields when present and writes a separate lifecycle-event staging table. It
does not infer missing events or completion from a general status field. Review
the field mapping and every lifecycle category before promoting staged rows
into `development_events.csv`. The expected long-format fields are also shown
in `data/templates/official_lifecycle_events_template.csv`.
