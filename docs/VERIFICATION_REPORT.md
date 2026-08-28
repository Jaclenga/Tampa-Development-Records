# Verification notes

## Automated source-fidelity check

Run:

```bash
python scripts/verify_data_accuracy.py
```

The script reconstructs source identifiers from the bundled GeoJSON and
compares every source record, retained property, geometry, centroid, universe
count, date, amount row, and recorded SHA-256 hash with the release tables. Its
machine-readable output is `accuracy_verification_report.json`.

For version 0.8.0, all automated checks passed for 4,469 core source features. This
result establishes fidelity to the archived City layer snapshots. It does not
establish construction, completion, project uniqueness, building-match
accuracy, or citywide coverage.

This file documents a 12-record pilot conducted for version 0.4.0 and retained
as historical evidence in version 0.8.0. The sources were reviewed on August
23, 2026. The pilot is not forced into or analyzed as part of the new study.

## Checks performed

- `scripts/validate_release.py` checked table keys, relationships, counts, geometries,
  aliases, and data-dictionary coverage.
- Classification rules and capital-project identifiers were checked for
  internal contradictions.
- Twelve sampled records were compared with cited public sources. The pilot
  used AI-assisted web research and was not independently replicated.

Results and source URLs are in `external_verification_pilot.csv`.

## Corrections from the pilot

Two classification problems were found in version 0.3.0:

1. Descriptions mentioning demolition could override stronger evidence of an
   addition, renovation, rebuild, or selective interior demolition. The rule
   now requires a demolition-oriented title without contradictory work terms.
2. Capital-project identifiers overlap across City layers. Source-specific IDs
   are now kept separate before exact normalized project names are used to
   connect records across layers.

The changes reduced the normalized activity count from 3,357 to 3,323 and the
demolition classification count from 231 to 155. The 229 replaced activity
IDs are listed in `activity_id_aliases.csv`.

## Pilot results

| Claim group | Supported | Contradicted | Inconclusive |
|---|---:|---:|---:|
| Capital-project identity or status | 10 | 0 | 0 |
| Permit identity or work classification | 1 | 0 | 0 |
| Planning-record identity or location | 1 | 0 | 0 |

| Physical evidence | Rows |
|---|---:|
| Work documented | 1 |
| Partial evidence | 3 |
| Not established | 7 |
| Not applicable | 1 |

The documented construction case is Green Spine Cycle Track Phase 2A. A City
news release identified its location, cost, contractor, schedule, and start of
construction. Administrative `Closeout` statuses were not counted as evidence
of physical completion.

## Interpretation

The pilot tested a small set of traceable claims; it did not estimate accuracy
for the full dataset. Records were selected partly because external evidence
was available, most capital-project evidence came from City sources, and no
second reviewer repeated the work.

The pilot therefore supports source traceability and documents two corrected
logic errors. It does not support citywide completion rates or investment
rankings.

## Frozen designed study retained in version 0.8.0

The current external-validation workflow uses a frozen, seeded stratified
sample of 150 activities, with a 100-row development phase, a separately drawn
50-row holdout, and 50 blinded second-review assignments. Claim-specific
criteria and acceptable sources were fixed before review in
`MANUAL_VALIDATION_PROTOCOL.md`. Human coding is pending; no error rate or
agreement statistic is claimed yet.
