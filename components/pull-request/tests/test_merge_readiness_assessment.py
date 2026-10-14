import unittest

import pandas as pd

from merge_readiness.assessment import (
    ATTENTION,
    BLOCKING,
    DISCLAIMER,
    LABEL_ATTENTION,
    LABEL_INSUFFICIENT,
    LABEL_READY,
    PASS,
    UNKNOWN,
    assess,
)
from merge_readiness.config import ReadinessThresholds
from merge_readiness.context import PRContext, PREvent


AS_OF = "2024-01-10T00:00:00Z"


def ts(value):
    return pd.Timestamp(value, tz="UTC")


def review(actor, day, state, actor_type="User"):
    return PREvent("review", actor, actor_type, ts(f"2024-01-{day:02d}"), state=state)


def thread(actor, day, replies=(), actor_type="User"):
    return PREvent("review_comment", actor, actor_type, ts(f"2024-01-{day:02d}"), reply_actors=tuple(replies))


def context(events, additions=40, deletions=10, external_checks=None, author="alice"):
    return PRContext(
        repo="org/repo",
        number=1,
        title="Add feature",
        author=author,
        author_type="User",
        created_at=ts("2024-01-01"),
        additions=additions,
        deletions=deletions,
        events=[PREvent("created", author, "User", ts("2024-01-01"))] + list(events),
        external_checks=external_checks,
    )


class ReadyPathTests(unittest.TestCase):
    def setUp(self):
        self.result = assess(context([
            thread("bob", 7, replies=["alice"]),
            review("bob", 8, "APPROVED"),
        ]), as_of=AS_OF)

    def test_clean_pr_is_ready_for_human_decision(self):
        self.assertEqual(self.result.label, LABEL_READY)
        for key in ("human_approval", "change_requests", "unanswered_threads",
                    "review_coverage", "recent_activity", "change_size"):
            self.assertEqual(self.result.item(key).status, PASS, key)

    def test_external_checks_are_reported_as_not_provided(self):
        item = self.result.item("external_checks")
        self.assertEqual(item.status, UNKNOWN)
        self.assertIn("ci", item.evidence)
        self.assertTrue(any("External checks" in m for m in self.result.missing_information))

    def test_output_is_decision_support_only(self):
        output = self.result.to_dict()
        self.assertEqual(output["disclaimer"], DISCLAIMER)
        self.assertNotIn("decision", output)
        self.assertEqual(set(output), {"repo", "number", "as_of", "label", "items",
                                       "missing_information", "thresholds", "disclaimer"})

    def test_known_data_gaps_are_always_disclosed(self):
        joined = " ".join(self.result.missing_information)
        self.assertIn("resolution status", joined)
        self.assertIn("Commit/push history", joined)


class ReviewStateTests(unittest.TestCase):
    def test_missing_approval_is_blocking(self):
        result = assess(context([thread("bob", 8, replies=["alice"])]), as_of=AS_OF)
        item = result.item("human_approval")
        self.assertEqual((item.status, item.severity), (ATTENTION, BLOCKING))
        self.assertEqual(result.label, LABEL_ATTENTION)

    def test_latest_state_per_reviewer_wins(self):
        result = assess(context([
            review("bob", 3, "CHANGES_REQUESTED"),
            review("bob", 5, "APPROVED"),
            review("carol", 4, "APPROVED"),
            review("carol", 6, "CHANGES_REQUESTED"),
        ]), as_of=AS_OF)
        self.assertIn("bob", result.item("human_approval").evidence)
        self.assertIn("carol", result.item("change_requests").evidence)
        self.assertEqual(result.item("change_requests").severity, BLOCKING)

    def test_commented_review_does_not_override_approval(self):
        result = assess(context([review("bob", 5, "APPROVED"), review("bob", 6, "COMMENTED")]), as_of=AS_OF)
        self.assertEqual(result.item("human_approval").status, PASS)

    def test_dismissed_review_is_withdrawn(self):
        result = assess(context([review("bob", 5, "CHANGES_REQUESTED"), review("bob", 6, "DISMISSED"),
                                 review("carol", 7, "APPROVED")]), as_of=AS_OF)
        self.assertEqual(result.item("change_requests").status, PASS)

    def test_bot_and_author_reviews_do_not_count(self):
        result = assess(context([
            review("renovate[bot]", 5, "APPROVED", actor_type="Bot"),
            review("matticbot", 5, "APPROVED"),
            review("Alice", 6, "APPROVED"),
        ]), as_of=AS_OF)
        self.assertEqual(result.item("human_approval").status, ATTENTION)
        self.assertEqual(result.item("review_coverage").status, ATTENTION)

    def test_events_at_or_after_assessment_time_are_ignored(self):
        result = assess(context([
            review("bob", 5, "APPROVED"),
            review("bob", 10, "CHANGES_REQUESTED"),   # exactly at as_of
            review("carol", 12, "CHANGES_REQUESTED"),  # after as_of
        ]), as_of=AS_OF)
        self.assertEqual(result.item("change_requests").status, PASS)
        self.assertEqual(result.label, LABEL_READY)


class AdvisoryItemTests(unittest.TestCase):
    def test_unanswered_threads_are_flagged_as_approximation(self):
        result = assess(context([thread("bob", 7), thread("bob", 7, replies=["alice"]),
                                 review("bob", 8, "APPROVED")]), as_of=AS_OF)
        item = result.item("unanswered_threads")
        self.assertEqual(item.status, ATTENTION)
        self.assertIn("1 of 2", item.evidence)
        self.assertIn("Approximation", item.basis)

    def test_stale_pr_needs_attention(self):
        result = assess(context([review("bob", 2, "APPROVED")]), as_of="2024-01-20T00:00:00Z")
        self.assertEqual(result.item("recent_activity").status, ATTENTION)

    def test_large_change_needs_attention_and_threshold_is_configurable(self):
        events = [review("bob", 8, "APPROVED")]
        self.assertEqual(assess(context(events, additions=450, deletions=100), as_of=AS_OF)
                         .item("change_size").status, ATTENTION)
        relaxed = ReadinessThresholds(large_change_lines=1000)
        self.assertEqual(assess(context(events, additions=450, deletions=100), as_of=AS_OF, thresholds=relaxed)
                         .item("change_size").status, PASS)

    def test_heuristic_thresholds_are_labelled(self):
        result = assess(context([review("bob", 8, "APPROVED")]), as_of=AS_OF)
        self.assertIn("Heuristic", result.item("change_size").basis)
        self.assertEqual(result.thresholds["stale_after_days"], 14.0)


class ExternalCheckAndLabelTests(unittest.TestCase):
    def test_failing_external_check_is_blocking(self):
        result = assess(context([review("bob", 8, "APPROVED")],
                                external_checks={"ci": "fail", "quality_gate": "pass", "merge_conflicts": "pass"}),
                        as_of=AS_OF)
        item = result.item("external_checks")
        self.assertEqual((item.status, item.severity), (ATTENTION, BLOCKING))
        self.assertEqual(result.label, LABEL_ATTENTION)

    def test_all_external_checks_passing(self):
        result = assess(context([review("bob", 8, "APPROVED")],
                                external_checks={"ci": "pass", "quality_gate": "pass", "merge_conflicts": "pass"}),
                        as_of=AS_OF)
        self.assertEqual(result.item("external_checks").status, PASS)

    def test_missing_required_information_gives_insufficient_label(self):
        result = assess(context([review("bob", 8, "APPROVED")], additions=None), as_of=AS_OF)
        self.assertEqual(result.item("change_size").status, UNKNOWN)
        self.assertEqual(result.label, LABEL_INSUFFICIENT)

    def test_assessment_is_deterministic(self):
        pr = context([thread("bob", 7), review("bob", 8, "APPROVED")])
        self.assertEqual(assess(pr, as_of=AS_OF).to_dict(), assess(pr, as_of=AS_OF).to_dict())


if __name__ == "__main__":
    unittest.main()
