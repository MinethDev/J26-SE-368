"""Metrics reported for every model, overall and per checkpoint."""
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from sprint_health.config import CHECKPOINTS


def metrics(rows: pd.DataFrame, scores) -> dict:
    out = {"auc": roc_auc_score(rows["missed"], scores)}
    for cp in CHECKPOINTS:
        mask = (rows["checkpoint"] == cp).to_numpy()
        out[f"auc@{cp:.0%}"] = roc_auc_score(rows.loc[mask, "missed"], scores[mask])
    out["avg_precision"] = average_precision_score(rows["missed"], scores)
    if scores.min() >= 0 and scores.max() <= 1:
        out["brier"] = brier_score_loss(rows["missed"], scores)
    return out


def table(results: dict[str, dict]) -> str:
    return pd.DataFrame(results).T.round(3).to_string()
