# Integrated activity dataset

`tampa_development_activity_with_accela.csv` combines the unchanged v0.9.0
eight-layer ArcGIS activity view with bounded Tampa ACA Building and Planning
collections. The current Accela aggregate covers records opened from
2025-08-01 through 2026-08-30.

This is a local expanded edition, not a replacement for the source-bounded
ArcGIS census. It must not be described as a complete census of Tampa permits,
projects, inspections, certificates, construction, or investment.

## Duplicate prevention

Run the deterministic integration with:

```bash
python scripts/integrate_accela.py
```

The script always rebuilds from the unchanged core activity table and the
latest `data/processed/accela_records.csv`; it never merges an already
integrated table back into itself.

Rules are applied in this order:

1. Collapse repeated Accela stable IDs, preserving later nonblank observations.
2. Collapse canonical public record numbers, tolerating punctuation and spacing
   differences only.
3. Merge an Accela record into the core only when its public record number maps
   to exactly one existing activity.
4. Hold ambiguous exact matches for review; fuzzy/address candidates are never
   auto-merged.
5. Assign deterministic activity IDs to unmatched records and fail the build if
   the final activity IDs or integrated Accela record numbers are duplicated.

`accela_integration_audit.csv` records the disposition and match method for
every Accela input. `accela_integration_report.json` records input, merge,
append, ambiguity, and uniqueness counts.

## Temporal evidence

The expanded CSV keeps source event time separate from collector observation
time:

| Field | Meaning |
| --- | --- |
| `event_date` | Selected Tampa/Accela lifecycle date; inspect `event_date_type` before comparison |
| `first_observed_date` | First UTC date TDR collected the record |
| `snapshot_date` | UTC date of the observation supplying the current Accela row |
| `last_observed_date` | Latest UTC date TDR collected the record |
| `historical_reconstruction` | `1` when the selected event predates 2026-08-01 |
| `temporal_evidence` | Controlled classification of the observation |

The 2025-08-01 through 2026-07-31 cohort is labeled
`retrospective_source_record`. It is administrative history retrieved in 2026,
not a set of contemporaneous 2025/2026 snapshots. The 2026-08-01 boundary
starts `prospective_snapshot` evidence. No row is labeled
`retrospective_event_history` because the list-only collection did not capture
a dated status-history feed.

## Current build

- Core activities: 3,323
- Accela input rows: 56,245
- Retrospective Accela source records: 52,264
- Prospective Accela snapshot records: 3,981
- Exact public-number matches merged into core: 1,891
- New Accela activities appended: 54,354
- Ambiguous exact matches held: 0
- Integrated activities: 57,677
- Duplicate final activity IDs: 0
- Duplicate integrated Accela record numbers: 0

`activity_id` is the unique row key. The inherited core data contains 24
groups where a primary `source_record_id` text is reused across source
namespaces or placeholder-ID records. Those are not duplicate activity IDs and
are deliberately not collapsed without stronger entity evidence.

Administrative ACA status text is retained without treating `Complete` as
proof of physical completion. Newly appended records receive evidence grade
`U` and `accela_administrative_record_only` as the realization basis.

`accela_backfill_report.json` validates all 24 requested module-months, their
date boundaries, gap/truncation status, aggregate reconciliation, temporal
classifications, and identifier uniqueness.
