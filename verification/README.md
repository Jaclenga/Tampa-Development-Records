# Verification architecture

`verification_summary.csv` reports validation layers separately. It does not
create a generic `verified` flag, an overall accuracy percentage, or a composite
score. Generate it with:

```bash
python scripts/build_verification_summary.py
```

Blank metrics mean **Not measured**, not zero.

## Three different validity questions

1. **Source fidelity:** did TDR faithfully capture what the City source
   published? This includes identity, source fields, and retrieval completeness.
2. **Transformation validity:** did TDR correctly normalize, classify, link,
   deduplicate, and assign temporal semantics to the captured source record?
3. **Real-world / outcome validity:** does evidence independent of the retained
   row establish that the described activity occurred, changed, completed, or
   was cancelled?

Passing one layer does not establish either of the other two. `unknown` and
`not_applicable` are valid outcomes and must not be forced into pass/fail.

## Study register

| Study | Population and frame | Seed | First review | Strata and allocation | Second review | Valid inference scope |
| --- | --- | ---: | ---: | --- | ---: | --- |
| Core eight-layer manual validation | Frozen original normalized activity universe | 20260823 | 150: 100 development + 50 holdout | Five fixed source-family/cross-source quotas; phase-specific probabilities and weights | 50 | Original core release only; never the Accela expansion |
| Accela source fidelity | 338,789 unique Building/Planning records in the completed aggregate | 20260911 | 200 | Module × retrospective/prospective × period × common/relatively rare type; proportional with minimum 2 per nonempty stratum | 50 | Fidelity to the City Accela publication for the sampled frame |
| Accela normalization | 338,589 Accela records after excluding the 200 source-fidelity assignments | 20260912 | 125 | Same four design dimensions; proportional with minimum 2 | 31 | Correctness of TDR transformation semantics, not portal truth |
| GIS–Accela linkage | 338,789 integration-audit decisions | 20260913 | 100 | 50 matched and 50 retained unmatched in the present frame; future ambiguous and duplicate strata are supported when populated | 25 | Linkage/deduplication decisions only; matched precision and unmatched error must be reported separately |
| Longitudinal change events | 2,822 machine-detected events in the currently archived comparison | 20260914 | 75 | Change type; proportional with minimum 3 per nonempty type | 19 | Meaning of detected snapshot changes, not collection completeness or physical outcomes |
| Core external outcome pilot | Evidence-selected historical pilot | Not applicable | 12 completed | Convenience/evidence-selected | None | Descriptive pilot only; no population estimate |
| Expanded external outcomes | No probability sample yet | Not measured | Not measured | Not measured | Not measured | No expanded-edition outcome inference yet |

The generated Accela and longitudinal rows record the universe hash, universe
size, seed, stratum population, stratum sample size, inclusion probability, and
inverse-probability weight. Because small strata are deliberately protected,
unweighted percentages across a whole sample are descriptive only. Use the
published weights for estimates supported by a completed probability study.

## Files

First-review assignments:

- `data/processed/manual_validation_sample.csv` — combined frozen core study;
- `data/processed/manual_validation_accela_source_fidelity.csv`;
- `data/processed/manual_validation_accela_normalization.csv`;
- `data/processed/manual_validation_integration_links.csv`; and
- `data/processed/manual_validation_change_events.csv`.

Each new study has an adjacent `_second_review.csv` file. These files preserve
independent reviewer fields and include later reconciliation fields for first
outcome, second outcome, agreement, adjudication status, and adjudicated
outcome. The second reviewer must finish a row before first-review outcomes are
copied into those reconciliation columns.

## Freeze and regeneration policy

The original 150 core assignments and 50 second-review assignments are guarded
by fixed context hashes in `scripts/validation_study.py`. Ordinary release
builds validate and reuse them. They are not redrawn from the expanded dataset.

Each new builder refuses to overwrite existing frozen CSVs unless `--force` is
supplied. `--force` is for a deliberate, versioned redesign before review; it
must never be part of an ordinary release build.

```bash
python scripts/build_accela_source_fidelity_sample.py
python scripts/build_accela_normalization_sample.py
python scripts/build_integration_validation_sample.py
python scripts/build_change_validation_sample.py
```

## Review, adjudication, and reporting

Reviewers use non-personal codes and ISO 8601 timestamps, cite public evidence,
and leave unresolved evidence as `unknown`. Do not copy owner, applicant,
contractor, phone, email, or mailing data into review notes.

Second review is blinded and independent. Preserve both original judgments.
After both are locked, populate `first_outcome`, determine `agreement`, and set
`adjudication_status`. An adjudicator may add `adjudicated_outcome`, but must not
overwrite either reviewer’s original outcome.

Only completed probability studies may support weighted estimates and
confidence intervals. Always report evaluated n, sampling universe, weighting
method, estimate, and uncertainty. Do not calculate dataset-wide accuracy from
the 12-row pilot, incomplete reviews, convenience samples, or collection
reconciliation. Small strata should be reported with raw counts and uncertainty.
