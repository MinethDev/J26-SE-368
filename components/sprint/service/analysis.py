"""Sprint Intelligence (owner: Wahalathanthri E. I.)

STUB: replace the body of analyze() with your real pipeline:
  sprint snapshots -> temporal features -> health/delay model (XGBoost/CatBoost) -> SHAP -> interventions.
Keep returning Insight objects (see contract.py and docs/CONTRACTS.md).

context received from the orchestrator:
  sprints: [{sourceId, name, state, startDate, endDate, completeDate, ...}]
  issues:  [{key, sprintId, storyPoints, statusCategory, assignee, ...}]
upstream:
  planning: insights from the planning component in this run (the planning baseline)
"""

from contract import AnalyzeRequest, Evidence, ExplanationItem, Insight, Prediction, Target

COMPONENT = "sprint"
MODEL_VERSION = "sprint-stub-0.1"


def analyze(request: AnalyzeRequest) -> list[Insight]:
    sprints = request.context.get("sprints", [])
    issues = request.context.get("issues", [])
    planning_baseline = next((i for i in request.upstream.get("planning", []) if i.get("type") == "planning-baseline"), None)

    insights = []
    for sprint in sprints:
        if sprint.get("state") != "active":
            continue
        sprint_issues = [i for i in issues if i.get("sprintId") == sprint.get("sourceId")]
        committed = sum(i.get("storyPoints") or 0 for i in sprint_issues)
        done = sum(i.get("storyPoints") or 0 for i in sprint_issues if i.get("statusCategory") == "Done")
        ratio = round(done / committed, 2) if committed else None

        explanation = [ExplanationItem(feature="completed_ratio", value=ratio, impact=ratio or 0.0)]
        evidence = []
        if planning_baseline:
            # Intelligence flow: the planning baseline arrives from the planning component.
            explanation.append(ExplanationItem(feature="planning_avg_points", value=planning_baseline["prediction"]["value"], impact=0.0))
            evidence.append(Evidence(source="component", ref="planning:planning-baseline", note="Planning baseline received from Planning Intelligence"))

        insights.append(
            Insight(
                component=COMPONENT,
                type="sprint-health",
                title=f"{sprint.get('name', 'Sprint')}: progress so far (stub)",
                target=Target(type="sprint", id=str(sprint.get("sourceId")), label=sprint.get("name")),
                prediction=Prediction(label="Completed / committed story points", value=ratio),
                severity="medium" if ratio is not None and ratio < 0.5 else "info",
                explanation=explanation,
                recommendations=["Replace this stub with the trained sprint-health model."],
                evidence=evidence,
                modelVersion=MODEL_VERSION,
                isStub=True,
            )
        )
    return insights
