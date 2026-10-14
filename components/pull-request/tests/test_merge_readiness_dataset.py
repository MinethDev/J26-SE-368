import unittest

from merge_readiness.assessment import LABEL_ATTENTION, LABEL_READY
from merge_readiness.context import contexts_from_raw, decision_outcome
from merge_readiness.descriptive import assess_at_decision, describe
from tests.fixtures import event, pull_request, raw_frame


REPO = "org/repo"


def merged_pr():
    return pull_request(REPO, 1, "alice", "2024-01-01T00:00:00Z", "Add feature", [
        event("created", "alice", "2024-01-01T00:00:00Z"),
        event("review_comment", "bob", "2024-01-02T00:00:00Z", comment_id=1,
              thread_replies=[{"reviewer": "alice", "reviewer_type": "User", "body": "done", "comment_id": 2}]),
        event("review", "bob", "2024-01-03T00:00:00Z", state="APPROVED", review_id=10),
        event("merged", "bob", "2024-01-04T00:00:00Z"),
        event("closed", "bob", "2024-01-04T00:00:05Z"),
        # After the decision: must not affect the assessment.
        event("review", "carol", "2024-01-05T00:00:00Z", state="CHANGES_REQUESTED", review_id=11),
    ])


def closed_pr():
    return pull_request(REPO, 2, "dependabot[bot]", "2024-01-01T00:00:00Z", "Bump lib", [
        event("created", "dependabot[bot]", "2024-01-01T00:00:00Z", reviewer_type="Bot"),
        event("closed", "dave", "2024-02-01T00:00:00Z"),
    ], author_type="Bot")


def open_pr():
    return pull_request(REPO, 3, "erin", "2024-01-01T00:00:00Z", "WIP", [
        event("created", "erin", "2024-01-01T00:00:00Z"),
    ])


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.contexts, self.stats = contexts_from_raw(raw_frame([merged_pr(), merged_pr(), closed_pr(), open_pr()]))
        self.by_number = {c.number: c for c in self.contexts}

    def test_duplicates_removed_and_events_attached(self):
        self.assertEqual(self.stats["unique_prs"], 3)
        self.assertEqual(len(self.by_number[1].events), 6)
        thread = next(e for e in self.by_number[1].events if e.event_type == "review_comment")
        self.assertEqual(thread.reply_actors, ("alice",))

    def test_decision_time_uses_merge_event_for_merged_prs(self):
        outcome = decision_outcome(self.by_number[1])
        self.assertEqual(outcome.outcome, "merged")
        self.assertEqual(str(outcome.decision_time), "2024-01-04 00:00:00+00:00")

    def test_closed_and_undecided_prs(self):
        self.assertEqual(decision_outcome(self.by_number[2]).outcome, "closed")
        self.assertIsNone(decision_outcome(self.by_number[3]))


class DescriptiveTests(unittest.TestCase):
    def setUp(self):
        contexts, _ = contexts_from_raw(raw_frame([merged_pr(), closed_pr(), open_pr()]))
        self.frame = assess_at_decision(contexts)

    def test_only_decided_prs_are_assessed_before_their_decision(self):
        self.assertEqual(sorted(self.frame["pr_number"]), [1, 2])
        merged = self.frame.set_index("pr_number").loc[1]
        self.assertEqual(merged["label"], LABEL_READY)
        self.assertEqual(merged["change_requests"], 0)

    def test_bot_authored_prs_are_grouped_separately(self):
        groups = dict(zip(self.frame["pr_number"], self.frame["author_group"]))
        self.assertEqual(groups, {1: "human", 2: "bot"})
        closed = self.frame.set_index("pr_number").loc[2]
        self.assertEqual(closed["label"], LABEL_ATTENTION)

    def test_summary_reports_groups(self):
        summary = describe(self.frame)
        self.assertEqual(summary["all"]["n"], 2)
        self.assertEqual(summary["author_group=bot"]["n"], 1)
        self.assertEqual(summary["outcome=merged,author_group=human"]["labels"][LABEL_READY]["n"], 1)


if __name__ == "__main__":
    unittest.main()
