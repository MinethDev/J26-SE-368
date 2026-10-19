"""Per-sprint explanations: how much each feature pushed the risk up or down (in log-odds).

Logistic regression: contribution = coefficient x standardised value. For a linear model this is
exactly its SHAP value (with the training mean as the baseline), so no extra package is needed.
XGBoost: uses XGBoost's built-in TreeSHAP (pred_contribs), also exact SHAP values.
"""
import numpy as np
import pandas as pd
import xgboost as xgb

from risk_prediction.dataset import FEATURES

INDICATOR_PREFIX = "missingindicator_"


def _logistic_contributions(pipeline, rows: pd.DataFrame) -> pd.DataFrame:
    imputer, scaler, lr = pipeline.named_steps.values()
    z = scaler.transform(imputer.transform(rows[FEATURES]))
    contrib = pd.DataFrame(z * lr.coef_[0], columns=imputer.get_feature_names_out(FEATURES), index=rows.index)
    # Fold "this value was missing" columns into the feature they belong to.
    for col in [c for c in contrib.columns if c.startswith(INDICATOR_PREFIX)]:
        contrib[col.removeprefix(INDICATOR_PREFIX)] += contrib.pop(col)
    return contrib[FEATURES]


def _xgboost_contributions(model, rows: pd.DataFrame) -> pd.DataFrame:
    values = model.get_booster().predict(xgb.DMatrix(rows[FEATURES]), pred_contribs=True)
    return pd.DataFrame(values[:, :-1], columns=FEATURES, index=rows.index)  # last column is the bias


def contributions(model, rows: pd.DataFrame) -> pd.DataFrame:
    if hasattr(model, "named_steps"):
        return _logistic_contributions(model, rows)
    return _xgboost_contributions(model, rows)


def explain_row(model, row: pd.Series, top: int = 5) -> list[dict]:
    """Top features for one row: [{feature, value, impact}], biggest effect first."""
    contrib = contributions(model, row.to_frame().T.astype({f: float for f in FEATURES})).iloc[0]
    order = contrib.abs().sort_values(ascending=False).index[:top]
    return [{"feature": f, "value": None if pd.isna(row[f]) else float(row[f]), "impact": round(float(contrib[f]), 4)}
            for f in order]


def global_importance(model, rows: pd.DataFrame) -> pd.Series:
    """Mean absolute contribution per feature: which features matter most overall."""
    return contributions(model, rows).abs().mean().sort_values(ascending=False)
