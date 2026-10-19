"""
Run-marker guard, common-valid-pairs comparison, and sensitivity analysis.

Guard tests use synthetic held-out cases in a temporary directory and a fake
model client. The real held_out.json and its run marker are never touched.
"""

import hashlib
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from code_review import benchmark_eval
from code_review.ai_reviewer import (
    STATUS_FINDINGS,
    STATUS_INVALID,
    STATUS_MODEL_ERROR,
    STATUS_NO_FINDINGS,
    ModelError,
)
from code_review.benchmark_eval import HeldOutRunAlreadyStarted


def synthetic_case(pair, label):
    return {
        "id": f"{pair}-{label}",
        "pair_id": pair,
        "label": label,
        "language": "python",
        "pr_title": "Synthetic change",
        "file_path": "synthetic.py",
        "diff": "@@ -1,1 +1,2 @@\n def f(x):\n+    return 1 / x" if label == "defect"
                else "@@ -1,1 +1,2 @@\n def f(x):\n+    return x",
        "expected": {"line": 2, "category": "correctness", "acceptable_categories": ["correctness"]}
                    if label == "defect" else None,
    }


def make_benchmark(directory) -> Path:
    """Write a synthetic held-out file and its freeze manifest."""

    directory = Path(directory)
    cases = [synthetic_case(p, l) for p in ("syn-01", "syn-02") for l in ("defect", "clean")]
    held_out = directory / "held_out.json"
    held_out.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    digest = hashlib.sha256(held_out.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    (directory / "held_out.freeze.json").write_text(
        json.dumps({"sha256_lf_normalized": digest, "frozen_at_utc": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8")
    return directory


class GuardFakeClient:
    """Fake model client that records calls and checks the marker exists before any chat."""

    model = "fake-model"

    def __init__(self, marker_path, fail_on_call=None, metadata_error=False):
        self.marker_path = Path(marker_path)
        self.fail_on_call = fail_on_call
        self.metadata_error = metadata_error
        self.metadata_calls = 0
        self.chat_calls = 0
        self.marker_existed_at_first_chat = None

    def resolve_options(self):
        self.metadata_calls += 1
        metadata = {"model": self.model}
        if self.metadata_error:
            metadata["error"] = "Could not connect to Ollama."
        return {"temperature": 0}, metadata

    def chat(self, messages, options, response_format="json"):
        self.chat_calls += 1
        if self.marker_existed_at_first_chat is None:
            self.marker_existed_at_first_chat = self.marker_path.exists()
        if self.fail_on_call == self.chat_calls:
            raise KeyboardInterrupt("simulated interruption")
        return '{"findings": []}'


class ScriptedClient(GuardFakeClient):
    """Returns scripted replies in order: "ok" = no findings, an exception = model-call failure."""

    def __init__(self, marker_path, script):
        super().__init__(marker_path)
        self.script = list(script)

    def chat(self, messages, options, response_format="json"):
        self.chat_calls += 1
        if self.marker_existed_at_first_chat is None:
            self.marker_existed_at_first_chat = self.marker_path.exists()
        reply = self.script.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return '{"findings": []}' if reply == "ok" else reply


class RunMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "benchmark").mkdir()
        self.benchmark = make_benchmark(root / "benchmark")
        self.results = root / "results"
        self.marker = self.benchmark / "held_out.run_marker.json"

    def tearDown(self):
        self.temporary.cleanup()

    def run_held_out(self, client):
        return benchmark_eval.run_benchmark(
            "held_out", ["v2", "v3"], client,
            results_dir=self.results, benchmark_dir=self.benchmark, marker_path=self.marker,
        )

    def test_marker_is_created_before_the_first_model_call_and_completed(self):
        client = GuardFakeClient(self.marker)
        results = self.run_held_out(client)

        self.assertTrue(client.marker_existed_at_first_chat)
        self.assertEqual(client.chat_calls, 8)
        marker = json.loads(self.marker.read_text(encoding="utf-8"))
        self.assertEqual(marker["status"], "completed")
        self.assertEqual(marker["prompt_versions"], ["v2", "v3"])
        self.assertEqual(marker["results_path"], results["results_path"])
        for field in ("held_out_sha256", "prompt_sha256", "started_at_utc", "ended_at_utc"):
            self.assertIn(field, marker)

    def test_existing_marker_stops_the_run_before_any_model_contact(self):
        self.run_held_out(GuardFakeClient(self.marker))
        before = self.marker.read_text(encoding="utf-8")

        client = GuardFakeClient(self.marker)
        with self.assertRaises(HeldOutRunAlreadyStarted) as raised:
            self.run_held_out(client)

        self.assertEqual((client.metadata_calls, client.chat_calls), (0, 0))
        self.assertEqual(self.marker.read_text(encoding="utf-8"), before)
        self.assertIn("Investigate", str(raised.exception))

    def test_interrupted_run_is_recorded_and_blocks_reruns(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_held_out(GuardFakeClient(self.marker, fail_on_call=2))

        marker = json.loads(self.marker.read_text(encoding="utf-8"))
        self.assertEqual(marker["status"], "failed")
        self.assertIn("simulated interruption", marker["error"])
        self.assertFalse(list(self.results.glob("benchmark_held_out_*.json")))

        client = GuardFakeClient(self.marker)
        with self.assertRaises(HeldOutRunAlreadyStarted):
            self.run_held_out(client)
        self.assertEqual(client.chat_calls, 0)

    def test_marker_left_in_started_state_blocks_reruns(self):
        benchmark_eval.create_run_marker("sha", ["v3"], self.marker)  # e.g. process killed mid-run

        client = GuardFakeClient(self.marker)
        with self.assertRaises(HeldOutRunAlreadyStarted):
            self.run_held_out(client)
        self.assertEqual(client.chat_calls, 0)

    def test_unavailable_model_metadata_does_not_start_a_run(self):
        client = GuardFakeClient(self.marker, metadata_error=True)
        with self.assertRaises(ModelError):
            self.run_held_out(client)

        self.assertFalse(self.marker.exists())
        self.assertEqual(client.chat_calls, 0)

    def test_first_model_error_stops_the_run_and_blocks_retries(self):
        client = ScriptedClient(self.marker, ["ok", ModelError("connection refused"), "ok", "ok"])

        with self.assertRaises(benchmark_eval.RunAbortedOnModelError) as raised:
            self.run_held_out(client)

        self.assertEqual(client.chat_calls, 2)  # no case is sent after the failure
        self.assertEqual(raised.exception.cases_sent, 2)
        self.assertEqual(raised.exception.case_id, "syn-01-clean")
        marker = json.loads(self.marker.read_text(encoding="utf-8"))
        self.assertEqual(marker["status"], "failed")
        self.assertEqual(marker["cases_sent"], 2)
        self.assertIn("connection refused", marker["error"])
        self.assertFalse(list(self.results.glob("benchmark_held_out_*.json")))

        retry = GuardFakeClient(self.marker)
        with self.assertRaises(HeldOutRunAlreadyStarted):
            self.run_held_out(retry)
        self.assertEqual((retry.metadata_calls, retry.chat_calls), (0, 0))

    def test_model_error_in_a_later_prompt_also_stops_the_run(self):
        client = ScriptedClient(self.marker, ["ok"] * 4 + [ModelError("timeout")] + ["ok"] * 3)

        with self.assertRaises(benchmark_eval.RunAbortedOnModelError) as raised:
            self.run_held_out(client)

        self.assertEqual(client.chat_calls, 5)
        self.assertEqual(raised.exception.prompt_version, "v3")
        self.assertEqual(json.loads(self.marker.read_text(encoding="utf-8"))["cases_sent"], 5)

    def test_invalid_responses_do_not_stop_the_run(self):
        client = ScriptedClient(self.marker, ["not json", "ok", '{"findings": {}}', "ok"] * 2)
        results = self.run_held_out(client)

        self.assertEqual(client.chat_calls, 8)
        counts = results["results"]["v2"]["metrics"]["status_counts"]
        self.assertEqual((counts[STATUS_INVALID], counts[STATUS_MODEL_ERROR]), (2, 0))
        marker = json.loads(self.marker.read_text(encoding="utf-8"))
        self.assertEqual((marker["status"], marker["cases_sent"]), ("completed", 8))

    def test_development_runs_continue_after_model_errors(self):
        (self.benchmark / "development.json").write_text(
            json.dumps({"cases": [synthetic_case("dev-x", "defect"), synthetic_case("dev-x", "clean")]}),
            encoding="utf-8")
        client = ScriptedClient(self.marker, [ModelError("refused"), "ok"])
        results = benchmark_eval.run_benchmark("development", ["v3"], client,
                                               results_dir=self.results, benchmark_dir=self.benchmark)

        self.assertEqual(client.chat_calls, 2)
        self.assertEqual(results["results"]["v3"]["metrics"]["status_counts"][STATUS_MODEL_ERROR], 1)

    def test_marker_creation_is_exclusive(self):
        first = benchmark_eval.create_run_marker("sha", ["v3"], self.marker)
        with self.assertRaises(HeldOutRunAlreadyStarted):
            benchmark_eval.create_run_marker("other", ["v1"], self.marker)
        self.assertEqual(json.loads(self.marker.read_text(encoding="utf-8")), first)

    def test_development_runs_do_not_create_a_marker(self):
        (self.benchmark / "development.json").write_text(
            json.dumps({"cases": [synthetic_case("dev-x", "defect"), synthetic_case("dev-x", "clean")]}),
            encoding="utf-8")
        benchmark_eval.run_benchmark("development", ["v3"], GuardFakeClient(self.marker),
                                     results_dir=self.results, benchmark_dir=self.benchmark)
        self.assertFalse(self.marker.exists())

    def test_marker_is_never_deleted_and_there_is_no_reset_command(self):
        sources = inspect.getsource(benchmark_eval)
        runner = (Path(benchmark_eval.__file__).resolve().parents[1] / "run_code_review_benchmark.py").read_text(
            encoding="utf-8")
        for forbidden in ("unlink", "os.remove", "rmtree"):
            self.assertNotIn(forbidden, sources)
            self.assertNotIn(forbidden, runner)
        for word in ("reset", "recover", "--force"):
            self.assertNotIn(word, runner.lower())


def record(pair, label, status, findings=()):
    return {
        "id": f"{pair}-{label}",
        "pair_id": pair,
        "label": label,
        "language": "python",
        "expected": {"line": 10, "acceptable_categories": ["correctness"]} if label == "defect" else None,
        "result": {"status": status, "findings": list(findings)},
    }


FOUND = [{"line": 10, "category": "correctness"}]


def prompt_records(invalid_pairs=(), error_pairs=(), pairs=("p1", "p2", "p3")):
    records = []
    for pair in pairs:
        defect_status = (STATUS_INVALID if pair in invalid_pairs else
                         STATUS_MODEL_ERROR if pair in error_pairs else STATUS_FINDINGS)
        records.append(record(pair, "defect", defect_status, FOUND if defect_status == STATUS_FINDINGS else ()))
        records.append(record(pair, "clean", STATUS_NO_FINDINGS))
    return records


class CommonValidPairsTests(unittest.TestCase):
    def test_pairs_invalid_under_any_prompt_are_excluded_for_all_prompts(self):
        comparison = benchmark_eval.common_valid_pairs_comparison({
            "v1": prompt_records(),
            "v2": prompt_records(invalid_pairs=("p2",)),
            "v3": prompt_records(error_pairs=("p3",)),
        })

        self.assertEqual(comparison["pair_ids"], ["p1"])
        self.assertEqual(comparison["excluded_pair_ids"], ["p2", "p3"])
        for version in ("v1", "v2", "v3"):
            self.assertEqual(comparison["metrics"][version]["cases"], 2)
            self.assertEqual(comparison["metrics"][version]["pair_accuracy"]["denominator"], 1)

    def test_comparison_requires_all_three_prompts(self):
        comparison = benchmark_eval.common_valid_pairs_comparison({"v2": prompt_records(), "v3": prompt_records()})
        self.assertIsNone(comparison["value"])
        self.assertIn("v1", comparison["note"])


class SensitivityAnalysisTests(unittest.TestCase):
    def setUp(self):
        pairs = ("held-01", "held-04", "held-05", "held-07", "held-10")
        self.records = {v: prompt_records(pairs=pairs) for v in ("v1", "v2", "v3")}

    def test_filter_removes_both_cases_of_each_excluded_pair(self):
        kept = benchmark_eval.filter_pairs(self.records["v3"], exclude=benchmark_eval.SENSITIVITY_EXCLUDED_PAIRS)
        self.assertEqual(sorted({r["pair_id"] for r in kept}), ["held-01", "held-07"])
        self.assertEqual(len(kept), 4)

    def test_sensitivity_is_labelled_diagnostic_and_keeps_primary_results(self):
        analysis = benchmark_eval.analyze_records(self.records, "held_out")

        self.assertEqual(analysis["primary"]["v3"]["cases"], 10)
        sensitivity = analysis["diagnostic_sensitivity"]
        self.assertIn("DIAGNOSTIC", sensitivity["label"])
        self.assertIn("potentially biased", sensitivity["label"])
        self.assertEqual(sensitivity["excluded_pair_ids"], ["held-04", "held-05", "held-10"])
        self.assertEqual(sensitivity["metrics"]["v3"]["cases"], 4)

    def test_sensitivity_is_only_produced_for_held_out(self):
        self.assertNotIn("diagnostic_sensitivity", benchmark_eval.analyze_records(self.records, "development"))


if __name__ == "__main__":
    unittest.main()
