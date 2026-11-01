# Capital-improvement source investigation — November 1, 2026

The 394-to-195 row decline is dominated by duplicate-like records in the
October source, rather than evidence of a 50% fall in capital projects.
Publisher cleanup is the likely explanation, but has not been confirmed by
the City. Earlier immutable observations have not been changed.

## Collection checks

On November 1 at 09:25 UTC, independent `where=1=1` count queries before and
after collection, an ID-only inventory, and complete feature retrieval each
returned 195 records. Their GlobalID set exactly matches the November 1
archive. The collector itself also reconciles repeated counts, the inventory,
feature IDs and a final count. This is not evidence of pagination truncation
or an added collector filter.

Source: [City Capital Projects layer](https://arcgis.tampagov.net/arcgis/rest/services/CapitalProjects/CapitalProjects/FeatureServer/0).
The service is not historically archived, so a current query cannot establish
when or why the publisher removed a record.

## Why October was unusually large

For diagnosis, group records by stripped, case-insensitive `DepPrjNum` plus
`projname`. These are candidate project groupings, not verified unique projects.
Separate records can share these values, so they do not authorize deduplication.

| Observation | Published rows | Diagnostic project groups |
| --- | ---: | ---: |
| August 23 | 192 | 191 |
| September 1 | 190 | 189 |
| October 1 | 394 | 200 |
| November 1 | 195 | 194 |

October has 191 groups with two rows, one with four, and eight with one.
In 71 repeated groups, every property except OBJECTID and GlobalID is
identical. Another 113 groups differ only in `docpath` after excluding those
IDs. This strongly supports duplicate publication as the main source of the
October inflation. Different GlobalIDs explain why a native-record comparison
counts these as separate records.

The row delta decomposes into a reduction of 193 surplus rows within these
groups and a net reduction of six groups: **-193 + -6 = -199**. This is an
arithmetic diagnostic, not a measured change in actual development activity.

## Projects that need separate interpretation

Of the diagnostic groups, 183 persist, 17 stop matching and 11 newly match.
Two of the 17 have plausible continuations:

- `TRANS10047`: Armenia Ave at Cypress St. appears under a revised name with
  the same department project number.
- `TRANS20176`: MacDill Air Force Base Access Improvements has three apparent
  successor segments, `TRANS20176.1`, `.2`, and `.3`.

The remaining 14 groups are no longer returned: 12 previously had status
`Closeout`, and two had `Planning` (Manhattan/Obispo-to-Bay-to-Bay Phase 2 and
Lamb Canal). Their disappearance does not establish completion or cancellation.
Closeout-heavy removal is consistent with source housekeeping, but the two
planning records and absent publisher explanation leave the reason unresolved.

The [candidate review CSV](../../data/monthly_changes/analysis/2026-11-01_capital_missing_projects.csv)
lists all 17 groups, their earlier status, and apparent continuations.
The [machine-readable evidence summary](../../data/monthly_changes/analysis/2026-11-01_capital_investigation.json)
records reconciliation counts and duplicate-group differences.

## Effect on the dataset

Retain the raw snapshots, the critical source-change alert and the exclusion
from global aggregate trends. November's 195 rows are independently reconciled;
October's 394 should not be interpreted as 394 distinct projects. No historical
rows were deleted or silently merged as part of this investigation.
