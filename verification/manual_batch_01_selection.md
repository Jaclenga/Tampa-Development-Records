# Core manual-validation development batch 01

This work-order subset was selected reproducibly from the 100 frozen
development assignments without considering evidence availability or review
outcomes.

- Population: 100 frozen development assignments
- Seed: `20260903-manual-batch-01`
- Ranking key: `SHA256(seed + "|" + audit_sample_id + "|" + activity_id)`
- Selection rule: select the ten lexicographically smallest hashes
- Selected IDs, in hash order: `dev-076`, `dev-031`, `dev-070`, `dev-093`,
  `dev-091`, `dev-025`, `dev-088`, `dev-068`, `dev-028`, `dev-071`

The ten first reviews were completed by the human reviewer on 2026-09-03 and
recorded in `data/processed/manual_validation_development_sample.csv` with
`reviewer_id=reviewer-01` and `ai_assistance_used=yes`. The combined
`manual_validation_sample.csv` remains a byte-frozen pre-human benchmark input;
the phase file is authoritative for review progress.

These partial results are exploratory development-phase diagnostics only. They
are not a population accuracy estimate. The holdout assignments and blind
second reviews remain untouched. Missing pages, access failures, permit
issuance, funding, design progress, planning, and administrative closeout do
not by themselves establish physical work.
