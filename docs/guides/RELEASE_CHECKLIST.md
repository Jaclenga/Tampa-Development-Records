# Release checklist

Version metadata has been advanced to 0.9.0, but the repository has no Git tag.
Use this checklist to turn the current working version into a concrete,
auditable release.

## 1. Finish the evidence work

- Complete all 150 core first reviews across the preserved phase files.
- Complete the active 25-row blinded reliability subset.
- Complete the 75-case targeted Accela audit by component.
- Complete the 30-case initial longitudinal audit.
- Generate pooled core estimates, 95% confidence intervals, and reviewer-agreement metrics.
- Update the README, manifest, verification report, and limitations with only
  the claims supported by those results.

Follow the [manual-validation operator guide](MANUAL_VALIDATION_GUIDE.md), the
[lean plan](../validation/LEAN_VALIDATION_PLAN.md), and the controlling field
[protocol](../validation/MANUAL_VALIDATION_PROTOCOL.md). Do not replace human
review with AI-generated judgments.

## 2. Demonstrate the tracker

- Preserve and inspect the August 23 to September 1 initial comparison.
- Collect the September 30 canonical month-end snapshot; treat September 30 to
  October 31 as the first full month-end-to-month-end interval.
- Inspect the generated change CSV, summary JSON, and Markdown report.
- Confirm that apparent additions and disappearances are described as
  publication changes rather than real-world outcomes.
- Confirm that snapshot and comparison counts reconcile in
  `data/monthly_changes/index.json` and `manifest.json`.
- Confirm that `event_month`, `first_observed_month`, and `snapshot_month`
  remain distinct. Confirm that `data/monthly_events/` contains no dates after
  their source snapshot, `data/planned_events/` contains only explicit future
  plans, and both indexes reconcile with `data/processed/activity_by_month.csv`.

## 3. Run the release checks

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/validate_release.py
python scripts/verify_data_accuracy.py
git diff --check
git status --short
```

Review every changed and untracked file before committing. Live verification
is optional and may differ legitimately when City services have changed since
the archived retrieval:

```bash
python scripts/verify_data_accuracy.py --live
```

## 4. Commit and tag

After the evidence, documentation, and checks are complete:

```bash
git add -A
git commit -m "release: publish v0.9.0"
git tag -a v0.9.0 -m "Tampa Published Development Records v0.9.0"
git push origin main
git push origin v0.9.0
```

The annotated tag should point at the exact commit containing the released
data, code, documentation, validation outputs, and version metadata. Confirm
the tag before announcing the release:

```bash
git show --stat v0.9.0
git tag --verify v0.9.0
```

`git tag --verify` requires a signed tag. If the release tag is intentionally
unsigned, inspect `git show v0.9.0` instead and document that choice.

## 5. Publish a release artifact

- Build the source-bounded ZIP from the tagged commit.
- Record its SHA-256 checksum in the release notes.
- Attach the ZIP and citation metadata to the hosted release.
- State the snapshot date, record counts, validation status, and known
  limitations prominently.
- Link to the tag rather than asking users to infer a release from branch
  history.
