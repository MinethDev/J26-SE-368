import unittest

import pandas as pd

from sprint_health.snapshot import SprintHistory, parse_sprint_ids

T = pd.Timestamp


def make_history() -> SprintHistory:
    sprints = pd.DataFrame([{"sprint_id": 1, "jira_sprint_id": 100, "project_id": 7,
                             "start_date": T("2020-01-01"), "end_date": T("2020-01-11")}])
    issues = pd.DataFrame([
        # A: committed at start, done on day 3
        {"issue_id": 1, "sprint_id": 1, "project_id": 7, "status": "Closed", "story_points": 5.0,
         "creation_date": T("2019-12-20"), "resolution_date": T("2020-01-04")},
        # B: added on day 5, still open
        {"issue_id": 2, "sprint_id": 1, "project_id": 7, "status": "Open", "story_points": 3.0,
         "creation_date": T("2019-12-20"), "resolution_date": pd.NaT},
        # C: committed, then moved out on day 2 (its final sprint is elsewhere, but we only know sprint 1)
        {"issue_id": 3, "sprint_id": 1, "project_id": 7, "status": "Open", "story_points": None,
         "creation_date": T("2019-12-20"), "resolution_date": pd.NaT},
        # D: added 2 hours after the sprint started, inside the commitment grace period
        {"issue_id": 4, "sprint_id": 1, "project_id": 7, "status": "Open", "story_points": 2.0,
         "creation_date": T("2019-12-20"), "resolution_date": pd.NaT},
    ])
    logs = pd.DataFrame([
        {"change_id": 1, "issue_id": 1, "field": "status", "from_value": "1", "to_value": "6", "creation_date": T("2020-01-04")},
        {"change_id": 2, "issue_id": 2, "field": "Sprint", "from_value": None, "to_value": "100", "creation_date": T("2020-01-06")},
        {"change_id": 3, "issue_id": 3, "field": "Sprint", "from_value": "100", "to_value": "200", "creation_date": T("2020-01-03")},
        {"change_id": 5, "issue_id": 4, "field": "Sprint", "from_value": None, "to_value": "100", "creation_date": T("2020-01-01 02:00")},
        {"change_id": 4, "issue_id": 3, "field": "Story Points", "from_value": None, "to_value": "8", "creation_date": T("2019-12-21")},
    ])
    return SprintHistory(issues, sprints, logs)


class SnapshotTest(unittest.TestCase):
    def test_not_yet_added_issues_are_not_removed_before_commitment(self):
        h = make_history()
        start = h.snapshot(1, T("2020-01-01"), h.committed_at_start(1), count_removed=False)
        self.assertEqual((start["issues"], start["removed_issues"]), (2, 0))

    def test_parse_sprint_ids(self):
        self.assertEqual(parse_sprint_ids("2486, 2670"), {2486, 2670})
        self.assertEqual(parse_sprint_ids(None), frozenset())

    def test_commitment_includes_grace_period_but_not_later_additions(self):
        self.assertEqual(make_history().committed_at_start(1), {1, 3, 4})

    def test_snapshot_uses_only_past_changes(self):
        h = make_history()
        committed = h.committed_at_start(1)
        day1 = h.snapshot(1, T("2020-01-02"), committed)
        self.assertEqual((day1["issues"], day1["done_issues"], day1["points"]), (3, 0, 15.0))
        day7 = h.snapshot(1, T("2020-01-08"), committed)
        self.assertEqual((day7["done_points"], day7["committed_done_points"]), (5.0, 5.0))
        self.assertEqual((day7["added_issues"], day7["removed_issues"], day7["removed_points"]), (1, 1, 8.0))

    def test_status_id_mapping_learned_from_final_status(self):
        self.assertEqual(make_history().status_map, {"6": "Closed"})


if __name__ == "__main__":
    unittest.main()
