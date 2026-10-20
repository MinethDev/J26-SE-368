import unittest

from productivity.workload import gini, team_workload


def issue(who, points, status="To Do"):
    return {"assignee": who, "story_points": points, "status_category": status}


class WorkloadTest(unittest.TestCase):
    def test_gini_even_and_concentrated(self):
        self.assertEqual(gini([5, 5, 5]), 0.0)
        self.assertGreater(gini([0, 0, 12]), 0.6)

    def test_even_team_is_balanced(self):
        w = team_workload([issue("Ann", 5), issue("Ben", 5), issue("Cal", 5)])
        self.assertFalse(w["imbalanced"])
        self.assertEqual(w["overloaded"], [])

    def test_one_person_holding_most_open_work_is_overloaded(self):
        w = team_workload([issue("Ann", 13), issue("Ann", 8), issue("Ben", 3), issue("Cal", 2),
                           issue("Cal", 5, "Done")])
        self.assertEqual(w["overloaded"], ["Ann"])
        self.assertTrue(w["imbalanced"])
        self.assertAlmostEqual(w["people"]["Ann"]["share_of_open"], 21 / 26, places=3)

    def test_done_work_and_unassigned_are_counted_separately(self):
        w = team_workload([issue("Ann", 3, "Done"), issue(None, 5), issue("Ben", 2)])
        self.assertEqual(w["free"], ["Ann"])
        self.assertEqual((w["unassigned_open_issues"], w["unassigned_open_points"]), (1, 5.0))
        self.assertEqual(w["open_total"], 2.0)

    def test_uses_issue_counts_without_points_and_flags_wip(self):
        w = team_workload([issue("Ann", None, "In Progress") for _ in range(4)] + [issue("Ben", None)])
        self.assertEqual(w["unit"], "issues")
        self.assertEqual(w["wip_heavy"], ["Ann"])
