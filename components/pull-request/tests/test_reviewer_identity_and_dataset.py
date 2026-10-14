import importlib
import sys
import unittest

from reviewer_recommendation.dataset import build_reviewer_dataset
from reviewer_recommendation.identity import is_bot, normalize_login, same_login
from tests.fixtures import event, pull_request, raw_frame


class ImportTests(unittest.TestCase):
    def test_modules_import_without_modifying_sys_path(self):
        before = list(sys.path)

        for name in (
            "preprocessing.cleaner",
            "preprocessing.extractor",
            "reviewer_recommendation.config",
            "reviewer_recommendation.identity",
            "reviewer_recommendation.dataset",
            "reviewer_recommendation.split",
            "reviewer_recommendation.recommender",
            "reviewer_recommendation.baselines",
            "reviewer_recommendation.metrics",
            "reviewer_recommendation.evaluate",
        ):
            importlib.import_module(name)

        self.assertEqual(sys.path, before)


class IdentityTests(unittest.TestCase):
    def test_bot_detection(self):
        self.assertTrue(is_bot("codecov[bot]"))
        self.assertTrue(is_bot("someone", "Bot"))
        self.assertTrue(is_bot("matticbot", "User"))
        self.assertTrue(is_bot("AzCliBot", "User"))
        self.assertFalse(is_bot("PixelRobots", "User"))
        self.assertFalse(is_bot("alice", "User"))
        self.assertFalse(is_bot(None, "Unknown"))

    def test_missing_logins_normalize_to_none(self):
        for value in (None, "", "  ", "nan", "None"):
            self.assertIsNone(normalize_login(value))
        self.assertEqual(normalize_login(" alice "), "alice")

    def test_same_login_is_case_insensitive(self):
        self.assertTrue(same_login("Alice", "alice"))
        self.assertFalse(same_login("alice", "bob"))
        self.assertFalse(same_login(None, None))


class DatasetTests(unittest.TestCase):
    def setUp(self):
        repo = "org/repo"
        pr1 = pull_request(repo, 1, "alice", "2024-01-01T00:00:00Z", "Fix login", [
            event("created", "alice", "2024-01-01T00:00:00Z"),
            event("review", "bob", "2024-01-02T00:00:00Z", state="APPROVED", review_id=11),
            event("review_comment", "bob", "2024-01-02T01:00:00Z", comment_id=21),
            event("review_comment", "alice", "2024-01-02T02:00:00Z", comment_id=22),
            event("review", "codecov[bot]", "2024-01-02T03:00:00Z", reviewer_type="Bot", review_id=12),
            event("review", "matticbot", "2024-01-02T04:00:00Z", review_id=13),
            event("review", None, "2024-01-02T05:00:00Z", reviewer_type="Unknown", review_id=14),
            event("comment", "carol", "2024-01-02T06:00:00Z"),
        ])
        pr2 = pull_request(repo, 2, "bob", "2024-01-05T00:00:00Z", "Add docs", [
            event("review", "dave", "2024-01-06T00:00:00Z", state="APPROVED", review_id=15),
        ])
        pr3 = pull_request(repo, 3, "erin", "2024-01-06T00:00:00Z", "Bump deps", [
            event("review", "renovate[bot]", "2024-01-07T00:00:00Z", reviewer_type="Bot", review_id=16),
        ])

        # pr1 appears twice, as in the real shard.
        self.dataset = build_reviewer_dataset(raw_frame([pr1, pr1, pr2, pr3]))

    def test_duplicate_pr_rows_are_removed(self):
        self.assertEqual(self.dataset.stats["raw_pr_rows"], 4)
        self.assertEqual(self.dataset.stats["unique_prs"], 3)

    def test_pairs_exclude_bots_authors_missing_logins_and_comments(self):
        pairs = set(zip(self.dataset.pairs["pr_number"], self.dataset.pairs["reviewer"]))
        self.assertEqual(pairs, {(1, "bob"), (2, "dave")})

    def test_pair_timestamp_is_first_review(self):
        bob = self.dataset.pairs[self.dataset.pairs["reviewer"] == "bob"].iloc[0]
        self.assertEqual(str(bob["reviewed_at"]), "2024-01-02 00:00:00+00:00")

    def test_ground_truth_and_ineligible_prs(self):
        truth = dict(zip(
            self.dataset.evaluation_prs["pr_number"],
            self.dataset.evaluation_prs["true_reviewers"],
        ))
        self.assertEqual(truth, {1: ["bob"], 2: ["dave"]})
        self.assertEqual(self.dataset.stats["prs_without_eligible_reviewer"], 1)


if __name__ == "__main__":
    unittest.main()
