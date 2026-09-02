# Repository scripts

Run these commands from the repository root. Core release scripts use only
Python's standard library. The optional Accela collector uses `requests` from
`requirements.txt`.

## Build and acquisition

- `build_release.py` orchestrates a complete dataset release.
- `build_tampa_development.py` downloads and normalizes the core City layers.
- `download_hcpa.py` downloads optional HCPA source archives.
- `import_accela_export.py` imports an official Accela CSV export when one is
  available and stages only explicitly delivered lifecycle events.
- `collect_accela.py` makes respectful, bounded anonymous searches of Tampa's
  public ACA portal, preserves token-redacted raw provenance, and writes
  normalized snapshots. See the [collector guide](../docs/ACCELA_COLLECTOR.md).
- `collect_and_freeze_month_end.py` collects one completed Accela day into an
  isolated Building/Planning snapshot, verifies gap-free checkpoints, records
  SHA-256 hashes, and then runs the immutable core snapshot tracker.
- `check_repository_privacy.py` blocks publication when tracked or unignored
  files contain workstation home paths or private Git-author email addresses.
  It runs from the repository's pre-commit hook and the monthly snapshot CI job.
- `backfill_accela.py` runs resumable, non-overlapping monthly Building and
  Planning collections through ACA's public Download results control. It
  writes immutable monthly partitions, retries temporary month-level failures,
  and rebuilds shared aggregates once after every requested partition passes.
  The earliest accepted month is January 2020.
- `finalize_accela_record_backfill.py` validates all requested list-only
  partition artifacts and performs the single deferred aggregate merge.
- `run_historical_accela_backfill.ps1` sequences the fast historical export
  backfill ahead of an optional resumed inspection backfill so the two jobs do
  not concurrently access Accela or rewrite shared outputs.
- `validate_accela_backfill.py` reconciles monthly snapshots to the aggregate,
  checks gaps, date bounds, temporal labels, and duplicate identifiers, and
  writes `data/integrated/accela_backfill_report.json`.
- `integrate_accela.py` rebuilds the expanded activity dataset from the core
  activity table and collected Accela rows. Exact public record-number matches
  merge once; unmatched rows receive deterministic IDs; ambiguous matches are
  held for review. See the [integrated dataset notes](../data/integrated/README.md).
- `context_modules.py` downloads privacy-whitelisted Budget Book and linked-
  parcel context snapshots, then builds comparison, finance-event, parcel-
  context, and parcel-link tables. Run with `--use-existing-raw` to avoid a
  live refresh.
- `snapshot_tracker.py` writes immutable compact source-record snapshots and,
  once two snapshots exist, publishes deterministic monthly change CSVs,
  summary JSON, and readable Markdown updates. See the detailed
  [tracker methodology](../docs/LONGITUDINAL_TRACKER.md).
  Live collection reconciles repeated count-only results, the ID-only
  inventory, chunked feature pages, and a final count before archiving; partial
  nonzero layers are rejected.
- `change_analysis.py` contains the deterministic comparison metrics, exact-
  field analysis, transition parsing, identity checks, and configured alerts.
- `analyze_snapshot_changes.py` writes the backward-compatible analysis JSON
  and CSVs and enriches the existing monthly Markdown report.
- `build_change_dashboard.py` generates the static dashboard index and
  identity-safe comparison detail pages without external dependencies.
- `monthly_cohorts.py` builds the cross-snapshot canonical source-date table,
  non-future `monthly_events` extracts, and forward-looking `planned_events`
  extracts while keeping event, first-observed, and snapshot months distinct. See
  [the cohort methodology](../docs/TEMPORAL_COHORTS.md).

## Transformation

- `bounded_census.py` creates source-universe and coverage tables.
- `ground_truth.py` creates evidence, entity-resolution, and source-observation
  event tables without inferring completion.

## Validation and analysis

- `validate_release.py` checks release schemas, relationships, and counts.
- `verify_data_accuracy.py` checks fidelity to the archived source records.
- `validation_study.py` creates the reproducible manual-review sample.
- `review_metrics.py` calculates phase-specific validation metrics.
- `build_verification_summary.py` regenerates the README scorecard and
  `verification/verification_summary.csv` from release and record-level data.
- `calculate_recall.py` compares the release with sampled official permits.

## Longitudinal tracking

The release build calls the tracker automatically after validation. It is also
safe to run directly; an existing dated snapshot is reused only when its
content hash matches exactly.

```bash
python scripts/snapshot_tracker.py collect-live
python scripts/snapshot_tracker.py update
python scripts/snapshot_tracker.py compare --from-date 2026-08-23 --to-date 2026-09-01
python scripts/analyze_snapshot_changes.py --from-date 2026-08-23 --to-date 2026-09-01
python scripts/analyze_snapshot_changes.py --all
python scripts/build_change_dashboard.py
python scripts/monthly_cohorts.py
```

Use `collect-live` for the scheduled monthly tracker. It collects the eight
core layers without regenerating the release-specific manual-validation sample.
The workflow collects on Tampa's last calendar day; manual runs retain the
actual retrieval date and are never relabeled as the prior month-end. Use the
full release build only when deliberately publishing a new processed release
and validation frame.
