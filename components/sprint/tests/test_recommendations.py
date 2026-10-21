import unittest
from unittest import mock

from productivity.workload import team_workload
from recommendations import report
from recommendations.interventions import recommend


def features(**overrides) -> dict:
    f = {"elapsed_fraction": 0.5, "committed_issues": 10, "delivered_so_far": 0.5, "burndown_gap": 0.0,
         "scope_added": 0.0, "unestimated": 0.0, "todo_share": 0.0, "team_prev_sprints": 5,
         "team_prev_missed_rate": 0.2, "team_prev_delivered_mean": 0.9}
    f.update(overrides)
    return f


class RecommendTest(unittest.TestCase):
    def test_healthy_sprint_is_on_track(self):
        result = recommend(features(), 0.1)
        self.assertEqual(result["risk_level"], "low")
        self.assertEqual([r["id"] for r in result["recommendations"]], ["on-track"])

    def test_behind_sprint_gets_scope_advice_with_numbers(self):
        result = recommend(features(delivered_so_far=0.2, burndown_gap=0.6, todo_share=0.6), 0.9)
        ids = [r["id"] for r in result["recommendations"]]
        self.assertEqual(ids[0], "reduce-scope")
        self.assertIn("start-or-drop-unstarted", ids)
        self.assertIn("40%", result["recommendations"][0]["reason"])  # projected delivery 0.2 / 0.5

    def test_shap_driver_moves_a_rule_up(self):
        f = features(scope_added=0.5, todo_share=0.5)
        plain = recommend(f, 0.8)
        driven = recommend(f, 0.8, drivers=[{"feature": "scope_added", "value": 0.5, "impact": 0.9}])
        self.assertEqual(plain["recommendations"][0]["id"], "start-or-drop-unstarted")
        self.assertEqual(driven["recommendations"][0]["id"], "freeze-scope")
        self.assertEqual(driven["recommendations"][0]["driver"], ["scope_added"])

    def test_overcommitment_and_workload_rules(self):
        velocity = {"ratio": 1.9, "overcommitted": True, "velocity": 20.0, "committed": 38.0, "unit": "points"}
        workload = team_workload([
            {"assignee": "Ann", "story_points": 13, "status_category": "To Do"},
            {"assignee": "Ann", "story_points": 8, "status_category": "In Progress"},
            {"assignee": "Ben", "story_points": 3, "status_category": "To Do"},
            {"assignee": "Cal", "story_points": 2, "status_category": "Done"},
            {"assignee": None, "story_points": 5, "status_category": "To Do"},
        ])
        result = recommend(features(), 0.75, velocity=velocity, workload=workload, limit=10)
        by_id = {r["id"]: r for r in result["recommendations"]}
        self.assertIn("about 18 points", by_id["overcommitted"]["action"])
        self.assertIn("Ann", by_id["rebalance-work"]["title"])
        self.assertIn("Cal", by_id["rebalance-work"]["action"])
        self.assertIn("assign-work", by_id)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.result = recommend(features(delivered_so_far=0.2, burndown_gap=0.6), 0.9)
        self.drivers = [{"feature": "delivered_so_far", "value": 0.2, "impact": 1.1}]

    def test_template_report_has_risk_reasons_and_actions(self):
        text = report.sprint_report("Sprint 7", self.result, self.drivers)["text"]
        self.assertIn("high (90%)", text)
        self.assertIn("share of the commitment delivered so far = 0.2: raises the risk", text)
        self.assertIn("Reduce the sprint scope", text)

    def test_llm_failure_falls_back_to_template(self):
        with mock.patch.object(report, "LLM_PROVIDER", "ollama"), \
                mock.patch.object(report, "_ollama", side_effect=OSError("no server")):
            out = report.sprint_report("Sprint 7", self.result, self.drivers)
        self.assertEqual(out["source"], "template")

    def test_llm_text_is_used_when_available(self):
        with mock.patch.object(report, "LLM_PROVIDER", "ollama"), \
                mock.patch.object(report, "_ollama", return_value="Short summary."):
            out = report.sprint_report("Sprint 7", self.result, self.drivers)
        self.assertEqual(out, {"text": "Short summary.", "source": "llm"})
