import unittest

import pandas as pd

from reviewer_recommendation.metrics import (
    hit_at_k,
    recall_at_k,
    reciprocal_rank,
    score_ranking,
    summarize,
)
from reviewer_recommendation.split import assign_chronological_splits


def make_prs(repo, count, start="2024-01-01"):
    created = pd.date_range(start, periods=count, freq="D", tz="UTC")
    return pd.DataFrame({
        "repo_full_name": repo,
        "pr_number": range(1, count + 1),
        "created_at": created,
    })


class SplitTests(unittest.TestCase):
    def setUp(self):
        # Shuffle so the split cannot rely on input order.
        prs = pd.concat([make_prs("a/large", 10), make_prs("b/small", 4)])
        self.split = assign_chronological_splits(prs.sample(frac=1, random_state=0))

    def test_split_sizes_per_repository(self):
        counts = self.split.groupby(["repo_full_name", "split"]).size().to_dict()
        self.assertEqual(counts[("a/large", "train")], 7)
        self.assertEqual(counts[("a/large", "validation")], 1)
        self.assertEqual(counts[("a/large", "test")], 2)
        self.assertEqual(counts[("b/small", "train")], 2)
        self.assertEqual(counts[("b/small", "validation")], 1)
        self.assertEqual(counts[("b/small", "test")], 1)

    def test_splits_are_chronological_within_each_repository(self):
        for _, block in self.split.groupby("repo_full_name"):
            dates = {name: block[block["split"] == name]["created_at"] for name in ("train", "validation", "test")}
            self.assertLess(dates["train"].max(), dates["validation"].min())
            self.assertLess(dates["validation"].max(), dates["test"].min())

    def test_each_pr_has_exactly_one_split(self):
        keys = self.split[["repo_full_name", "pr_number"]]
        self.assertFalse(keys.duplicated().any())
        self.assertEqual(len(self.split), 14)

    def test_invalid_ratios_are_rejected(self):
        prs = make_prs("a/large", 5)
        with self.assertRaises(ValueError):
            assign_chronological_splits(prs, train_ratio=0.9, validation_ratio=0.1)
        with self.assertRaises(ValueError):
            assign_chronological_splits(prs, train_ratio=0.0)


class MetricTests(unittest.TestCase):
    def test_ranking_metrics_hand_calculated(self):
        ranked = ["a", "b", "c", "d"]
        truth = ["c", "x"]

        self.assertEqual(hit_at_k(ranked, truth, 1), 0.0)
        self.assertEqual(hit_at_k(ranked, truth, 3), 1.0)
        self.assertEqual(recall_at_k(ranked, truth, 3), 0.5)
        self.assertAlmostEqual(reciprocal_rank(ranked, truth), 1 / 3)

    def test_empty_ranking_scores_zero(self):
        scores = score_ranking([], ["a"], ks=(1, 3))
        self.assertEqual(scores, {"mrr": 0.0, "hit@1": 0.0, "recall@1": 0.0, "hit@3": 0.0, "recall@3": 0.0})

    def test_macro_average_weights_repositories_equally(self):
        per_query = pd.DataFrame({
            "repo_full_name": ["big", "big", "big", "small"],
            "mrr": [1.0, 1.0, 1.0, 0.0],
        })
        summary = summarize(per_query, ["mrr"])

        self.assertEqual(summary["n"], 4)
        self.assertEqual(summary["overall"]["mrr"], 0.75)
        self.assertEqual(summary["macro"]["mrr"], 0.5)
        self.assertEqual(summary["per_repo"]["small"], {"n": 1, "mrr": 0.0})


if __name__ == "__main__":
    unittest.main()
