import json
import unittest

from code_review import ai_reviewer
from code_review.ai_reviewer import (
    STATUS_FINDINGS,
    STATUS_INVALID,
    STATUS_MODEL_ERROR,
    STATUS_NO_FINDINGS,
    ModelError,
    OllamaClient,
    annotate_diff,
    build_messages,
    parse_response,
    prompt_sha256,
    review_code,
    run_review,
)


DIFF = """@@ -10,3 +10,5 @@
 def average(values):
-    return 0
+    total = sum(values)
+    return total / len(values)
 # end"""


def v2_finding(**overrides):
    finding = {
        "line": 12,
        "category": "correctness",
        "severity": "high",
        "finding": "Division by zero",
        "explanation": "len(values) can be 0.",
        "suggestion": "Guard empty input.",
        "confidence": 0.9,
    }
    finding.update(overrides)
    return finding


class FakeClient:
    """Stands in for OllamaClient: returns canned responses or raises ModelError."""

    model = "fake-model"

    def __init__(self, responses=(), context_length=32768, info_error=False):
        self.responses = list(responses)
        self.context_length = context_length
        self.info_error = info_error
        self.calls = []

    def resolve_options(self):
        # Reuse the real resolution logic against this fake's model_info.
        return OllamaClient.resolve_options(self)

    def model_info(self):
        if self.info_error:
            raise ModelError("unreachable")
        return {"model": self.model, "server_version": "test", "context_length": self.context_length}

    def chat(self, messages, options, response_format="json"):
        self.calls.append({"messages": messages, "options": options})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def fake(*responses, **kwargs):
    client = FakeClient(responses, **kwargs)
    client._options = None
    client._metadata = None
    return client


class PromptTests(unittest.TestCase):
    def test_annotation_numbers_new_file_lines_from_hunk_header(self):
        lines = annotate_diff(DIFF).splitlines()
        self.assertEqual(lines[0], "@@ -10,3 +10,5 @@")
        self.assertEqual(lines[1], "   10 |  def average(values):")
        self.assertEqual(lines[2], "      | -    return 0")
        self.assertEqual(lines[3], "   11 | +    total = sum(values)")
        self.assertEqual(lines[4], "   12 | +    return total / len(values)")
        self.assertEqual(lines[5], "   13 |  # end")

    def test_annotation_without_header_starts_at_one(self):
        self.assertEqual(annotate_diff("+a = 1\n+b = 2").splitlines(), ["    1 | +a = 1", "    2 | +b = 2"])

    def test_v1_prompt_is_the_original_text(self):
        messages = build_messages("Title", "a.py", DIFF, "v1")
        self.assertIs(messages[0]["content"], ai_reviewer.SYSTEM_PROMPT)
        self.assertIn("3. When a variable is used as a divisor", messages[0]["content"])
        self.assertIn("```diff\n" + DIFF + "\n```", messages[1]["content"])

    def test_v2_prompt_uses_annotated_diff_and_schema(self):
        messages = build_messages("Title", "a.py", DIFF, "v2")
        self.assertIn("   12 | +    return total / len(values)", messages[1]["content"])
        for word in ("line", "category", "severity", "null_safety"):
            self.assertIn(word, messages[0]["content"])
        self.assertNotIn("divisor", messages[0]["content"])

    def test_v3_extends_v2_with_false_positive_rules(self):
        v2 = build_messages("T", "a.py", DIFF, "v2")
        v3 = build_messages("T", "a.py", DIFF, "v3")
        self.assertIn("already prevents", v3[0]["content"])
        self.assertTrue(v3[0]["content"].startswith(v2[0]["content"].split("5. Never")[0]))
        self.assertEqual(v2[1], v3[1])
        self.assertNotEqual(prompt_sha256("v2"), prompt_sha256("v3"))

    def test_code_with_braces_is_not_treated_as_a_template(self):
        messages = build_messages("T", "a.ts", "+const x = {a: 1};", "v2")
        self.assertIn("{a: 1}", messages[1]["content"])

    def test_prompt_hashes_are_stable_and_distinct(self):
        self.assertEqual(prompt_sha256("v2"), prompt_sha256("v2"))
        self.assertNotEqual(prompt_sha256("v1"), prompt_sha256("v2"))
        with self.assertRaises(ValueError):
            build_messages("T", "a", DIFF, "v9")


class ParsingTests(unittest.TestCase):
    def test_valid_v2_findings(self):
        status, findings, error = parse_response(json.dumps({"findings": [v2_finding()]}), "v2")
        self.assertEqual((status, len(findings), error), (STATUS_FINDINGS, 1, None))

    def test_valid_empty_response(self):
        self.assertEqual(parse_response('{"findings": []}', "v2"), (STATUS_NO_FINDINGS, [], None))

    def test_null_line_is_allowed(self):
        status, _, _ = parse_response(json.dumps({"findings": [v2_finding(line=None)]}), "v2")
        self.assertEqual(status, STATUS_FINDINGS)

    def test_v1_schema(self):
        v1 = {"finding": "x", "explanation": "y", "suggestion": "z", "confidence": 0.5}
        self.assertEqual(parse_response(json.dumps({"findings": [v1]}), "v1")[0], STATUS_FINDINGS)
        self.assertEqual(parse_response(json.dumps({"findings": [v1]}), "v2")[0], STATUS_INVALID)

    def test_malformed_responses_are_invalid_not_empty(self):
        cases = {
            "empty string": "",
            "whitespace": "   ",
            "not json": "The code looks fine.",
            "json list": "[]",
            "extra top-level key": '{"findings": [], "summary": "ok"}',
            "findings not list": '{"findings": {}}',
            "finding not object": '{"findings": ["bug"]}',
            "missing field": json.dumps({"findings": [{k: v for k, v in v2_finding().items() if k != "severity"}]}),
            "extra field": json.dumps({"findings": [v2_finding(file="a.py")]}),
            "bad category": json.dumps({"findings": [v2_finding(category="style")]}),
            "bad severity": json.dumps({"findings": [v2_finding(severity="critical")]}),
            "line zero": json.dumps({"findings": [v2_finding(line=0)]}),
            "line string": json.dumps({"findings": [v2_finding(line="12")]}),
            "line bool": json.dumps({"findings": [v2_finding(line=True)]}),
            "confidence high": json.dumps({"findings": [v2_finding(confidence=1.5)]}),
            "confidence bool": json.dumps({"findings": [v2_finding(confidence=True)]}),
            "empty text": json.dumps({"findings": [v2_finding(finding="  ")]}),
        }

        for name, content in cases.items():
            status, findings, error = parse_response(content, "v2")
            self.assertEqual(status, STATUS_INVALID, name)
            self.assertEqual(findings, [], name)
            self.assertTrue(error, name)

    def test_one_invalid_finding_invalidates_the_response(self):
        content = json.dumps({"findings": [v2_finding(), v2_finding(category="style")]})
        self.assertEqual(parse_response(content, "v2")[:2], (STATUS_INVALID, []))


class RunReviewTests(unittest.TestCase):
    def test_result_records_metadata_and_raw_response(self):
        raw = json.dumps({"findings": [v2_finding()]})
        client = fake(raw)
        result = run_review("T", "a.py", DIFF, "v2", client)

        self.assertEqual(result.status, STATUS_FINDINGS)
        self.assertEqual(result.raw_response, raw)
        self.assertEqual(result.prompt_version, "v2")
        self.assertEqual(result.prompt_sha256, prompt_sha256("v2"))
        self.assertEqual(result.model, "fake-model")
        self.assertEqual(result.model_metadata["server_version"], "test")

    def test_num_ctx_is_capped_by_reported_context_length(self):
        result = run_review("T", "a.py", DIFF, "v2", fake('{"findings": []}', context_length=4096))
        self.assertEqual(result.options, {"temperature": 0, "num_ctx": 4096})

        result = run_review("T", "a.py", DIFF, "v2", fake('{"findings": []}', context_length=32768))
        self.assertEqual(result.options["num_ctx"], ai_reviewer.DESIRED_NUM_CTX)

    def test_num_ctx_not_set_when_context_length_unknown(self):
        for client in (fake('{"findings": []}', context_length=None), fake('{"findings": []}', info_error=True)):
            result = run_review("T", "a.py", DIFF, "v2", client)
            self.assertEqual(result.options, {"temperature": 0})
            self.assertIn("not set", result.model_metadata["num_ctx_source"])

    def test_model_error_is_reported_not_raised(self):
        result = run_review("T", "a.py", DIFF, "v2", fake(ModelError("connection refused")))
        self.assertEqual(result.status, STATUS_MODEL_ERROR)
        self.assertEqual(result.findings, [])
        self.assertIsNone(result.raw_response)
        self.assertIn("connection refused", result.error)

    def test_invalid_response_keeps_raw_text(self):
        result = run_review("T", "a.py", DIFF, "v2", fake("not json"))
        self.assertEqual(result.status, STATUS_INVALID)
        self.assertEqual(result.raw_response, "not json")
        self.assertFalse(result.is_valid)


class ReviewCodeCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.original = ai_reviewer._default_client

    def tearDown(self):
        ai_reviewer._default_client = self.original

    def test_returns_findings_dict(self):
        ai_reviewer._default_client = fake(json.dumps({"findings": [v2_finding()]}))
        self.assertEqual(review_code("T", "a.py", DIFF), {"findings": [v2_finding()]})

    def test_empty_result(self):
        ai_reviewer._default_client = fake('{"findings": []}')
        self.assertEqual(review_code("T", "a.py", DIFF, debug=False), {"findings": []})

    def test_raises_runtime_error_on_invalid_or_model_error(self):
        ai_reviewer._default_client = fake("not json")
        with self.assertRaisesRegex(RuntimeError, "invalid review response"):
            review_code("T", "a.py", DIFF)

        ai_reviewer._default_client = fake(ModelError("Could not connect to Ollama."))
        with self.assertRaisesRegex(RuntimeError, "Could not connect"):
            review_code("T", "a.py", DIFF)


if __name__ == "__main__":
    unittest.main()
