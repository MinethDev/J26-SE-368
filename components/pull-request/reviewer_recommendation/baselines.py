"""
Simple baselines. All rank the same as-of candidate pool as the recommender,
so differences come from the ranking, not from candidate selection.
"""

import numpy as np
import pandas as pd


def popularity_ranking(signals: pd.DataFrame) -> list:
    """Most PRs reviewed in the repository before the PR was opened."""

    # candidate_signals already returns rows in this order.
    return list(signals.index)


def recent_popularity_ranking(signals: pd.DataFrame) -> list:
    """Most PRs reviewed in the recent window; all-time count breaks ties."""

    order = np.argsort(
        -signals["recent_review_count"].to_numpy(dtype=float), kind="stable"
    )

    return list(signals.index[order])


def random_ranking(signals: pd.DataFrame, rng: np.random.Generator) -> list:
    """Uniformly random order of the candidate pool."""

    return list(rng.permutation(signals.index.to_numpy()))
