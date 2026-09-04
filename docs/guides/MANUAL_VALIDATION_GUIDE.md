# Manual validation: step-by-step operator guide

This guide explains what to do with the distinct frozen manual-validation CSV files.
The controlling definitions and statistical design remain in
[`MANUAL_VALIDATION_PROTOCOL.md`](../validation/MANUAL_VALIDATION_PROTOCOL.md).

The original protocol document governs only the **Core eight-layer manual
validation study**. It does not govern or validate the expanded Accela edition.
The additive study designs are registered in
[`verification/README.md`](../../verification/README.md).

## Current progress and release gate

| Review phase | Required | Completed |
| --- | ---: | ---: |
| Development first review | 100 | 10 |
| Holdout first review | 50 | 0 |
| Blind second review | 50 | 0 |

Core first-review progress is 10 of 150 (6.7%). The completed rows are an
exploratory development-phase diagnostic subset; they are not a population
accuracy estimate. The repository does not yet have an empirical error
baseline. A public release may describe the sample and progress, but it must
not claim measured accuracy, precision, or reviewer agreement until the
applicable rows are complete and the metrics are published. The recommended
v0.9.0 publication sequence is in the [release checklist](RELEASE_CHECKLIST.md).

## What the review data are for

The review rows measure separate questions rather than producing one vague
"accurate/inaccurate" label:

1. Is the source record correctly identified?
2. Is the normalized activity class correct?
3. If sources were merged, do they describe the same activity?
4. Does the normalized stage faithfully represent the source status?
5. Is there evidence that physical work started?
6. If a building footprint was linked, is it the correct building?

The first 100 rows are a **development sample**. Use their results to diagnose
and improve rules. The other 50 rows are a **holdout sample**. Do not inspect
or label the holdout until all rule changes based on the development sample
are frozen. A separately assigned reviewer labels 50 rows without seeing the
first reviewer's answers so reviewer agreement can be measured.

## Files and order

| Order | File | Who uses it | Purpose |
|---:|---|---|---|
| 1 | `data/processed/manual_validation_development_sample.csv` | First reviewer | Develop and diagnose the rules using 100 rows. |
| 2 | `data/processed/manual_validation_second_review.csv`, filtered to `sample_phase=development` | Independent reviewer | Blindly label the 34 development-phase assignments. |
| 3 | Freeze rules and protocol | Project lead | End all rule tuning before either reviewer opens holdout rows. |
| 4 | `data/processed/manual_validation_holdout_sample.csv` | First reviewer | Estimate final performance on 50 untouched rows. |
| 5 | `data/processed/manual_validation_second_review.csv`, filtered to `sample_phase=holdout` | Independent reviewer | Blindly label the 16 holdout assignments. |
| Reference | `data/processed/manual_validation_sample.csv` | Analysis only | Combined sample; do not use it as the primary data-entry file. |

## Review one row

1. Open the appropriate CSV in a spreadsheet program using UTF-8 encoding.
2. Do not edit identifiers, sampling fields, source fields, or dataset claims.
3. Open `source_url` and verify the native record ID, address or location,
   record type, relevant date, and source status.
4. Search official permit, inspection, occupancy, planning, capital-project,
   property, or archived government records for corroborating evidence.
5. Enter one of `supported`, `contradicted`, `inconclusive`, or
   `not_applicable` in every `*_result` column according to the protocol.
6. Populate `reviewed_activity_class` and `reviewed_activity_stage` when the
   associated outcome is supported or contradicted.
7. Enter `present`, `absent`, `unknown`, or `not_applicable` in
   `physical_work_evidence`. Permit issuance or a footprint alone is not
   evidence that work started.
8. Record the evidence categories in `evidence_source_types` and at least one
   public URL or stable document reference. Separate multiple values with
   semicolons.
9. Set `evidence_accessed_at_utc` and `reviewed_at_utc` to ISO 8601 UTC
   timestamps, for example `2026-08-28T15:30:00Z`.
10. Record whether AI helped locate sources in `ai_assistance_used`. AI output
    is not evidence; the reviewer must open the cited source personally.
11. Set `manual_evidence_confirmed=yes`, enter a non-personal reviewer code in
    `reviewer_id`, add concise notes, and set `review_status=complete` only
    after every required field is filled.
12. Save as UTF-8 CSV under the same filename. Do not sort, delete, add, or
    renumber rows.

An unsuccessful search is `inconclusive`, not `contradicted`. Do not put
personal contact information in notes or copy owner or applicant details into
the review files.

## Check progress and use the results

During the development phase, run:

```bash
python scripts/review_metrics.py --phase development --allow-partial
```

Use those exploratory results to identify recurring problems. If a rule is
changed, document the change, rebuild the derived tables, and version the
protocol or release as required. Never tune a rule after examining holdout
answers and then report that same holdout as an untouched test.

When all required development reviews and independent second reviews are
complete, freeze the rules. Then complete the holdout file and run:

```bash
python scripts/review_metrics.py --phase holdout
```

The resulting report may support claim-specific accuracy and agreement
statements. Keep inconclusive and not-applicable counts visible. Do not turn
the outputs into a claim about all Tampa development, construction completion,
or total investment.

## Protect the review work

Commit completed CSVs and generated metrics together. The rebuild process
preserves reviews only while each sampled activity and its review context are
unchanged; it refuses to silently attach an old judgment to changed context.
Keep an independent copy of completed review files before forcing a new sample
or protocol version.

## Expanded Accela and longitudinal studies

These studies answer different questions and must remain in separate files.
All use SHA-256 deterministic rankings, explicit seeds, frozen universe hashes,
stratum-specific inclusion probabilities, and inverse-probability weights.

### Accela source fidelity

- **File:** `manual_validation_accela_source_fidelity.csv`
- **Population:** 338,789 unique Building and Planning records in the completed
  Accela aggregate.
- **Seed and size:** 20260911; 200 rows.
- **Strata:** module, retrospective/prospective observation, event period, and
  common versus relatively rare record type. Allocation is proportional after
  reserving at least two rows for each nonempty stratum.
- **Review question:** does the live or archived City source show the same
  record number, module, type, status, primary date, and identity?
- **Outcomes:** `yes`, `no`, `unknown`, `not_applicable` in each decision field
  and `source_fidelity_outcome`.
- **Inference:** fidelity to the City publication, not real-world occurrence or
  semantic correctness of TDR transformations.

Open the cited source record, compare every requested source field, record the
stable URL or archive reference, and use `unknown` when source evidence is no
longer accessible. A missing page is not automatically evidence that collection
was wrong.

### Accela normalization and semantic correctness

- **File:** `manual_validation_accela_normalization.csv`
- **Population:** 338,589 Accela records after deliberately excluding the 200
  source-fidelity assignments, preventing accidental cross-study reuse.
- **Seed and size:** 20260912; 125 rows.
- **Strata and weights:** the same module, observation, period, and type-rarity
  design; proportional allocation with minimum two per nonempty stratum.
- **Review question:** did TDR select the intended source field and value for
  the event date, normalize status correctly, assign temporal/planned semantics
  correctly, map the activity correctly, and preserve record identity?
- **Inference:** transformation validity only. A correct transformation can
  faithfully preserve an incorrect or incomplete City value.

Evaluate the source-to-normalized rule in code and compare the retained source
fields with the analytical row. Do not use external project outcome evidence to
decide whether the transformation itself was correctly applied.

### GIS–Accela linkage and deduplication

- **File:** `manual_validation_integration_links.csv`
- **Population:** 338,789 integration decisions.
- **Seed and size:** 20260913; 100 cases.
- **Current strata:** 50 exact GIS–Accela matches and 50 retained-unmatched
  Accela records. The builder supports ambiguous/multi-candidate and duplicate-
  suppression strata if those populations become nonempty.
- **Review question:** is the linkage decision supported, was a duplicate
  correctly suppressed, and is there evidence of a false positive, false
  negative, or unresolved ambiguity?
- **Inference:** linkage precision/error characteristics, reported separately
  by decision stratum; never ordinary record-level accuracy.

A shared address alone is insufficient linkage evidence. Use stable record
numbers and uniquely identifying official context. Unmatched review can reveal
false negatives; matched review estimates false-positive risk. Do not combine
those denominators without the published sampling weights.

### Longitudinal change-event validation

- **File:** `manual_validation_change_events.csv`
- **Population:** 2,822 machine-detected changes in the currently archived
  August 23 to September 1 comparison.
- **Seed and size:** 20260914; 75 events.
- **Strata:** detected change type, with proportional allocation and at least
  three rows per nonempty type.
- **Review question:** is the source-field change confirmed, what is its
  defensible semantic interpretation, and is it likely a publication artifact?
- **Inference:** interpretation of detected source changes. It does not prove
  physical development, and collection reconciliation does not answer it.

Compare the prior and current archived values first. Then inspect the source or
archive reference. Keep formatting refreshes, source corrections, and actual
administrative changes distinct. Use `unknown` rather than treating every
machine-detected difference as a substantive real-world event.

## Expanded second review and adjudication

Each new first-review file has an adjacent `_second_review.csv` assignment file:
50 source-fidelity, 31 normalization, 25 linkage, and 19 change-event rows. This
is approximately 25% of each study. The second reviewer must not see the first
reviewer's code, outcome, notes, or evidence judgment before locking
`second_outcome` and `second_review_status=complete`.

After both reviews are locked:

1. copy the original first-review code and outcome into the reconciliation
   fields without modifying either source file;
2. record `agreement=yes`, `no`, `unknown`, or `not_applicable`;
3. set `adjudication_status` to `not_needed`, `pending`, or `complete`;
4. if needed, have a separate adjudicator record `adjudicated_outcome` and
   concise evidence-based notes; and
5. calculate agreement from the two original outcomes, never from the
   adjudicated replacement.

Automated QA and collection-integrity reconciliation are not second review.

## Statistical reporting for new studies

Do not publish an empirical accuracy percentage until the relevant probability
sample is reviewed to its stated completion rule. When supported, report the
evaluated n, sampling universe and hash, weighted estimate, weighting method,
confidence interval, unknown/not-applicable counts, and stratum-level raw counts.
Disproportionate allocation protects small strata, so a simple unweighted total
is descriptive only. Never derive a dataset-wide estimate from the 12-row pilot,
an incomplete sample, a convenience review, or source reconciliation alone.

## Generating new frozen assignments

Run these once for a new versioned study frame:

```bash
python scripts/build_accela_source_fidelity_sample.py
python scripts/build_accela_normalization_sample.py
python scripts/build_integration_validation_sample.py
python scripts/build_change_validation_sample.py
```

The scripts refuse to overwrite existing frozen assignments. `--force` is an
explicit destructive override and must not be used after review begins without
versioning the study and preserving the prior files.
