# Verification architecture

`verification_summary.csv` reports each validation claim separately. Blank
metrics mean **not measured**; the repository does not publish a composite
verification score.

Generate the summary with:

```bash
python scripts/build_verification_summary.py
```

## Distinct validity questions

1. **Source fidelity:** did TDR capture what the City source published?
2. **Transformation validity:** did TDR correctly normalize, classify, link,
   deduplicate, and assign temporal meaning?
3. **Real-world / outcome validity:** does independent evidence establish that
   the described activity occurred, changed, completed, or was cancelled?

Passing one layer does not establish either of the others. `unknown` and
`not_applicable` are valid outcomes.

## Active human-validation plan

Plan v2.0.0 reduces the initial workload to 280 judgments while retaining the
original probability sample and independent review.

| Layer | Active cases | Selection | Valid inference |
| --- | ---: | --- | --- |
| Core semantic validation | 150 | Frozen stratified probability sample | Claim-specific quality for the original core normalized universe |
| Core reviewer reliability | 25 | Deterministic stratified subset of 50 frozen candidates | Agreement and protocol reproducibility |
| Targeted Accela audit | 75 | 15 fidelity + 30 normalization + 30 linkage cases, risk oversampled | Component-specific failure modes only |
| Initial longitudinal audit | 30 | 20 high-impact changes + 10 controls | Initial source-publication comparison only |

The [lean validation plan](../docs/validation/LEAN_VALIDATION_PLAN.md) defines
the inference boundaries. The [operator guide](../docs/guides/MANUAL_VALIDATION_GUIDE.md)
defines the workflow.

## Active files

- Core first review:
  `data/processed/manual_validation_development_sample.csv` and
  `data/processed/manual_validation_holdout_sample.csv`.
- Independent review:
  `data/processed/manual_validation_core_reliability.csv`.
- Accela portfolio index:
  `data/processed/manual_validation_accela_audit_plan.csv`.
- Longitudinal index:
  `data/processed/manual_validation_longitudinal_initial_plan.csv`.

The Accela and longitudinal indexes point to rows in the preserved component
assignment files where reviewers enter results.

## Legacy assignment preservation

The original unreviewed designs remain committed for provenance:

| Legacy design | Frozen assignments | Plan-v2 use |
| --- | ---: | --- |
| Core second review | 50 | 25 selected into the active reliability file |
| Accela source fidelity | 200 | 15 selected into the targeted portfolio |
| Accela normalization | 125 | 30 selected into the targeted portfolio |
| GIS–Accela linkage | 100 | 30 selected into the targeted portfolio |
| Longitudinal changes | 75 | 25 selected into the initial audit |
| Expanded second-review assignments | 125 | Preserved, not required by plan v2 |

These files must not be deleted or rewritten because they document the earlier
preregistered design. Unselected rows are simply no longer part of the active
completion gate.

## Review and reporting rules

- Human reviewers use non-personal codes, cite public evidence, and keep
  unresolved evidence as `unknown`.
- Independent review remains blinded until both judgments are locked.
- Report core estimates with their evaluated n, sampling universe,
  design-weighted estimate, and 95% confidence interval.
- Report Accela results by component and risk tier; do not estimate global
  Accela accuracy from the targeted portfolio.
- Report longitudinal cases by release cycle and selection reason.
- Never infer real-world construction outcomes from automated reconciliation,
  administrative status, or publication changes.

The machine-readable plan is `config/manual_validation_plan.json`. Its active
subsets are reproduced by `scripts/build_lean_validation_plan.py`.
