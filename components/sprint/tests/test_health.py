import unittest

from sprint_health.health import AT_RISK, CRITICAL, HEALTHY, assess, delivered_share


def snap(**overrides) -> dict:
    s = {
        "elapsed_fraction": 0.5, "issues": 10, "committed_issues": 10, "committed_points": 20.0,
        "committed_done_issues": 5, "committed_done_points": 10.0,
        "added_issues": 0, "added_points": 0.0, "removed_issues": 0, "removed_points": 0.0,
        "unestimated_issues": 0, "todo_issues": 0,
    }
    s.update(overrides)
    return s


class HealthTest(unittest.TestCase):
    def test_on_track_sprint_is_healthy(self):
        result = assess(snap())
        self.assertEqual((result["score"], result["band"]), (100.0, HEALTHY))

    def test_falling_behind_lowers_score_and_explains_why(self):
        result = assess(snap(committed_done_points=0.0, todo_issues=10))
        self.assertLess(result["score"], 70)
        self.assertEqual(min(result["impacts"], key=result["impacts"].get), "burndown_gap")

    def test_everything_wrong_is_critical(self):
        result = assess(snap(elapsed_fraction=1.0, committed_done_points=0.0, todo_issues=10,
                             added_points=20.0, removed_points=20.0, unestimated_issues=10))
        self.assertEqual((result["score"], result["band"]), (0.0, CRITICAL))

    def test_uses_issue_counts_when_nothing_has_points(self):
        s = snap(committed_points=0.0, committed_done_points=0.0, committed_done_issues=5)
        self.assertEqual(delivered_share(s), 0.5)

    def test_moderate_problems_are_at_risk(self):
        result = assess(snap(committed_done_points=2.0, added_points=10.0))
        self.assertEqual(result["band"], AT_RISK)


if __name__ == "__main__":
    unittest.main()
