"""Project Planning Intelligence (owner: Vidusini W. M. O.)

STUB: replace the body of analyze() with your real pipeline:
  requirements text -> requirement extraction (LLM) -> effort model -> SHAP -> plan + risks.
Keep returning Insight objects (see contract.py and docs/CONTRACTS.md).

context received from the orchestrator:
  requirements: uploaded documents  [{fileName, rawText, items, ...}]
  issues:       historical Jira issues [{key, type, storyPoints, status, ...}]
"""

from statistics import mean

from contract import AnalyzeRequest, ExplanationItem, Insight, Prediction, Target

COMPONENT = "planning"
MODEL_VERSION = "planning-stub-0.1"


def analyze(request: AnalyzeRequest) -> list[Insight]:
    ctx = request.context
    requirements = ctx.get("requirements", [])
    issues = ctx.get("issues", [])
    points = [i["storyPoints"] for i in issues if isinstance(i.get("storyPoints"), (int, float))]
    avg_points = round(mean(points), 2) if points else None

    insights = [
        Insight(
            component=COMPONENT,
            type="planning-baseline",
            title="Planning baseline from historical issues (stub)",
            target=Target(type="project", id=request.projectId),
            prediction=Prediction(label="Average story points per issue", value=avg_points, unit="points"),
            confidence=None,
            explanation=[ExplanationItem(feature="historical_issues", value=len(points), impact=1.0)] if points else [],
            recommendations=["Replace this stub with the trained effort-estimation model."],
            modelVersion=MODEL_VERSION,
            isStub=True,
        )
    ]
    for doc in requirements:
        insights.append(
            Insight(
                component=COMPONENT,
                type="requirements-received",
                title=f"Requirement document received: {doc.get('fileName', 'document')} (stub)",
                target=Target(type="requirement", id=str(doc.get("sourceId", doc.get("fileName", "doc"))), label=doc.get("fileName")),
                prediction=Prediction(label="Characters of text extracted", value=len(doc.get("rawText", ""))),
                recommendations=["Requirement extraction (LLM) will list functional and non-functional requirements here."],
                modelVersion=MODEL_VERSION,
                isStub=True,
            )
        )
    return insights
