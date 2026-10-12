"""
Auxiliary baseline: predict merged vs. closed from checklist signals.

This is NOT a measure of merge readiness. A PR can be merged without being
ready, or closed for reasons unrelated to readiness (superseded, duplicate,
abandoned). It only shows how much outcome information the signals carry.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from merge_readiness.assessment import LABEL_READY
from merge_readiness.config import RANDOM_SEED
from reviewer_recommendation.split import assign_chronological_splits


FEATURES = [
    "approvals",
    "change_requests",
    "reviewers",
    "review_threads",
    "unanswered_threads",
    "log_days_since_activity",
    "log_changed_lines",
    "author_is_bot",
]

# Inactivity right before the decision mostly reflects how PRs end
# (abandoned PRs are closed after long idle periods), so the primary model
# excludes it; the all-signals model is kept only as a diagnostic.
PRIMARY_VARIANT = "excluding_recent_activity"
MODEL_VARIANTS = {
    PRIMARY_VARIANT: [f for f in FEATURES if f != "log_days_since_activity"],
    "all_signals_diagnostic": FEATURES,
}

C_GRID = (0.01, 0.1, 1.0, 10.0)
POSITIVE_CLASS = "closed"
SUBSETS = ("all", "human", "bot")

CAVEATS = [
    "Merged vs. closed is an auxiliary proxy, not merge readiness.",
    "Signals are taken immediately before the final merge/close event; the decision event and later events are excluded.",
    "Thread replies have no timestamps, so replies after the decision may be counted.",
    "Change size is the final additions + deletions.",
    "Approval features partly reflect repository merge policies (e.g. branch protection requiring approval "
    "before merge), so their predictive weight does not show that approvals indicate readiness.",
    "These metrics evaluate outcome prediction only; they are not readiness accuracy. The checklist is "
    "evaluated separately (unit tests and descriptive statistics).",
    "Days since activity at decision time mostly reflects how PRs end (abandoned PRs are closed after long "
    "inactivity); it is excluded from the primary model and used only in a labelled diagnostic model.",
]


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add model features and the binary target (1 = closed without merge)."""

    data = frame.copy()
    data["log_changed_lines"] = np.log1p(data["changed_lines"].astype(float))
    data["log_days_since_activity"] = np.log1p(data["days_since_activity"].astype(float))
    data["author_is_bot"] = (data["author_group"] == "bot").astype(int)
    data["target"] = (data["outcome"] == POSITIVE_CLASS).astype(int)

    return assign_chronological_splits(data)


class FittedModel:
    """Logistic regression with its feature list and training-set fill values."""

    def __init__(self, features, c_value, pipeline, fill):
        self.features = list(features)
        self.c_value = c_value
        self.pipeline = pipeline
        self.fill = fill

    def matrix(self, data: pd.DataFrame) -> np.ndarray:
        return data[self.features].astype(float).fillna(self.fill).to_numpy()

    def predict_closed(self, data: pd.DataFrame) -> np.ndarray:
        return self.pipeline.predict_proba(self.matrix(data))[:, 1]


def fit_logistic(train: pd.DataFrame, c_value: float, features=None) -> FittedModel:
    features = list(features or MODEL_VARIANTS[PRIMARY_VARIANT])
    fill = train[features].median().to_dict()
    pipeline = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=c_value, class_weight="balanced", max_iter=1000, random_state=RANDOM_SEED),
    )
    model = FittedModel(features, c_value, pipeline, fill)
    pipeline.fit(model.matrix(train), train["target"].to_numpy())

    return model


def classification_metrics(y_true, scores, predictions) -> dict:
    y_true = np.asarray(y_true)
    result = {
        "n": int(len(y_true)),
        "closed_share": round(float(y_true.mean()), 4) if len(y_true) else None,
        "roc_auc": None,
        "pr_auc_closed": None,
        "balanced_accuracy": None,
    }

    if len(y_true) and len(np.unique(y_true)) == 2:
        result["roc_auc"] = round(float(roc_auc_score(y_true, scores)), 4)
        result["pr_auc_closed"] = round(float(average_precision_score(y_true, scores)), 4)
        result["balanced_accuracy"] = round(float(balanced_accuracy_score(y_true, predictions)), 4)

    return result


def subset_masks(data: pd.DataFrame) -> dict:
    return {
        "all": np.ones(len(data), dtype=bool),
        "human": (data["author_group"] == "human").to_numpy(),
        "bot": (data["author_group"] == "bot").to_numpy(),
    }


def predictor_scores(data: pd.DataFrame, train: pd.DataFrame, models=None) -> dict:
    """Closed-class scores and hard predictions for each predictor."""

    prevalence = float(train["target"].mean())
    not_ready = (data["label"] != LABEL_READY).astype(int).to_numpy()

    predictors = {
        # Constant score: ROC-AUC 0.5, PR-AUC equals the closed share.
        "majority_class": (np.full(len(data), prevalence), np.zeros(len(data), dtype=int)),
        # Checklist label as a rule: anything other than "ready" predicts closed.
        "checklist_label_rule": (not_ready.astype(float), not_ready),
    }

    for variant, model in (models or {}).items():
        probabilities = model.predict_closed(data)
        predictors[f"logistic_regression[{variant}]"] = (probabilities, (probabilities >= 0.5).astype(int))

    return predictors


def evaluate_split(data: pd.DataFrame, train: pd.DataFrame, models=None) -> dict:
    masks = subset_masks(data)
    y_true = data["target"].to_numpy()

    return {
        name: {
            subset: classification_metrics(y_true[mask], scores[mask], predictions[mask])
            for subset, mask in masks.items()
        }
        for name, (scores, predictions) in predictor_scores(data, train, models).items()
    }


def select_c(train: pd.DataFrame, validation: pd.DataFrame, features=None) -> tuple:
    """Choose the regularization strength by validation ROC-AUC (all PRs)."""

    results = []

    for c_value in C_GRID:
        scores = fit_logistic(train, c_value, features).predict_closed(validation)
        results.append({"C": c_value, "roc_auc": round(float(roc_auc_score(validation["target"], scores)), 4)})

    # First best value in grid order, so selection is deterministic.
    best = max(results, key=lambda row: row["roc_auc"])

    return best["C"], results


def coefficients(model: FittedModel) -> dict:
    """Standardized coefficients: positive values push towards 'closed'."""

    weights = model.pipeline.named_steps["logisticregression"].coef_[0]

    return {name: round(float(weight), 4) for name, weight in zip(model.features, weights)}
