"""Software Quality Intelligence (owner: Senura Virantha S.J.)

STUB: replace the body of analyze() with your real pipeline:
  SonarQube metrics + churn -> features -> quality-risk model -> SHAP -> prioritised hotspots + actions.
Keep returning Insight objects (see contract.py and docs/CONTRACTS.md).

context received from the orchestrator:
  repository:       {fullName, ...} or None
  qualitySnapshots: [{path, metrics: {ncloc, complexity, code_smells, bugs, ...}, issueCounts}]
  pullRequests:     recent PRs [{files: [{path, additions, deletions}], ...}] (for churn)
"""

from contract import AnalyzeRequest, Evidence, ExplanationItem, Insight, Prediction, Target

COMPONENT = "quality"
MODEL_VERSION = "quality-stub-0.1"
TOP_N = 5


def _num(metrics: dict, key: str) -> float:
    value = metrics.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.0


def analyze(request: AnalyzeRequest) -> list[Insight]:
    snapshots = request.context.get("qualitySnapshots", [])

    def placeholder_score(s):  # NOT a model: a visible placeholder until the trained model is plugged in
        m = s.get("metrics") or {}
        return _num(m, "complexity") + 2 * _num(m, "bugs") + _num(m, "code_smells")

    ranked = sorted(snapshots, key=placeholder_score, reverse=True)[:TOP_N]
    insights = []
    for rank, s in enumerate(ranked, start=1):
        m = s.get("metrics") or {}
        insights.append(
            Insight(
                component=COMPONENT,
                type="quality-hotspot",
                title=f"Hotspot #{rank}: {s.get('path')} (stub)",
                target=Target(type="file", id=s.get("path") or str(rank), label=s.get("path")),
                prediction=Prediction(label="Placeholder risk score", value=placeholder_score(s)),
                severity="high" if rank == 1 else "medium",
                explanation=[
                    ExplanationItem(feature="complexity", value=m.get("complexity"), impact=_num(m, "complexity")),
                    ExplanationItem(feature="bugs", value=m.get("bugs"), impact=2 * _num(m, "bugs")),
                    ExplanationItem(feature="code_smells", value=m.get("code_smells"), impact=_num(m, "code_smells")),
                ],
                recommendations=["Replace this stub with the trained quality-risk model."],
                evidence=[Evidence(source="sonarqube", ref=s.get("sourceId", s.get("path", "")))],
                modelVersion=MODEL_VERSION,
                isStub=True,
            )
        )
    return insights
