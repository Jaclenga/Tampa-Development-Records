# Manual validation: operator guide

This guide implements the [lean validation plan](../validation/LEAN_VALIDATION_PLAN.md).
The frozen [core protocol](../validation/MANUAL_VALIDATION_PROTOCOL.md) still
controls evidence requirements and field-level decisions.

## Active workload

| Review layer | Required | Completed |
| --- | ---: | ---: |
| Core first review | 150 | 10 |
| Independent core reliability review | 25 | 0 |
| Targeted Accela audit | 75 | 0 |
| Initial longitudinal audit | 30 | 0 |
| **Total** | **280** | **10** |

The legacy Accela, linkage, change-event, and 50-row second-review files are
preserved. Do not review rows that are absent from the active plan-v2 indexes.

## 1. Complete the core sample

Enter first-review results in:

- `data/processed/manual_validation_development_sample.csv` (100 rows); and
- `data/processed/manual_validation_holdout_sample.csv` (50 rows).

Both files now form one pooled 150-row probability sample. Their historical
phase labels remain unchanged for provenance. Do not edit identifiers,
sampling fields, or dataset claims.

For each row:

1. Confirm the source identity using the native ID and official source.
2. Review activity classification, merged-source identity, status semantics,
   physical-work evidence, and any building-footprint match independently.
3. Use only the protocol vocabularies. An unsuccessful search is
   `inconclusive`, not `contradicted`.
4. Record evidence categories and at least one public URL or stable document
   reference.
5. Add ISO 8601 UTC timestamps, a non-personal reviewer code, AI-use disclosure,
   and concise notes.
6. Set `manual_evidence_confirmed=yes` only after a human opens the evidence;
   set `review_status=complete` only after every required field is populated.

Check partial progress with:

```bash
python scripts/review_metrics.py --phase pooled --allow-partial
```

The partial output is exploratory. Final estimates require all 150 first
reviews and all 25 active independent reviews.

## 2. Complete independent review

The second reviewer works only in
`data/processed/manual_validation_core_reliability.csv`. Its 25 cases are a
deterministic stratified subset of the original 50 frozen candidates.

The reviewer must not see the first reviewer's labels, notes, or conclusions
before locking their own results. After both reviews are complete, calculate
agreement from the two original judgments and preserve both during any
adjudication.

Generate final core metrics with:

```bash
python scripts/review_metrics.py --phase pooled
```

Report claim-specific estimates and 95% confidence intervals rather than a
single accuracy score.

## 3. Complete the targeted Accela audit

Open `data/processed/manual_validation_accela_audit_plan.csv`. Each of its 75
rows names a source assignment file and `source_validation_sample_id`. Enter
the review in that named source file only for the listed ID.

| Component | Cases | Primary question |
| --- | ---: | --- |
| Source-fidelity spot checks | 15 | Did TDR capture the City-published identity and fields? |
| Normalization and semantics | 30 | Did TDR transform dates, status, type, and temporal meaning correctly? |
| Linkage and deduplication | 30 | Are matched and retained-unmatched decisions defensible? |

Keep component denominators separate. The portfolio is risk-based and cannot
support a global Accela accuracy estimate. Shared address alone is not linkage
evidence, and a missing live page is not automatically a collection error.

## 4. Complete the longitudinal audit

Open `data/processed/manual_validation_longitudinal_initial_plan.csv`, then
review only the named IDs in
`data/processed/manual_validation_change_events.csv`.

Compare archived before/after values first, then consult the source or archive.
Separate publication refreshes, corrections, and administrative changes. A
detected source difference is not proof that construction started, completed,
or was cancelled.

For later canonical comparisons, preselect 25–40 cases per release cycle:
critical or substantively important flags plus deterministic controls.

## Protect the work

- Save review CSVs as UTF-8 without sorting, deleting, or renumbering rows.
- Do not copy owner, applicant, phone, email, or mailing details into notes.
- Commit completed review files and generated metrics together.
- Preserve an independent backup before any versioned redesign.
- Never use `--force` on the plan builder after review starts.

The study register and current denominators are in
[`verification/README.md`](../../verification/README.md).
