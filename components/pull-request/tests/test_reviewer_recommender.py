import unittest

import numpy as np

from reviewer_recommendation.baselines import (
    popularity_ranking,
    random_ranking,
    recent_popularity_ranking,
)
from reviewer_recommendation.recommender import (
    RecommenderConfig,
    ReviewerRecommender,
    ReviewHistory,
    candidate_signals,
    fit_title_vectorizer,
)
from tests.fixtures import pairs_frame


REPO = "org/repo"
QUERY = {
    "repo": REPO,
    "author": "alice",
    "title": "Fix login form validation",
    "created_at": "2024-02-01T00:00:00Z",
}


class RecommenderTests(unittest.TestCase):
    def setUp(self):
        pairs = pairs_frame([
            (REPO, 10, "bob", "2024-01-01T00:00:00Z", "alice", "Fix login button"),
            (REPO, 11, "carol", "2024-01-02T00:00:00Z", "zed", "Update docs"),
            (REPO, 12, "carol", "2024-01-03T00:00:00Z", "zed", "Docs typo"),
            (REPO, 14, "Alice", "2024-01-04T00:00:00Z", "bob", "Refactor parser"),
            (REPO, 15, "renovate[bot]", "2024-01-04T00:00:00Z", "zed", "Bump deps"),
            (REPO, 16, "frank", "2024-02-01T00:00:00Z", "zed", "Fix login form"),
            (REPO, 13, "dave", "2024-03-01T00:00:00Z", "alice", "Fix login form validation"),
            ("other/repo", 1, "grace", "2024-01-01T00:00:00Z", "alice", "Fix login form"),
        ])
        vectorizer = fit_title_vectorizer(pairs["pr_title"])
        self.history = ReviewHistory(pairs, vectorizer)
        self.recommender = ReviewerRecommender(self.history, RecommenderConfig())

    def candidates(self):
        return set(candidate_signals(self.history, **QUERY).index)

    def test_only_strictly_earlier_activity_is_used(self):
        # dave reviews after the PR is opened; frank at the exact same instant.
        self.assertNotIn("dave", self.candidates())
        self.assertNotIn("frank", self.candidates())

    def test_author_bots_and_other_repositories_are_excluded(self):
        self.assertEqual(self.candidates(), {"bob", "carol"})

    def test_signals_favour_author_affinity_and_title_similarity(self):
        ranked = self.recommender.rank(**QUERY)
        self.assertEqual(list(ranked.index), ["bob", "carol"])
        self.assertEqual(ranked.loc["carol", "activity"], 1.0)
        self.assertEqual(ranked.loc["bob", "author_affinity"], 1.0)
        self.assertEqual(ranked.loc["carol", "title_similarity"], 0.0)

    def test_recommendations_include_explanations(self):
        top = self.recommender.recommend(**QUERY, k=1)[0].to_dict()
        self.assertEqual(top["reviewer"], "bob")
        self.assertEqual(set(top["signals"]), {"activity", "author_affinity", "title_similarity"})
        self.assertTrue(any("by alice" in reason for reason in top["reasons"]))
        self.assertTrue(any("similar title" in reason for reason in top["reasons"]))

    def test_recommendations_are_deterministic(self):
        first = [r.to_dict() for r in self.recommender.recommend(**QUERY)]
        second = [r.to_dict() for r in self.recommender.recommend(**QUERY)]
        self.assertEqual(first, second)

    def test_unknown_repository_returns_no_candidates(self):
        self.assertEqual(self.recommender.recommend("new/repo", "alice", "x", "2024-02-01"), [])

    def test_naive_timestamps_are_treated_as_utc(self):
        naive = dict(QUERY, created_at="2024-02-01 00:00:00")
        self.assertEqual(
            [r.reviewer for r in self.recommender.recommend(**naive)],
            [r.reviewer for r in self.recommender.recommend(**QUERY)],
        )


class BaselineTests(unittest.TestCase):
    def setUp(self):
        pairs = pairs_frame([
            (REPO, 1, "old_regular", "2023-01-01T00:00:00Z", "x", "alpha"),
            (REPO, 2, "old_regular", "2023-01-02T00:00:00Z", "x", "beta"),
            (REPO, 3, "old_regular", "2023-01-03T00:00:00Z", "x", "gamma"),
            (REPO, 4, "newcomer", "2024-01-20T00:00:00Z", "x", "delta"),
            (REPO, 5, "middle", "2023-06-01T00:00:00Z", "x", "epsilon"),
            (REPO, 6, "middle", "2023-06-02T00:00:00Z", "x", "zeta"),
        ])
        history = ReviewHistory(pairs, fit_title_vectorizer(pairs["pr_title"]))
        self.signals = candidate_signals(history, REPO, "x2", "title", "2024-02-01T00:00:00Z")

    def test_popularity_uses_all_time_count(self):
        self.assertEqual(popularity_ranking(self.signals), ["old_regular", "middle", "newcomer"])

    def test_recent_popularity_prefers_recent_reviewers(self):
        self.assertEqual(recent_popularity_ranking(self.signals), ["newcomer", "old_regular", "middle"])

    def test_random_ranking_is_seeded_permutation(self):
        first = random_ranking(self.signals, np.random.default_rng(7))
        second = random_ranking(self.signals, np.random.default_rng(7))
        self.assertEqual(first, second)
        self.assertEqual(sorted(first), sorted(self.signals.index))


if __name__ == "__main__":
    unittest.main()
