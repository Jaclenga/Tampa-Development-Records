# Repository scripts

Run these commands from the repository root. All scripts use only Python's
standard library.

## Build and acquisition

- `build_release.py` orchestrates a complete dataset release.
- `build_tampa_development.py` downloads and normalizes the core City layers.
- `download_hcpa.py` downloads optional HCPA source archives.
- `import_accela_export.py` imports an official Accela CSV export when one is
  available.

## Transformation

- `bounded_census.py` creates source-universe and coverage tables.
- `ground_truth.py` creates evidence and entity-resolution tables.

## Validation and analysis

- `validate_release.py` checks release schemas, relationships, and counts.
- `verify_data_accuracy.py` checks fidelity to the archived source records.
- `validation_study.py` creates the reproducible manual-review sample.
- `review_metrics.py` calculates phase-specific validation metrics.
- `calculate_recall.py` compares the release with sampled official permits.
