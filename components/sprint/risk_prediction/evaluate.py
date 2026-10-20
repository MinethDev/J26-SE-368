"""Metrics reported for every model, overall and per checkpoint."""
import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss, f1_score, precision_score,
                             recall_score, roc_auc_score)

from sprint_health.config import CHECKPOINTS


def metrics(rows: pd.DataFrame, scores, predicted=None) -> dict:
    """AUC-type metrics from scores; accuracy/precision/recall/F1 from yes/no predictions when given.

    "Positive" = the sprint misses its commitment, so recall = share of missed sprints that were flagged.
    """
    out = {"auc": roc_auc_score(rows["missed"], scores)}
    for cp in CHECKPOINTS:
        mask = (rows["checkpoint"] == cp).to_numpy()
        out[f"auc@{cp:.0%}"] = roc_auc_score(rows.loc[mask, "missed"], scores[mask])
    out["avg_precision"] = average_precision_score(rows["missed"], scores)
    if scores.min() >= 0 and scores.max() <= 1:
        out["brier"] = brier_score_loss(rows["missed"], scores)
    if predicted is not None:
        y = rows["missed"]
        out["accuracy"] = accuracy_score(y, predicted)
        out["precision"] = precision_score(y, predicted, zero_division=0)
        out["recall"] = recall_score(y, predicted, zero_division=0)
        out["f1"] = f1_score(y, predicted, zero_division=0)
    return out


def bootstrap_auc(rows: pd.DataFrame, scores, n: int = 1000, seed: int = 42) -> tuple[float, float]:
    """95% confidence interval for AUC, resampling whole sprints (all checkpoints of a sprint together)."""
    rng = np.random.default_rng(seed)
    rows = rows.reset_index(drop=True).assign(_score=scores)
    by_sprint = {sid: idx.to_numpy() for sid, idx in rows.groupby("sprint_id").groups.items()}
    sprint_ids = np.array(list(by_sprint))
    aucs = []
    for _ in range(n):
        idx = np.concatenate([by_sprint[s] for s in rng.choice(sprint_ids, len(sprint_ids))])
        sample = rows.iloc[idx]
        if sample["missed"].nunique() == 2:
            aucs.append(roc_auc_score(sample["missed"], sample["_score"]))
    low, high = np.percentile(aucs, [2.5, 97.5])
    return float(low), float(high)


def table(results: dict[str, dict]) -> str:
    return pd.DataFrame(results).T.round(3).to_string()
