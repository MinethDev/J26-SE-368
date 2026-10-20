import unittest

import numpy as np
import pandas as pd

from risk_prediction.dataset import FEATURES
from risk_prediction.explain import contributions, explain_row
from risk_prediction.model import logistic_regression, xgboost


def data(n=200, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.random((n, len(FEATURES))), columns=FEATURES)
    df.loc[: n // 4, "team_prev_delivered_mean"] = np.nan  # a team's first sprints have no history
    df["missed"] = (df["delivered_so_far"] < 0.5).astype(int)
    return df


class ExplainTest(unittest.TestCase):
    def test_logistic_contributions_add_up_to_the_prediction(self):
        df = data()
        model = logistic_regression().fit(df[FEATURES], df["missed"])
        total = contributions(model, df).sum(axis=1) + model.named_steps["logisticregression"].intercept_[0]
        np.testing.assert_allclose(total, model.decision_function(df[FEATURES]), atol=1e-8)

    def test_xgboost_contributions_are_per_feature(self):
        df = data()
        model = xgboost(max_depth=2, n_estimators=20).fit(df[FEATURES], df["missed"])
        self.assertEqual(list(contributions(model, df).columns), FEATURES)

    def test_explain_row_puts_the_real_driver_first(self):
        df = data()
        model = logistic_regression().fit(df[FEATURES], df["missed"])
        top = explain_row(model, df.iloc[0])
        self.assertEqual(top[0]["feature"], "delivered_so_far")
        self.assertEqual(len(top), 5)


if __name__ == "__main__":
    unittest.main()
