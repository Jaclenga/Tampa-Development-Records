"""Failure drills for durable capture and publication recovery (no live APIs)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import snapshot_pipeline as pipeline

DATE = "2026-11-30"
NOW = dt.datetime(2026, 11, 30, 18, tzinfo=dt.timezone.utc)
SOURCES = {name: f"https://example.test/{name}" for name in pipeline.endpoints()}


def collection(count=400):
    return {
        "features": [{"properties": {
            "OBJECTID": i, "GlobalID": f"g-{i}", "projname": f"Project {i}",
            "POCEmail": "excluded@example.test",
        }} for i in range(1, count + 1)],
        "collection_integrity": {
            "passed": True, "count_only": count, "id_only": count,
            "paginated_feature_count": count, "final_count_only": count,
        },
    }


class MemoryArchive:
    def __init__(self):
        self.files = {}

    def read(self, name):
        return self.files.get(name)

    def put(self, files):
        for name, content in files.items():
            if name in self.files and self.files[name] != content:
                raise RuntimeError("immutable checkpoint conflict")
        self.files.update(files)


class SnapshotPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backup = self.root / "backup"
        self.store = MemoryArchive()
        self.patch = mock.patch.object(pipeline, "endpoints", return_value=SOURCES)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def capture(self, **kwargs):
        return pipeline.capture(
            DATE, self.store, self.backup, now=lambda: NOW,
            fetch=kwargs.pop("fetch", lambda *a, **kw: collection()),
            allow_live=kwargs.pop("allow_live", True), **kwargs,
        )

    def test_runner_loss_resumes_only_missing_sources(self):
        fetch = mock.Mock(side_effect=[collection(), RuntimeError("runner lost")])
        with self.assertRaisesRegex(RuntimeError, "runner lost"):
            self.capture(fetch=fetch)
        self.assertEqual(len(self.store.files), 1)
        fetch = mock.Mock(return_value=collection())
        self.capture(fetch=fetch)
        self.assertEqual(fetch.call_count, 7)
        self.assertEqual(len(self.store.files), 11)

    def test_remote_backup_failure_preserves_local_scrubbed_source(self):
        self.store.put = mock.Mock(side_effect=RuntimeError("remote unavailable"))
        with self.assertRaisesRegex(RuntimeError, "remote unavailable"):
            self.capture()
        saved = list((self.backup / "sources").glob("*.json"))
        self.assertEqual(len(saved), 1)
        self.assertFalse("excluded@example.test" in saved[0].read_text())
        self.assertFalse((self.backup / "complete").exists())

    def test_publication_failure_recovers_after_midnight_without_network(self):
        original = self.capture()
        network = mock.Mock(side_effect=AssertionError("must not query live sources"))
        recovered = self.capture(allow_live=False, fetch=network)
        self.assertEqual(recovered, original)
        network.assert_not_called()
        restored = pipeline.restore(DATE, self.store, self.root / "snapshots")
        self.assertEqual(restored, original)
        self.assertEqual(
            (self.root / "snapshots" / DATE / "source_records.csv.gz").read_bytes(),
            self.store.files["complete/source_records.csv.gz"],
        )
        self.assertTrue((self.root / "snapshots" / DATE / "collection_receipt.json").is_file())

    def test_missing_past_source_never_gets_recollected_or_backdated(self):
        network = mock.Mock(side_effect=AssertionError("no live data"))
        with self.assertRaisesRegex(RuntimeError, "cannot reconstruct"):
            self.capture(allow_live=False, fetch=network)
        network.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "cannot reconstruct"):
            pipeline.capture(
                DATE, self.store, self.backup, allow_live=True,
                now=lambda: NOW + dt.timedelta(days=1), fetch=network,
            )

    def test_corrupt_source_checkpoint_blocks_recovery(self):
        self.capture()
        name = next(name for name in self.store.files if name.startswith("sources/"))
        payload = json.loads(self.store.files[name])
        payload["rows"][0]["source_object_id"] = "tampered"
        self.store.files[name] = pipeline.encoded(payload)
        with self.assertRaisesRegex(RuntimeError, "Invalid source checkpoint"):
            self.capture(allow_live=False)

    def test_corrupt_complete_snapshot_is_not_replaced_or_published(self):
        self.capture()
        self.store.files["complete/source_records.csv.gz"] = b"damaged"
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            pipeline.restore(DATE, self.store, self.root / "snapshots")
        self.assertFalse((self.root / "snapshots" / DATE).exists())

    def test_midnight_boundary_refuses_mixed_day_capture(self):
        times = iter([
            dt.datetime(2026, 12, 1, 4, 59, tzinfo=dt.timezone.utc),
            dt.datetime(2026, 12, 1, 4, 59, tzinfo=dt.timezone.utc),
            dt.datetime(2026, 12, 1, 5, 1, tzinfo=dt.timezone.utc),
        ])
        with self.assertRaisesRegex(RuntimeError, "crossed Tampa midnight"):
            pipeline.capture(DATE, self.store, self.backup, allow_live=True,
                             now=lambda: next(times), fetch=lambda *a, **kw: collection())
        self.assertFalse(self.store.files)

    def test_restoring_conflicting_published_snapshot_is_rejected(self):
        self.capture()
        directory = self.root / "snapshots" / DATE
        directory.mkdir(parents=True)
        (directory / "metadata.json").write_text("do not overwrite")
        with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
            pipeline.restore(DATE, self.store, directory.parent)
        self.assertEqual((directory / "metadata.json").read_text(), "do not overwrite")

    def test_schedule_handles_leap_year_dst_and_recovery_days(self):
        leap = dt.datetime(2028, 2, 29, 18, tzinfo=dt.timezone.utc)
        self.assertEqual(pipeline.plan("schedule", now=leap)["target_date"], "2028-02-29")
        next_day = dt.datetime(2026, 12, 1, 18, tzinfo=dt.timezone.utc)
        decision = pipeline.plan("schedule", now=next_day)
        self.assertEqual(decision["target_date"], DATE)
        self.assertEqual(decision["allow_live"], "false")
        self.assertEqual(pipeline.plan("schedule", now=NOW - dt.timedelta(days=1))["should_run"], "false")
        tampa_oct31 = dt.datetime(2026, 11, 1, 2, tzinfo=dt.timezone.utc)
        self.assertEqual(pipeline.plan("schedule", now=tampa_oct31)["target_date"], "2026-10-31")
        with self.assertRaises(ValueError):
            pipeline.plan("workflow_dispatch", "2026-12-01", now=NOW)

    def test_watchdog_detects_missing_and_corrupt_publication(self):
        config = self.root / "config"
        config.mkdir()
        (config / "snapshot_pipeline.json").write_text(json.dumps({"first_required_month_end": DATE}))
        self.assertIn("Monitoring starts", pipeline.watchdog(self.root, NOW))
        december = NOW + dt.timedelta(days=1)
        with self.assertRaises(FileNotFoundError):
            pipeline.watchdog(self.root, december)
        self.capture()
        pipeline.restore(DATE, self.store, self.root / "data" / "snapshots")
        self.assertIn("verified", pipeline.watchdog(self.root, december))
        (self.root / "data" / "snapshots" / DATE / "source_records.csv.gz").write_bytes(b"bad")
        with self.assertRaises(Exception):
            pipeline.watchdog(self.root, december)

    def test_git_remote_survives_new_runner_and_preserves_main_index(self):
        remote, runner1, runner2 = (self.root / name for name in ("remote.git", "runner1", "runner2"))
        def git(*args):
            return subprocess.run(["git", *map(str, args)], check=True, capture_output=True).stdout
        git("init", "--bare", remote)
        for runner in (runner1, runner2):
            git("init", runner)
            git("-C", runner, "remote", "add", "origin", remote)
        (runner1 / "sentinel.txt").write_text("staged main change")
        git("-C", runner1, "add", "sentinel.txt")
        index_before = git("-C", runner1, "ls-files", "--stage")
        store = pipeline.GitArchive(DATE, runner1)
        pipeline.capture(DATE, store, self.backup, allow_live=True,
                         now=lambda: NOW, fetch=lambda *a, **kw: collection())
        self.assertEqual(git("-C", runner1, "ls-files", "--stage"), index_before)
        fresh = pipeline.GitArchive(DATE, runner2)
        pipeline.restore(DATE, fresh, self.root / "restored")
        self.assertEqual(
            (self.root / "restored" / DATE / "source_records.csv.gz").read_bytes(),
            store.read("complete/source_records.csv.gz"),
        )
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            fresh.put({"complete/metadata.json": b"overwrite"})


if __name__ == "__main__":
    unittest.main()
