# Tampa Accela public-record collector

This optional collector acquires date-bounded records from the City of Tampa's
anonymous Accela Citizen Access (ACA) portal. It does not log in, bypass access
controls, solve CAPTCHAs, or use private endpoints. It stops on HTTP 401/403 or
a CAPTCHA response.

## Verified source and approach

The public portal is `https://aca-prod.accela.com/TAMPA/`. On August 30, 2026,
anonymous search pages returned HTTP 200 for the Building, Planning,
RightOfWay, and Enforcement modules. A bounded search is an ASP.NET WebForms
POST to the module's `Cap/CapHome.aspx` page. Search results use public detail
links keyed by `capID1`, `capID2`, and `capID3`; pagination is a session-bound
WebForms postback.

The collector uses this sequence:

1. GET the public module search page and retain its transient view state.
2. POST a record number or explicit opened-date range to the same page.
3. Parse the public result grid and follow its displayed `Next` postback until
   the last page or a configured safeguard.
4. Optionally GET each public detail page for address/parcel fields and
   optionally post back the public inspection panel.

Accela's v4 documentation labels record-search operations as unauthenticated,
but the Tampa agency endpoint returned `400` and required an `x-accela-appid`
or access token during verification. No public Tampa app ID was discovered, so
the collector does not pretend the v4 API is usable. The ACA flow is HTML and
can change; parser failures are recorded as collection gaps instead of silently
producing a complete-looking file.

## Install and run

```bash
python -m pip install -r requirements.txt

# Validate a plan without making a request
python scripts/collect_accela.py --module Building --from-date 2026-08-13 --to-date 2026-08-13 --dry-run

# Small bounded Building collection
python scripts/collect_accela.py --module Building --from-date 2026-08-13 --to-date 2026-08-13 --max-records 25

# Planning collection
python scripts/collect_accela.py --module Planning --from-date 2026-08-01 --to-date 2026-08-07

# Exact public record lookup
python scripts/collect_accela.py --module Building --record-number BDE-26-0445754

# Resume enrichment after interruption (the session-bound list pages replay)
python scripts/collect_accela.py --module Building --from-date 2026-08-13 --to-date 2026-08-13 --run-id sample --resume
```

`--updated-since` is accepted so the limitation is explicit, but it exits with
an error: Tampa's verified anonymous form has no last-updated filter. Opened
dates are not substituted because that would mislabel incremental semantics.

The default list-only mode avoids opening detail pages. Use
`--include-addresses`, `--include-parcels`, or `--include-inspections` only when
needed. Detail HTML may contain public owner, applicant, contractor, phone,
email, or mailing information even though the normalized table excludes phone,
email, and mailing fields. Treat opt-in raw files as sensitive working data and
review them before redistribution. An exact record-number search can redirect
straight to its detail page, so its raw response needs the same review even
without enrichment flags.

## Network and recovery behavior

- One request per second by default and never more than one per second.
- Connect/read timeouts, exponential backoff, and retries for 429, 500, 502,
  503, and 504 responses; numeric or HTTP-date `Retry-After` is respected.
- Stable IDs are derived from Tampa module and public `capID1/2/3`; the public
  record number is a documented fallback.
- Checkpoints are written after each record. Because pagination is tied to a
  WebForms session, resume replays earlier list pages and skips already
  completed detail enrichment.
- A repeated page, unrecognized empty response, parser/schema failure, maximum
  page limit, or failed optional detail request becomes an explicit gap.

## Outputs and provenance

Raw, token-redacted HTML is stored under
`data/raw/accela/YYYY-MM-DD/<module>/<run-id>/`. Each response has adjacent JSON
metadata with request URL, semantic parameters, retrieval time, status,
collector version, response SHA-256, page, and row count. Cookies, headers,
anti-CSRF values, and WebForms view state are not retained. Existing raw files
are content-addressed and never overwritten.

Processed outputs are CSV because this repository has no required Parquet
engine:

- `data/processed/accela_records.csv`: latest observed row per stable ID.
- `data/processed/accela_<module>_records.csv`: module subset.
- `data/processed/accela_inspections.csv`: optional inspection observations.
- `data/processed/accela_snapshots/<run>-<module>.csv`: run snapshot.
- adjacent `-summary.json` and `-gaps.json`: counts and completeness flags.

The normalized schema keeps lifecycle dates distinct (`opened_date`,
`issued_date`, `completed_date`, `closed_date`, and `updated_date`). A null means
the source did not expose that concept in the collected view; the collector
does not infer one lifecycle event from another. A record disappearing from a
later query is not treated as deletion or cancellation. Clearly labeled public
parent/related record numbers are retained; no relationship is inferred when a
detail page does not expose one.

## Conservative GIS matching

Pass `--match-gis data/processed/source_records.csv` to write
`accela_gis_crosswalk.csv`. Matching precedence is exact public record number,
exact parcel, exact normalized address with a compatible date, then fuzzy
address plus a compatible date (within 45 days). Fuzzy results are `candidate` rows with
`review_required=true`; they are never auto-merged into the GIS dataset.
Unmatched Accela records are retained. The crosswalk records the method, score,
and each matching signal.

## Adding collected rows to the activity dataset

Run `python scripts/integrate_accela.py` after collection. It writes a separate
expanded edition at
`data/integrated/tampa_development_activity_with_accela.csv`, preserving the
original eight-layer bounded-census tables and claims. Stable Accela IDs and
canonical public record numbers are deduplicated first. A record merges into a
core activity only on one unambiguous exact public record-number match; fuzzy
matches never merge automatically. The adjacent audit CSV and report JSON make
every merge, append, exclusion, and duplicate assertion reviewable.

## Scope and interpretation

Building and Planning are primary modules; RightOfWay and Enforcement are
supported secondary modules. A bounded ACA result is complete only for the
query the portal returned at that retrieval time. It is not proof of a complete
permit, certificate-of-occupancy, code-enforcement, or inspection population.
Public ACA status text is administrative source data, not proof that work
started, finished, passed inspection, or exists physically. Verify material
claims against official source records.
