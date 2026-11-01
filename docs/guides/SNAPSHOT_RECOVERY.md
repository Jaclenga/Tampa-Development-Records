# Durable monthly acquisition and recovery

The monthly pipeline preserves source observations before running report
builders, dependency installation, the test suite, or publication checks.
These are separate acquisition and publication jobs. Failing publication
does not invalidate or delete a successful capture.

## Storage and integrity

Each of the eight layers is collected with repeated count queries, an ID-only
inventory, feature-page reconciliation, and a final count. Source properties
use the existing release privacy scrubber. Each source is immediately written
to `snapshot-captures/YYYY-MM-DD` on the same GitHub repository. The branch is
fetched back and its bytes verified before acquisition proceeds to the next
source. Writes are append-only; conflicting checkpoints fail, never overwrite.
The acquisition process does not change the checked-out branch or its index.

The branch holds `sources/<source>.json` with checksums, source timestamps and
inventory receipts. After all eight pass, it also holds `complete/metadata.json`,
`complete/source_records.csv.gz`, and `complete/receipt.json`. Partial branches
are acquisition checkpoints, not complete or validated dataset publications.

An independent Actions artifact, `tampa-capture-<run-id>`, retains the available
scrubbed checkpoints for 90 days, even when capture fails partway through.
Git checkpoints do not expire with Actions artifacts. Keep these branches;
do not force-push, edit, or automatically delete them. This uses existing
repository write permission and requires no new service credentials.

Publication runs on a fresh runner, reconstructs exclusively from the eight
verified checkpoints, checks immutable complete files, then builds reports and
cohorts, runs all tests, and checks privacy and diffs. Only generated data and
report paths are staged. A publication failure leaves the capture untouched.
The final snapshot includes `collection_receipt.json` and explicit inventory
reconciliation status; this is collection integrity, not human accuracy validation.

## Retry rules and dates

There are three scheduled opportunities on candidate month-end dates: 12:17,
18:17 and 22:17 UTC. The date gate uses America/New_York, including DST and leap
years. Non-month-end candidate days skip collection. Already published,
checksum-verified observations are skipped as well.

Same-day retries reuse each saved source and collect only missing ones. Source
observations may therefore span several hours. Individual timestamps remain in
the receipt; the compact archive's common timestamp is the final source retrieval.
All source observations must belong to the same Tampa day. A source request that
crosses midnight is rejected rather than assigned to the earlier date.

Days 1 and 2 retry the prior month-end using checkpoints only. Missing sources
cannot be reconstructed after midnight: recovery fails explicitly and the gap
remains. Manual past dates also prohibit live queries. This system does not
claim to backfill an observation that was never captured.

## Recover publication without recollecting

From GitHub Actions, dispatch **Month-end Tampa snapshot** with
`observation_date=YYYY-MM-DD`. Leave `verify_only` false. It restores the durable
capture and rebuilds against current main, then repeats publication checks.
The same CLI action is:

```powershell
gh workflow run monthly-snapshot.yml -f observation_date=2026-11-30
```

If a Git checkpoint push failed but the fallback artifact succeeded, also
provide `backup_run_id` for that failed run. The workflow downloads the artifact,
validates source names, configured endpoints, dates, privacy policy, inventory
counts, object-ID uniqueness, and payload hashes, then imports the checkpoints.
It never executes files from the artifact. Conflicting saved bytes are rejected.

```powershell
gh workflow run monthly-snapshot.yml -f observation_date=2026-11-30 -f backup_run_id=RUN_ID
```

Inspect logs if a push to main fails: a newer main commit will be picked up on
the next dispatch, and outputs are rebuilt rather than force-pushed or blindly
rebased. A failing validation must be fixed; recovery does not bypass it.

## Detection and failure drills

The independent **Tampa snapshot watchdog** runs daily at 15:43 UTC. It verifies
the prior month-end archive's compressed and content hashes, source-state hash,
row count and eight-source counts. `config/snapshot_pipeline.json` starts required
coverage at November 30, 2026. September and October gaps remain historical facts;
the watchdog does not repeatedly alert about those already documented gaps.

A missing or corrupt required archive makes the watchdog fail. Enable GitHub
Actions failure notifications for this repository to receive those failures;
this workflow does not send email or external messages itself. Job summaries
also identify the recovery date and branch. GitHub schedules can be delayed or
dropped, so this watchdog is independent of the monthly workflow but is not an
independent hosting provider.

Dispatch with `verify_only=true` to run isolated recovery drills on GitHub's
Linux runner. These use synthetic records and temporary local Git remotes;
they do not query Tampa, create remote capture branches, or publish data.

```powershell
gh workflow run monthly-snapshot.yml -f verify_only=true
python -m pytest -q tests/test_snapshot_pipeline.py
```

The tests cover interrupted acquisition, remote backup failure, later recovery,
checksum corruption, immutable conflicts, midnight boundaries, watchdog
detection, and restoring on a fresh runner without changing its working index.

## Remaining limits

A runner can die between receiving a response and the first remote checkpoint.
Same-day retries reduce that window; no system can preserve a response it never
successfully writes remotely. Git and artifacts provide two storage mechanisms
on GitHub, not protection against loss of the GitHub account or repository.
Off-provider backups or a second scheduler would require separate configured
infrastructure. Source outages, permission changes and genuine validation
failures still prevent publication and should remain visible failures.
