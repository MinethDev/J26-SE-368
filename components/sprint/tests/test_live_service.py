"""The live pipeline and the sprint service on a small made-up Jira project."""
import importlib
import sys
import unittest
from pathlib import Path

from live.pipeline import analyze_sprints

SERVICE_DIR = Path(__file__).resolve().parent.parent / "service"


def jira_context(with_changelog: bool = True) -> dict:
    """Two finished sprints and one active sprint, 7 of 10 days in, with half its work not started."""
    sprints = [
        {"sourceId": "101", "name": "Sprint 1", "state": "closed", "startDate": "2025-01-01T09:00:00.000Z", "endDate": "2025-01-11T09:00:00.000Z"},
        {"sourceId": "102", "name": "Sprint 2", "state": "closed", "startDate": "2025-01-11T09:00:00.000Z", "endDate": "2025-01-21T09:00:00.000Z"},
        {"sourceId": "103", "name": "Sprint 3", "state": "active", "startDate": "2025-01-21T09:00:00.000Z", "endDate": "2025-01-31T09:00:00.000Z"},
    ]
    issues = []
    for s, n_done in (("101", 3), ("102", 2)):
        for k in range(4):
            done = k < n_done
            issues.append({"key": f"P-{s}{k}", "sprintId": s, "storyPoints": 3, "assignee": "Ann" if k % 2 else "Ben",
                           "status": "Done" if done else "To Do", "statusCategory": "Done" if done else "To Do",
                           "createdAt": "2024-12-20T09:00:00.000Z",
                           "resolvedAt": f"2025-01-{'05' if s == '101' else '15'}T09:00:00.000Z" if done else None})
    people = ["Ann", "Ann", "Ann", "Ann", "Ben", None]
    for k, who in enumerate(people):
        cat = "Done" if k == 0 else "In Progress" if k == 1 else "To Do"
        issues.append({"key": f"P-103{k}", "sprintId": "103", "storyPoints": 5 if k < 5 else None, "assignee": who,
                       "status": cat, "statusCategory": cat, "createdAt": "2025-01-15T09:00:00.000Z",
                       "resolvedAt": "2025-01-24T09:00:00.000Z" if k == 0 else None})
    # One issue added mid-sprint (created after the start).
    issues.append({"key": "P-1039", "sprintId": "103", "storyPoints": 8, "assignee": "Ann", "status": "To Do",
                   "statusCategory": "To Do", "createdAt": "2025-01-25T09:00:00.000Z", "resolvedAt": None})
    if with_changelog:
        issues[-1]["changelog"] = [{"field": "Sprint", "from": None, "to": "103", "at": "2025-01-25T10:00:00.000Z"}]
        issues[8]["changelog"] = [{"field": "status", "from": "1", "to": "3", "at": "2025-01-22T09:00:00.000Z"},
                                  {"field": "status", "from": "3", "to": "10001", "at": "2025-01-24T09:00:00.000Z"}]
    return {"sprints": sprints, "issues": issues, "asOf": "2025-01-28T09:00:00.000Z"}


class LivePipelineTest(unittest.TestCase):
    def test_active_sprint_gets_risk_health_workload_and_actions(self):
        [r] = analyze_sprints(jira_context())
        self.assertEqual(r["sprint"]["name"], "Sprint 3")
        self.assertEqual(r["snapshot"]["committed_issues"], 6)
        self.assertEqual(r["snapshot"]["added_issues"], 1)
        self.assertEqual(r["closed_sprints_seen"], 2)
        self.assertEqual(r["features"]["team_prev_sprints"], 2)
        self.assertAlmostEqual(r["features"]["elapsed_fraction"], 0.7)
        self.assertEqual(r["snapshot"]["in_progress_issues"], 1)  # current status used when there's no history
        self.assertIn(r["risk"]["level"], ("medium", "high"))
        self.assertIn("Ann", r["workload"]["overloaded"])
        ids = [x["id"] for x in r["recommendations"]]
        self.assertIn("reduce-scope", ids)
        self.assertEqual(len(r["burndown"]), 8)
        self.assertTrue(r["report"]["text"].startswith("# Sprint report: Sprint 3"))

    def test_works_without_changelog(self):
        [r] = analyze_sprints(jira_context(with_changelog=False))
        self.assertFalse(r["has_changelog"])
        self.assertEqual(r["snapshot"]["added_issues"], 1)  # from the creation date
        self.assertIsNotNone(r["risk"])

    def test_sprint_without_dates_is_skipped(self):
        context = {"sprints": [{"sourceId": "s1", "name": "Sprint 1", "state": "active"}],
                   "issues": [{"sprintId": "s1", "storyPoints": 5, "statusCategory": "Done"}]}
        self.assertEqual(analyze_sprints(context), [])


class ServiceTest(unittest.TestCase):
    def setUp(self):
        for name in ("app", "analysis", "contract"):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(SERVICE_DIR))
        self.addCleanup(sys.path.remove, str(SERVICE_DIR))
        self.analysis = importlib.import_module("analysis")
        self.contract = importlib.import_module("contract")

    def test_insights_for_active_sprint(self):
        upstream = {"planning": [{"type": "planning-baseline", "prediction": {"value": 4.0}}]}
        request = self.contract.AnalyzeRequest(projectId="p", context=jira_context(), upstream=upstream)
        insights = self.analysis.analyze(request)
        types = [i.type for i in insights]
        self.assertEqual(types, ["sprint-risk", "sprint-health", "sprint-burndown", "sprint-workload", "sprint-report"])
        self.assertFalse(any(i.isStub for i in insights))
        risk = insights[0]
        self.assertEqual(risk.target.id, "103")
        self.assertTrue(risk.recommendations)
        self.assertIn("planning:planning-baseline", [e.ref for e in risk.evidence])

    def test_sprint_without_dates_still_reports_progress(self):
        context = {"sprints": [{"sourceId": "s1", "name": "Sprint 1", "state": "active"}],
                   "issues": [{"sprintId": "s1", "storyPoints": 5, "statusCategory": "Done"},
                              {"sprintId": "s1", "storyPoints": 3, "statusCategory": "In Progress"}]}
        [insight] = self.analysis.analyze(self.contract.AnalyzeRequest(projectId="p", context=context))
        self.assertEqual((insight.type, insight.prediction.value), ("sprint-progress", 0.62))
