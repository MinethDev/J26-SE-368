import unittest

import pandas as pd

from productivity.velocity import overcommitment, sprint_velocity, team_trend


def final_snapshot(sprint_id, committed_points, delivered_points, done_points):
    return {"sprint_id": sprint_id, "project_id": 1, "day": 10, "committed_issues": 5,
            "committed_points": committed_points, "committed_done_points": delivered_points,
            "committed_done_issues": 4, "done_points": done_points, "done_issues": 6,
            "added_points": 2.0, "added_issues": 1}


class VelocityTest(unittest.TestCase):
    def setUp(self):
        starts = pd.date_range("2024-01-01", periods=4, freq="14D")
        self.sprints = pd.DataFrame({"sprint_id": [1, 2, 3, 4], "start_date": starts,
                                     "end_date": starts + pd.Timedelta(days=13), "planned_days": 13.0})
        snaps = [final_snapshot(1, 20, 10, 12), final_snapshot(2, 20, 15, 16),
                 final_snapshot(3, 20, 20, 20), final_snapshot(4, 40, 0, 0)]
        self.velocity = sprint_velocity(pd.DataFrame(snaps), self.sprints)

    def test_per_sprint_numbers(self):
        v = self.velocity.loc[1]
        self.assertEqual((v["unit"], v["committed"], v["delivered"], v["completed"]), ("points", 20, 10, 12))
        self.assertEqual(v["say_do"], 0.5)
        self.assertEqual(v["carry_over_issues"], 1)

    def test_trend_only_uses_sprints_that_ended_before(self):
        start_4 = self.sprints.loc[3, "start_date"]
        trend = team_trend(self.velocity, 1, start_4)
        self.assertEqual(trend["sprints_seen"], 3)
        self.assertAlmostEqual(trend["velocity"], 16.0)
        self.assertAlmostEqual(trend["velocity_trend"], 4.0)
        self.assertTrue(overcommitment(40, trend["velocity"])["overcommitted"])
        self.assertEqual(team_trend(self.velocity, 1, self.sprints.loc[0, "start_date"])["sprints_seen"], 0)
