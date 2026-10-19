import json
import tempfile
import unittest
from pathlib import Path

from code_review import benchmark_eval
from code_review.ai_reviewer import (
    CATEGORIES,
    STATUS_FINDINGS,
    STATUS_INVALID,
    STATUS_MODEL_ERROR,
    STATUS_NO_FINDINGS,
    annotate_diff,
)


class BenchmarkIntegrityTests(unittest.TestCase):
    def test_splits_are_paired_and_balanced(self):
        all_ids = set()

        for split in benchmark_eval.SPLITS:
            cases = benchmark_eval.load_cases(split)
            pairs = {}

            for case in cases:
                self.assertNotIn(case["id"], all_ids)
                all_ids.add(case["id"])
                pairs.setdefault(case["pair_id"], set()).add(case["label"])

            self.assertEqual(len(cases), 24, split)
            self.assertTrue(all(labels == {"defect", "clean"} for labels in pairs.values()), split)

    def test_development_and_held_out_do_not_share_code(self):
        development = {c["diff"] for c in benchmark_eval.load_cases("development")}
        held_out = {c["diff"] for c in benchmark_eval.load_cases("held_out")}
        self.assertFalse(development & held_out)

    def test_expected_line_points_to_an_added_line_that_differs_from_the_clean_twin(self):
        for split in benchmark_eval.SPLITS:
            cases = benchmark_eval.load_cases(split)
            clean = {c["pair_id"]: c for c in cases if c["label"] == "clean"}

            for case in (c for c in cases if c["label"] == "defect"):
                expected = case["expected"]
                annotated = {
                    int(line.split("|")[0]): line.split("|", 1)[1][1:]
                    for line in annotate_diff(case["diff"]).splitlines()[1:]
                    if line.split("|")[0].strip()
                }
                line = annotated[expected["line"]]
                self.assertTrue(line.startswith("+"), case["id"])
                self.assertIn(expected["category"], expected["acceptable_categories"])
                self.assertTrue(set(expected["acceptable_categories"]) <= set(CATEGORIES))
                self.assertNotEqual(case["diff"], clean[case["pair_id"]]["diff"])

    def test_held_out_matches_freeze_manifest(self):
        manifest = benchmark_eval.check_held_out_frozen()
        self.assertEqual(manifest["cases"], 24)

    def test_changed_held_out_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "held_out.json"
            changed.write_text(benchmark_eval.HELD_OUT_FILE.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                benchmark_eval.check_held_out_frozen(changed, benchmark_eval.HELD_OUT_MANIFEST)

    def test_held_out_can_only_be_evaluated_once(self):
        manifest = benchmark_eval.check_held_out_frozen()

        with tempfile.TemporaryDirectory() as directory:
            benchmark_eval.check_held_out_not_evaluated(manifest, directory)
            (Path(directory) / "benchmark_held_out_20260101_000000.json").write_text(
                json.dumps({"run": {"held_out_sha256": manifest["sha256_lf_normalized"]}}), encoding="utf-8")
            with self.assertRaises(FileExistsError):
                benchmark_eval.check_held_out_not_evaluated(manifest, directory)


def record(pair, label, status, findings=(), line=10, acceptable=("correctness",)):
    return {
        "id": f"{pair}-{label}",
        "pair_id": pair,
        "label": label,
        "language": "python",
        "expected": {"line": line, "acceptable_categories": list(acceptable)} if label == "defect" else None,
        "result": {"status": status, "findings": list(findings)},
    }


def finding(line=10, category="correctness"):
    return {"line": line, "category": category}


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            # p1: detected, right line and category; clean twin quiet -> correct pair.
            record("p1", "defect", STATUS_FINDINGS, [finding(10)]),
            record("p1", "clean", STATUS_NO_FINDINGS),
            # p2: detected, line off by 1 (hit), wrong category; clean twin flagged.
            record("p2", "defect", STATUS_FINDINGS, [finding(11, "security")]),
            record("p2", "clean", STATUS_FINDINGS, [finding(3)]),
            # p3: missed; clean quiet.
            record("p3", "defect", STATUS_NO_FINDINGS),
            record("p3", "clean", STATUS_NO_FINDINGS),
            # p4: detected but wrong line (miss) and no category hit; clean invalid.
            record("p4", "defect", STATUS_FINDINGS, [finding(30, "security")]),
            record("p4", "clean", STATUS_INVALID),
            # p5: model error on defect; clean quiet.
            record("p5", "defect", STATUS_MODEL_ERROR),
            record("p5", "clean", STATUS_NO_FINDINGS),
        ]
        self.metrics = benchmark_eval.compute_metrics(self.records)

    def value(self, name):
        metric = self.metrics[name]
        return metric["numerator"], metric["denominator"]

    def test_detection_and_false_positive_rates(self):
        self.assertEqual(self.value("detection_rate"), (3, 4))       # p5 defect excluded (error)
        self.assertEqual(self.value("false_positive_rate"), (1, 4))  # p4 clean excluded (invalid)

    def test_localized_detection_uses_all_valid_defects(self):
        self.assertEqual(self.value("localized_detection_rate"), (2, 4))  # p1, p2 within tolerance

    def test_precision(self):
        self.assertEqual(self.value("precision"), (3, 4))  # 3 detected defects + 1 flagged clean

    def test_line_and_category_accuracy_use_detected_defects(self):
        self.assertEqual(self.value("line_accuracy"), (2, 3))      # p1 exact, p2 within tolerance
        self.assertEqual(self.value("category_accuracy"), (1, 3))  # only p1

    def test_pair_accuracy_requires_both_valid(self):
        self.assertEqual(self.value("pair_accuracy"), (1, 3))  # p1 correct; p4, p5 incomplete

    def test_error_and_invalid_rates_use_all_cases(self):
        self.assertEqual(self.value("invalid_response_rate"), (1, 10))
        self.assertEqual(self.value("model_error_rate"), (1, 10))
        self.assertEqual(self.metrics["status_counts"][STATUS_FINDINGS], 4)

    def test_conservative_detection_counts_invalid_and_errors_as_misses(self):
        self.assertEqual(self.value("conservative_detection_rate"), (3, 5))            # all 5 defect cases
        self.assertEqual(self.value("conservative_localized_detection_rate"), (2, 5))  # p5 error = miss

    def test_conservative_pair_accuracy_counts_invalid_pairs_as_failures(self):
        self.assertEqual(self.value("conservative_pair_accuracy"), (1, 5))  # p4 invalid, p5 error fail

    def test_valid_response_metrics_are_unchanged_by_conservative_variants(self):
        self.assertEqual(self.value("detection_rate"), (3, 4))
        self.assertEqual(self.value("pair_accuracy"), (1, 3))
        self.assertIn("valid response", self.metrics["detection_rate"]["definition"])

    def test_conservative_variants_equal_primary_when_all_valid(self):
        records = [record("p1", "defect", STATUS_FINDINGS, [finding(10)]),
                   record("p1", "clean", STATUS_NO_FINDINGS),
                   record("p2", "defect", STATUS_NO_FINDINGS),
                   record("p2", "clean", STATUS_NO_FINDINGS)]
        metrics = benchmark_eval.compute_metrics(records)
        for name in ("detection_rate", "localized_detection_rate", "pair_accuracy"):
            self.assertEqual(metrics[name]["value"], metrics[f"conservative_{name}"]["value"], name)

    def test_line_accuracy_unavailable_without_line_field(self):
        v1_records = [record("p1", "defect", STATUS_FINDINGS, [{"finding": "x"}]),
                      record("p1", "clean", STATUS_NO_FINDINGS)]
        metrics = benchmark_eval.compute_metrics(v1_records)
        self.assertIsNone(metrics["line_accuracy"]["value"])
        self.assertIn("Not available", metrics["line_accuracy"]["note"])

    def test_every_metric_has_a_definition(self):
        for name in benchmark_eval.METRIC_DEFINITIONS:
            self.assertIn("definition", self.metrics[name])


class ResultFileTests(unittest.TestCase):
    def test_results_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.json"
            benchmark_eval._write_json({"a": 1}, path)
            with self.assertRaises(FileExistsError):
                benchmark_eval._write_json({"a": 2}, path)

    def test_real_data_summary_is_descriptive(self):
        records = [{"result": {"status": STATUS_FINDINGS, "findings": [finding()]}},
                   {"result": {"status": STATUS_NO_FINDINGS, "findings": []}}]
        summary = benchmark_eval.describe_real_data(records)
        self.assertEqual(summary["cases_with_findings"], 1)
        self.assertIn("not verified bug labels", summary["note"])


if __name__ == "__main__":
    unittest.main()
