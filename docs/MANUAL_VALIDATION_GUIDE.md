# Manual validation: step-by-step operator guide

This guide explains what to do with the frozen manual-validation CSV files.
The controlling definitions and statistical design remain in
[`MANUAL_VALIDATION_PROTOCOL.md`](MANUAL_VALIDATION_PROTOCOL.md).

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
