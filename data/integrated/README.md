# Integrated activity dataset

`tampa_development_activity_with_accela.csv` combines the unchanged v0.9.0
eight-layer ArcGIS activity view with the bounded Tampa ACA Building and
Planning collection for records opened from 2026-08-01 through 2026-08-30.

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

## Current build

- Core activities: 3,323
- Accela input rows: 3,981
- Exact public-number matches merged into core: 78
- New Accela activities appended: 3,903
- Ambiguous exact matches held: 0
- Integrated activities: 7,226
- Duplicate final activity IDs: 0
- Duplicate integrated Accela record numbers: 0

`activity_id` is the unique row key. The inherited core data contains 24
groups where a primary `source_record_id` text is reused across source
namespaces or placeholder-ID records. Those are not duplicate activity IDs and
are deliberately not collapsed without stronger entity evidence.

Administrative ACA status text is retained without treating `Complete` as
proof of physical completion. Newly appended records receive evidence grade
`U` and `accela_administrative_record_only` as the realization basis.
