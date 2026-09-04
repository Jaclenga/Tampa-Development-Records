# Integrated activity dataset

`tampa_development_activity_with_accela.csv.gz` combines the unchanged v0.9.0
eight-layer ArcGIS activity view with bounded Tampa ACA Building and Planning
collections. The current Accela aggregate covers records opened from
2020-01-01 through 2026-08-30; January 2020 is the enforced lower boundary.

This is a local expanded edition, not a replacement for the source-bounded
ArcGIS census. It must not be described as a complete census of Tampa permits,
projects, inspections, certificates, construction, or investment.
See the detailed [Accela limitations](../../docs/reference/ACCELA_LIMITATIONS.md) before
using the expanded edition for trends or outcome claims.

The published file is a deterministic gzip-compressed CSV because the complete
uncompressed table exceeds GitHub's ordinary per-file limit. Decompress it
with any gzip-compatible tool. Run
`python scripts/integrate_accela.py --keep-expanded` to retain an ignored local
`tampa_development_activity_with_accela.csv` working copy; the normal build
removes that oversized intermediate after publishing the gzip artifact.

`manifest.json` records the publishable artifacts' byte sizes and SHA-256 hashes,
the integrated row counts, and the January 2020 lower boundary.

The expanded activity CSV remains one row per activity. Public Accela
inspections are stored separately in
`data/processed/accela_inspections.csv` because one permit can have many
inspection events. Join on `record_id`; do not duplicate activity rows to put
multiple inspections into the activity table. The linked table uses a
permit-namespaced `inspection_id`, retains Accela's displayed
`source_inspection_id`, and upserts repeat observations without duplicates.

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

The 2020-01-01 through 2026-07-31 cohort is labeled
`retrospective_source_record`. It is administrative history retrieved in 2026,
not a set of contemporaneous 2025/2026 snapshots. The 2026-08-01 boundary
starts `prospective_snapshot` evidence. Activity rows are not labeled
`retrospective_event_history`; that classification is reserved for explicit
dated rows in the separate inspection history table.

## Current build

- Core activities: 3,323
- Accela input rows: 338,789
- Retrospective Accela source records: 334,808
- Prospective Accela snapshot records: 3,981
- Exact public-number matches merged into core: 2,933
- New Accela activities appended: 335,856
- Ambiguous exact matches held: 0
- Integrated activities: 339,179
- Duplicate final activity IDs: 0
- Duplicate integrated Accela record numbers: 0

`activity_id` is the unique row key. The inherited core data contains 24
groups where a primary `source_record_id` text is reused across source
namespaces or placeholder-ID records. Those are not duplicate activity IDs and
are deliberately not collapsed without stronger entity evidence.

Administrative ACA status text is retained without treating `Complete` as
proof of physical completion. Newly appended records receive evidence grade
`U` and `accela_administrative_record_only` as the realization basis.

`accela_backfill_report.json` validates all 158 requested module-months, their
date boundaries, gap/truncation status, aggregate reconciliation, temporal
classifications, and identifier uniqueness.
