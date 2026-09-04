# Lean manual-validation plan

## Plan v2.0.0

This plan reduces the active human-review burden while preserving a defensible
probability sample, separate validation claims, and independent review. It is
the controlling operational plan from September 3, 2026 onward. The frozen
[protocol 1.0.0](MANUAL_VALIDATION_PROTOCOL.md) still governs the claim fields,
evidence rules, and original assignment provenance.

| Active layer | Human judgments | Design | Permitted inference |
| --- | ---: | --- | --- |
| Core semantic validation | 150 | Existing frozen stratified probability sample, analyzed as one pooled sample | Claim-specific transformation quality for the original core universe |
| Reviewer reliability | 25 | Deterministic stratified subset of the 50 frozen second-review candidates | Agreement and protocol reproducibility |
| Targeted Accela audit | 75 | 15 source-fidelity, 30 normalization, and 30 linkage cases selected for risk and controls | Failure-mode evidence by component, not global Accela accuracy |
| Initial longitudinal audit | 30 | 20 high-impact changes and 10 deterministic controls | Interpretation of the initial source-publication comparison |
| **Initial total** | **280** |  |  |

The older unreviewed assignments remain unchanged for provenance, but only the
IDs in the plan-v2 subset files are required. This is a prospective workload
change, not a deletion or relabeling of completed judgments.

## Core probability sample

All 150 existing first-review assignments remain active. The historical
`development` and `holdout` labels are retained in the data, but they no longer
create separate completion gates. Final core estimates pool the full sample and
recompute each stratum's weight from its combined selection count.

Report every claim separately: source identity, activity classification,
cross-source linkage, status interpretation, physical-work evidence, and
building-footprint matching. Publish the observed numerator and denominator,
the design-weighted estimate, and a 95% confidence interval. Inconclusive and
not-applicable results remain visible and are not forced into pass/fail.

## Independent review

The active reliability file contains 25 cases selected reproducibly across all
five core strata. The second reviewer must remain blind to the first judgment
until their review is locked. Report raw agreement and Cohen's kappa by claim;
adjudication must preserve both original labels.

The original 50-row second-review file remains the immutable candidate frame.
The other 25 candidates are not required under plan v2.

## Targeted Accela audit

The active portfolio contains:

- 15 source-fidelity spot checks, split between elevated-risk and control cases;
- 30 normalization and semantic cases, oversampling prospective observations
  and relatively rare record types; and
- 30 linkage cases, evenly split between matched-link false-positive risk and
  retained-unmatched false-negative risk.

Reviewers enter results in the component source files named by
`manual_validation_accela_audit_plan.csv`. Results must be reported by
component and risk tier. Because selection is deliberately risk-based, do not
publish a population-wide Accela accuracy percentage from these 75 cases.

## Longitudinal review

The initial 30-case file contains 20 high-impact or alert-relevant changes and
10 deterministic controls. It validates the interpretation of changes in City
source publication, not physical construction outcomes.

For later canonical release comparisons, inspect 25–40 cases: all critical or
substantively important flags up to the cap, plus deterministic random controls.
Precommit the selection before reviewing outcomes and identify the release
cycle in every report.

## Claim boundaries

- **Source fidelity:** automated reconciliation plus selected manual spot checks.
- **Normalization and semantic correctness:** the core probability sample and
  targeted Accela component.
- **Reviewer reliability:** the 25-case blinded core subset.
- **GIS–Accela linkage:** targeted matched and unmatched cases reported
  separately.
- **Real-world construction outcome:** not established without a separate
  outcome study.
- **Longitudinal change:** a source-publication change, not proof of physical or
  administrative change outside the source.

No composite accuracy score is permitted.

## Reproducibility

The machine-readable plan is
[`config/manual_validation_plan.json`](../../config/manual_validation_plan.json).
The active subset files are generated once with:

```bash
python scripts/build_lean_validation_plan.py
```

The generator refuses to overwrite published plan files unless `--force` is
explicitly supplied. Never use that override after review begins without a new
plan version and preservation of the prior files.
