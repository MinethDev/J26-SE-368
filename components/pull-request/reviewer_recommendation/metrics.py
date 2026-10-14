"""Ranking metrics for reviewer recommendation."""

import pandas as pd


DEFAULT_KS = (1, 3, 5)


def hit_at_k(ranked, truth, k) -> float:
    """1.0 if any true reviewer appears in the top k, else 0.0."""

    return float(bool(set(ranked[:k]) & set(truth)))


def recall_at_k(ranked, truth, k) -> float:
    """Share of true reviewers that appear in the top k."""

    truth = set(truth)

    if not truth:
        return 0.0

    return len(set(ranked[:k]) & truth) / len(truth)


def reciprocal_rank(ranked, truth) -> float:
    """1 / rank of the first true reviewer, or 0.0 if none is ranked."""

    truth = set(truth)

    for position, reviewer in enumerate(ranked, start=1):
        if reviewer in truth:
            return 1.0 / position

    return 0.0


def score_ranking(ranked, truth, ks=DEFAULT_KS) -> dict:
    ranked = list(ranked)
    scores = {"mrr": reciprocal_rank(ranked, truth)}

    for k in ks:
        scores[f"hit@{k}"] = hit_at_k(ranked, truth, k)
        scores[f"recall@{k}"] = recall_at_k(ranked, truth, k)

    return scores


def summarize(per_query: pd.DataFrame, metric_columns) -> dict:
    """
    Overall (micro) means, per-repository means, and the macro mean across
    repositories, which stops one large repository dominating the result.
    """

    metric_columns = list(metric_columns)

    if per_query.empty:
        return {"n": 0, "overall": {}, "macro": {}, "per_repo": {}}

    per_repo = per_query.groupby("repo_full_name")[metric_columns].mean()
    counts = per_query.groupby("repo_full_name").size()

    return {
        "n": int(len(per_query)),
        "overall": _rounded(per_query[metric_columns].mean()),
        "macro": _rounded(per_repo.mean()),
        "per_repo": {
            repo: {"n": int(counts[repo]), **_rounded(row)}
            for repo, row in per_repo.iterrows()
        },
    }


def _rounded(series) -> dict:
    return {name: round(float(value), 4) for name, value in series.items()}
