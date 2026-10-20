"""Sprint Intelligence (owner: Wahalathanthri E. I.)

Pipeline (code in the parent folder, shared with the research scripts):
  Jira data -> sprint snapshots -> health score -> XGBoost risk model -> SHAP drivers
  -> velocity and workload -> recommendations -> sprint report.
See live/pipeline.py. Returns Insight objects (see contract.py and docs/CONTRACTS.md).

context received from the orchestrator:
  sprints: [{sourceId, name, state, startDate, endDate, completeDate, ...}]
  issues:  [{key, sprintId, storyPoints, statusCategory, assignee, createdAt, resolvedAt, changelog?, ...}]
upstream:
  planning: insights from the planning component in this run (the planning baseline)
"""
import sys
from pathlib import Path

from contract import AnalyzeRequest, Evidence, ExplanationItem, Insight, Prediction, Target

SPRINT_ROOT = str(Path(__file__).resolve().parent.parent)  # components/sprint: the shared pipeline code
# The pull-request component also has a top-level 'preprocessing' package. When both services load in
# one process (components/test_contract.py), each must get its own, so ours is imported in isolation.
SHARED_PACKAGE_NAMES = {"preprocessing"}


def _import_pipeline():
    def shared():
        return [m for m in sys.modules if m.split(".")[0] in SHARED_PACKAGE_NAMES]

    others = {m: sys.modules.pop(m) for m in shared()}
    sys.path.insert(0, SPRINT_ROOT)
    try:
        from live.pipeline import analyze_sprints, load_model
    finally:
        sys.path.remove(SPRINT_ROOT)
        for m in shared():
            del sys.modules[m]
        sys.modules.update(others)
    return analyze_sprints, load_model


analyze_sprints, load_model = _import_pipeline()

COMPONENT = "sprint"
HEALTH_ONLY_VERSION = "sprint-health-rules-v1"
_saved = load_model()
MODEL_VERSION = _saved["model_version"] if _saved else HEALTH_ONLY_VERSION

SEVERITY = {"high": "high", "medium": "medium", "low": "info"}
HEALTH_SEVERITY = {"healthy": "info", "at-risk": "medium", "critical": "high"}


def _planning_avg_points(request: AnalyzeRequest) -> tuple[float | None, list[Evidence]]:
    baseline = next((i for i in request.upstream.get("planning", []) if i.get("type") == "planning-baseline"), None)
    if not baseline:
        return None, []
    value = baseline.get("prediction", {}).get("value")
    note = "Planning baseline (average story points per issue) used to size unestimated issues"
    return (float(value) if isinstance(value, (int, float)) else None,
            [Evidence(source="component", ref="planning:planning-baseline", note=note)])


def _progress_only(sprint: dict, issues: list[dict]) -> Insight:
    """For an active sprint the pipeline can't measure (no dates, or nothing committed yet)."""
    mine = [i for i in issues if str(i.get("sprintId")) == str(sprint.get("sourceId"))]
    total = sum(i.get("storyPoints") or 0 for i in mine)
    done = sum(i.get("storyPoints") or 0 for i in mine if i.get("statusCategory") == "Done")
    ratio = round(done / total, 2) if total else None
    return Insight(
        component=COMPONENT, type="sprint-progress",
        title=f"{sprint.get('name', 'Sprint')}: {'%d%%' % (100 * ratio) if ratio is not None else 'no story points'} of story points done",
        target=Target(type="sprint", id=str(sprint.get("sourceId")), label=sprint.get("name")),
        prediction=Prediction(label="Completed / total story points", value=ratio),
        explanation=[ExplanationItem(feature="completed_ratio", value=ratio, impact=0.0)],
        recommendations=["Add start and end dates to the sprint in Jira so its health and risk can be measured."],
        evidence=[Evidence(source="jira", ref=f"sprint:{sprint.get('sourceId')}")],
        modelVersion=MODEL_VERSION,
    )


def _insights(r: dict, planning_evidence: list[Evidence]) -> list[Insight]:
    sprint = r["sprint"]
    name = sprint.get("name") or "Sprint"
    target = Target(type="sprint", id=str(sprint.get("sourceId")), label=name)
    jira = [Evidence(source="jira", ref=f"sprint:{sprint.get('sourceId')}",
                     note=None if r["has_changelog"] else "No Jira change history: scope changes are estimated from issue creation dates")]
    s, health, out = r["snapshot"], r["health"], []

    if r["risk"]:
        risk = r["risk"]
        out.append(Insight(
            component=COMPONENT, type="sprint-risk",
            title=f"{name}: {risk['level']} risk of missing the commitment ({100 * risk['probability']:.0f}%)",
            target=target,
            prediction=Prediction(label="Chance the sprint delivers less than 80% of its commitment",
                                  value=round(risk["probability"], 3), unit="probability"),
            severity=SEVERITY[risk["level"]],
            explanation=[ExplanationItem(**d) for d in risk["drivers"]],
            recommendations=[f"{x['title']}: {x['action']} ({x['reason']})" for x in r["recommendations"]],
            evidence=jira + planning_evidence,
            modelVersion=risk["model_version"] or HEALTH_ONLY_VERSION,
        ))

    out.append(Insight(
        component=COMPONENT, type="sprint-health",
        title=f"{name}: health {health['score']:.0f}/100 ({health['band']})",
        target=target,
        prediction=Prediction(label="Sprint health score", value=health["score"], unit="score 0-100"),
        severity=HEALTH_SEVERITY[health["band"]],
        explanation=[ExplanationItem(feature=k, value=round(health["signals"][k], 3), impact=v)
                     for k, v in sorted(health["impacts"].items(), key=lambda kv: kv[1])],
        evidence=jira, modelVersion=HEALTH_ONLY_VERSION,
    ))

    if r["burndown"]:
        out.append(Insight(
            component=COMPONENT, type="sprint-burndown", title=f"{name}: burndown",
            target=target, prediction=Prediction(label="Remaining committed work per day", value=r["burndown"],
                                                 unit=r["burndown"][0]["unit"]),
            evidence=jira, modelVersion=HEALTH_ONLY_VERSION,
        ))

    w = r["workload"]
    if w["people"]:
        people = [{"assignee": n, **p} for n, p in sorted(w["people"].items(), key=lambda kv: -kv[1][f"open_{w['unit']}"])]
        flags = [x for x in (r["recommendations"] or []) if x["id"] in ("rebalance-work", "limit-wip", "assign-work")]
        out.append(Insight(
            component=COMPONENT, type="sprint-workload",
            title=f"{name}: workload {'uneven' if w['imbalanced'] else 'balanced'} across {w['assignees']} people",
            target=target,
            prediction=Prediction(label="Open work per person", value={
                "unit": w["unit"], "imbalance": w["imbalance"], "people": people,
                "unassignedOpenIssues": w["unassigned_open_issues"]}),
            severity="medium" if w["overloaded"] or w["imbalanced"] else "info",
            explanation=[ExplanationItem(feature="imbalance_gini", value=w["imbalance"], impact=w["imbalance"])],
            recommendations=[f"{x['title']}: {x['action']}" for x in flags],
            evidence=jira, modelVersion=HEALTH_ONLY_VERSION,
        ))

    if r["report"]:
        out.append(Insight(
            component=COMPONENT, type="sprint-report", title=f"{name}: sprint report",
            target=target, prediction=Prediction(label=f"Sprint report ({r['report']['source']})", value=r["report"]["text"]),
            evidence=jira + planning_evidence, modelVersion=MODEL_VERSION,
        ))
    return out


def analyze(request: AnalyzeRequest) -> list[Insight]:
    context = request.context
    avg_points, planning_evidence = _planning_avg_points(request)
    results = analyze_sprints(context, avg_points)
    measured = {str(r["sprint"].get("sourceId")) for r in results if r["risk"] or r["snapshot"]["committed_issues"]}

    insights = []
    for r in results:
        if r["snapshot"]["committed_issues"] or r["risk"]:
            insights += _insights(r, planning_evidence)
    for sprint in context.get("sprints", []):
        if sprint.get("state") == "active" and str(sprint.get("sourceId")) not in measured:
            insights.append(_progress_only(sprint, context.get("issues", [])))
    return insights
