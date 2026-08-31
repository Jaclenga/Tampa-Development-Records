import tempfile
import unittest
from pathlib import Path

from tampa_accela.models import Inspection
from tampa_accela.output import upsert_inspections


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


if __name__ == "__main__":
    unittest.main()
