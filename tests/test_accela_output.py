import json
import tempfile
import unittest
from pathlib import Path

from tampa_accela.models import CollectionResult, Inspection, NormalizedRecord
from tampa_accela.output import merge_snapshot_records, upsert_inspections, write_collection_outputs


class AccelaInspectionOutputTests(unittest.TestCase):
    def test_upsert_is_idempotent_and_preserves_observation_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inspections.csv"
            first = Inspection(
                record_id="acc-1", inspection_id="ins-1", source_inspection_id="42",
                inspection_type="Final", result_date="2026-07-01",
                retrieved_at="2026-08-31T00:00:00Z", raw_source_file="first.html.gz",
            )
            later = Inspection(
                record_id="acc-1", inspection_id="ins-1", source_inspection_id="42",
                inspection_type="Final", result="Approved", result_date="2026-07-01",
                retrieved_at="2026-09-30T00:00:00Z", raw_source_file="later.html.gz",
            )
            upsert_inspections(path, [first])
            output = upsert_inspections(path, [later, later])
            self.assertEqual(len(output), 1)
            self.assertEqual(output[0]["result"], "Approved")
            self.assertEqual(output[0]["first_observed_date"], "2026-08-31")
            self.assertEqual(output[0]["last_observed_date"], "2026-09-30")
            self.assertEqual(output[0]["temporal_evidence"], "retrospective_event_history")

    def test_snapshot_only_partition_can_be_merged_once_after_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            result = CollectionResult(
                records=[NormalizedRecord(
                    source_module="Building",
                    record_id="acc-1",
                    record_number="BLD-20-1",
                    opened_date="2020-01-02",
                    retrieved_at="2026-09-01T00:00:00+00:00",
                )],
                checkpoint_path="checkpoint.json",
                pages=1,
                requests=4,
            )
            paths = write_collection_outputs(
                output_dir,
                result,
                module="Building",
                run_id="backfill-2020-01",
                query={"use_export": True, "snapshot_only": True},
                update_current=False,
            )
            self.assertNotIn("current", paths)
            self.assertFalse((output_dir / "accela_records.csv").exists())
            summary = json.loads(Path(paths["summary"]).read_text(encoding="utf-8"))
            self.assertFalse(summary["aggregate_updated"])

            report = merge_snapshot_records(output_dir, [Path(paths["snapshot"])])
            self.assertEqual(report["snapshots_merged"], 1)
            self.assertEqual(report["aggregate_records"], 1)
            self.assertTrue((output_dir / "accela_records.csv").exists())
            self.assertTrue((output_dir / "accela_building_records.csv").exists())


if __name__ == "__main__":
    unittest.main()
