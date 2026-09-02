import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_automated_validation as reproducibility


class ReproducibilityTests(unittest.TestCase):
    def test_offline_substantive_outputs_repeat_identically(self) -> None:
        temporary_root = reproducibility.ROOT / ".cache"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            root = Path(temporary)
            first = root / "first" / "outputs"
            second = root / "second" / "outputs"
            first_status = reproducibility.generate_substantive_outputs(first, include_privacy=False)
            second_status = reproducibility.generate_substantive_outputs(second, include_privacy=False)
            self.assertTrue(all(code == 0 for code in first_status.values()))
            self.assertEqual(first_status, second_status)
            self.assertEqual(
                reproducibility.analytical_output_manifest(first),
                reproducibility.analytical_output_manifest(second),
            )

    def test_rule_registry_is_hashed_and_runtime_is_non_ai(self) -> None:
        registry = json.loads(reproducibility.RULE_REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(registry["rule_set_version"], "1.0.0")
        self.assertFalse(registry["llm_required_at_runtime"])
        self.assertEqual(len(reproducibility.sha256_file(reproducibility.RULE_REGISTRY)), 64)

    def test_every_frozen_sample_is_hashed(self) -> None:
        hashes = reproducibility.frozen_sample_hashes()
        expected = sorted(
            path.relative_to(reproducibility.ROOT).as_posix()
            for path in (reproducibility.ROOT / "data" / "processed").glob("manual_validation*.csv")
        )
        self.assertEqual(sorted(hashes), expected)
        self.assertTrue(all(len(value) == 64 for value in hashes.values()))


if __name__ == "__main__":
    unittest.main()
