"""Models compared for sprint risk. All return P(missed) for each row."""
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from risk_prediction.config import RANDOM_SEED
from risk_prediction.dataset import FEATURES


def logistic_regression():
    # Imputer: team-history features are missing for a team's first sprints.
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                         LogisticRegression(max_iter=1000, random_state=RANDOM_SEED))


def xgboost(**params):
    # XGBoost handles missing values natively.
    return XGBClassifier(random_state=RANDOM_SEED, eval_metric="logloss", n_jobs=1, **params)


def fit_predict(model, train, rows) -> np.ndarray:
    model.fit(train[FEATURES], train["missed"])
    return model.predict_proba(rows[FEATURES])[:, 1]
