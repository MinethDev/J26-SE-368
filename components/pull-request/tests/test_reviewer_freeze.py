import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reviewer_recommendation import evaluate


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.results = Path(self.directory.name)
        self.selected = self.results / "selected_config.json"
        self.frozen = self.results / "frozen_config.json"

        self.selected.write_text(json.dumps({
            "config": {
                "activity_weight": 0.25,
                "author_weight": 1.0,
                "similarity_weight": 0.25,
                "half_life_days": 90.0,
            },
            "selected_on": "validation",
            "validation_mrr": 0.6,
            "results_file": "validation.json",
        }), encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def freeze(self):
        return evaluate.freeze_config(self.selected, self.frozen)

    def test_freeze_records_config_and_code_state(self):
        record = self.freeze()
        self.assertEqual(record["config"]["author_weight"], 1.0)
        self.assertEqual(record["code_sha256"], evaluate.code_fingerprint())
        self.assertEqual(
            evaluate.check_frozen_config(self.frozen, self.results)["config"],
            record["config"],
        )

    def test_settings_cannot_be_frozen_twice(self):
        self.freeze()
        with self.assertRaises(FileExistsError):
            self.freeze()

    def test_testing_requires_frozen_settings(self):
        with self.assertRaises(FileNotFoundError):
            evaluate.check_frozen_config(self.frozen, self.results)

    def test_code_change_after_freezing_blocks_testing(self):
        self.freeze()
        with mock.patch.object(evaluate, "code_fingerprint", return_value="changed"):
            with self.assertRaises(RuntimeError):
                evaluate.check_frozen_config(self.frozen, self.results)

    def test_test_split_can_only_be_evaluated_once(self):
        self.freeze()
        frozen_sha = evaluate.file_fingerprint(self.frozen)["sha256"]
        (self.results / "test_20260101_000000.json").write_text(
            json.dumps({"run": {"frozen_config_sha256": frozen_sha}}),
            encoding="utf-8",
        )
        with self.assertRaises(FileExistsError):
            evaluate.check_frozen_config(self.frozen, self.results)


if __name__ == "__main__":
    unittest.main()
