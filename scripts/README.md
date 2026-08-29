# Repository scripts

Run these commands from the repository root. All scripts use only Python's
standard library.

## Build and acquisition

- `build_release.py` orchestrates a complete dataset release.
- `build_tampa_development.py` downloads and normalizes the core City layers.
- `download_hcpa.py` downloads optional HCPA source archives.
- `import_accela_export.py` imports an official Accela CSV export when one is
  available and stages only explicitly delivered lifecycle events.
- `context_modules.py` downloads privacy-whitelisted Budget Book and linked-
  parcel context snapshots, then builds comparison, finance-event, parcel-
  context, and parcel-link tables. Run with `--use-existing-raw` to avoid a
  live refresh.
- `snapshot_tracker.py` writes immutable compact source-record snapshots and,
  once two snapshots exist, publishes deterministic monthly change CSVs,
  summary JSON, and readable Markdown updates. See the detailed
  [tracker methodology](../docs/LONGITUDINAL_TRACKER.md).

## Transformation

- `bounded_census.py` creates source-universe and coverage tables.
- `ground_truth.py` creates evidence, entity-resolution, and source-observation
  event tables without inferring completion.

## Validation and analysis

- `validate_release.py` checks release schemas, relationships, and counts.
- `verify_data_accuracy.py` checks fidelity to the archived source records.
- `validation_study.py` creates the reproducible manual-review sample.
- `review_metrics.py` calculates phase-specific validation metrics.
- `calculate_recall.py` compares the release with sampled official permits.

## Longitudinal tracking

The release build calls the tracker automatically after validation. It is also
safe to run directly; an existing dated snapshot is reused only when its
content hash matches exactly.

```bash
python scripts/snapshot_tracker.py collect-live
python scripts/snapshot_tracker.py update
python scripts/snapshot_tracker.py compare --from-date 2026-08-23 --to-date 2026-09-01
```

Use `collect-live` for the scheduled monthly tracker. It collects the eight
core layers without regenerating the release-specific manual-validation sample.
Use the full release build only when deliberately publishing a new processed
release and validation frame.
