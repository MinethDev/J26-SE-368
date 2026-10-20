import unittest

import pandas as pd

from risk_prediction.dataset import _team_history
from risk_prediction.split import assign_splits, check_no_leakage

T = pd.Timestamp


class RiskDatasetTest(unittest.TestCase):
    def test_team_history_uses_only_sprints_that_already_ended(self):
        sprints = pd.DataFrame({
            "project_id": [1, 1, 1, 2],
            "end_date": [T("2020-01-10"), T("2020-01-24"), T("2020-02-07"), T("2020-01-10")],
        }, index=[10, 11, 12, 20])
        outcomes = pd.DataFrame({"delivered": [0.9, 0.5, 0.1, 0.0], "missed": [0, 1, 1, 1]}, index=[10, 11, 12, 20])
        # Sprint 12, checked on Jan 30: only sprints 10 and 11 had ended; sprint 20 is another project.
        h = _team_history(sprints, outcomes, 12, T("2020-01-30"))
        self.assertEqual(h["team_prev_sprints"], 2)
        self.assertAlmostEqual(h["team_prev_delivered_mean"], 0.7)
        self.assertEqual(h["team_prev_missed_rate"], 0.5)

    def test_split_is_chronological_per_project_and_keeps_checkpoints_together(self):
        rows = []
        for sid in range(20):
            for cp in (0.25, 0.5):
                rows.append({"sprint_id": sid, "project_id": 1, "checkpoint": cp,
                             "start_date": T("2020-01-01") + pd.Timedelta(days=14 * sid)})
        data = pd.DataFrame(rows)
        data = data.join(assign_splits(data), on="sprint_id")
        check_no_leakage(data)
        self.assertEqual(data.groupby("sprint_id")["split"].nunique().max(), 1)
        counts = data.drop_duplicates("sprint_id")["split"].value_counts()
        self.assertEqual((counts["train"], counts["validation"], counts["test"]), (14, 3, 3))


if __name__ == "__main__":
    unittest.main()
