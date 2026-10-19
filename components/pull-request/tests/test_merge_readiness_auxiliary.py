import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from merge_readiness import auxiliary, evaluate
from merge_readiness.assessment import LABEL_ATTENTION, LABEL_READY


def synthetic_frame(count=60):
    rows = []

    for index in range(count):
        closed = index % 3 == 0
        rows.append({
            "repo_full_name": "org/repo",
            "pr_number": index + 1,
            "created_at": pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=index),
            "outcome": "closed" if closed else "merged",
            "author_group": "bot" if index % 5 == 0 else "human",
            "label": LABEL_ATTENTION if closed else LABEL_READY,
            "approvals": 0 if closed else 1,
            "change_requests": 1 if closed else 0,
            "reviewers": 1,
            "review_threads": 2,
            "unanswered_threads": 2 if closed else 0,
            "days_since_activity": 30.0 if closed else 1.0,
            "changed_lines": 800 if closed else 50,
        })

    return pd.DataFrame(rows)


class ImportTests(unittest.TestCase):
    def test_merge_readiness_imports_without_modifying_sys_path(self):
        before = list(sys.path)

        for name in ("merge_readiness.config", "merge_readiness.context", "merge_readiness.signals",
                     "merge_readiness.assessment", "merge_readiness.descriptive",
                     "merge_readiness.auxiliary", "merge_readiness.evaluate"):
            importlib.import_module(name)

        self.assertEqual(sys.path, before)


class AuxiliaryBaselineTests(unittest.TestCase):
    def setUp(self):
        self.data = auxiliary.prepare_features(synthetic_frame())
        self.train = self.data[self.data["split"] == "train"]
        self.validation = self.data[self.data["split"] == "validation"]

    def test_target_marks_closed_prs_and_split_is_chronological(self):
        self.assertEqual(int(self.data["target"].sum()), 20)
        self.assertLess(self.train["created_at"].max(), self.validation["created_at"].min())
        self.assertIn("author_is_bot", auxiliary.FEATURES)
        self.assertNotIn("log_days_since_activity", auxiliary.MODEL_VARIANTS[auxiliary.PRIMARY_VARIANT])

    def test_majority_and_rule_predictors(self):
        results = auxiliary.evaluate_split(self.validation, self.train)
        self.assertEqual(results["majority_class"]["all"]["roc_auc"], 0.5)
        self.assertEqual(results["checklist_label_rule"]["all"]["roc_auc"], 1.0)
        self.assertFalse(any(name.startswith("logistic_regression") for name in results))

    def test_logistic_regression_reports_subsets_separately(self):
        c_value, grid = auxiliary.select_c(self.train, self.validation)
        self.assertIn(c_value, auxiliary.C_GRID)
        self.assertEqual(len(grid), len(auxiliary.C_GRID))

        models = {
            variant: auxiliary.fit_logistic(self.train, c_value, features)
            for variant, features in auxiliary.MODEL_VARIANTS.items()
        }
        results = auxiliary.evaluate_split(self.validation, self.train, models)
        primary = f"logistic_regression[{auxiliary.PRIMARY_VARIANT}]"
        self.assertEqual(set(results[primary]), {"all", "human", "bot"})
        self.assertIn("logistic_regression[all_signals_diagnostic]", results)
        weights = auxiliary.coefficients(models[auxiliary.PRIMARY_VARIANT])
        self.assertGreater(weights["change_requests"], 0)
        self.assertNotIn("log_days_since_activity", weights)

    def test_single_class_subset_reports_no_auc(self):
        metrics = auxiliary.classification_metrics([0, 0, 0], [0.1, 0.2, 0.3], [0, 0, 0])
        self.assertIsNone(metrics["roc_auc"])
        self.assertEqual(metrics["n"], 3)

    def test_caveats_state_proxy_limitation(self):
        self.assertTrue(any("not merge readiness" in caveat for caveat in auxiliary.CAVEATS))


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.results = Path(self.directory.name)
        self.selected = self.results / "selected_config.json"
        self.frozen = self.results / "frozen_config.json"
        self.selected.write_text(json.dumps({"selected_c": {"excluding_recent_activity": 1.0}, "primary_variant": "excluding_recent_activity", "selected_on": "validation",
                                             "results_file": "validation.json"}), encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def test_freeze_then_check(self):
        record = evaluate.freeze_config(self.selected, self.frozen)
        self.assertEqual(record["code_sha256"], evaluate.code_fingerprint())
        self.assertEqual(evaluate.check_frozen_config(self.frozen, self.results)["selected_c"], {"excluding_recent_activity": 1.0})

    def test_guards(self):
        with self.assertRaises(FileNotFoundError):
            evaluate.check_frozen_config(self.frozen, self.results)

        evaluate.freeze_config(self.selected, self.frozen)

        with self.assertRaises(FileExistsError):
            evaluate.freeze_config(self.selected, self.frozen)

        with mock.patch.object(evaluate, "code_fingerprint", return_value="changed"):
            with self.assertRaises(RuntimeError):
                evaluate.check_frozen_config(self.frozen, self.results)

        frozen_sha = evaluate._sha256_file(self.frozen)
        (self.results / "test_20260101_000000.json").write_text(
            json.dumps({"run": {"frozen_config_sha256": frozen_sha}}), encoding="utf-8")

        with self.assertRaises(FileExistsError):
            evaluate.check_frozen_config(self.frozen, self.results)


if __name__ == "__main__":
    unittest.main()
