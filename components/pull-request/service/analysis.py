"""Pull Request Intelligence (owner: Perera W. M. M.)

STUB: the research code in ../reviewer_recommendation, ../merge_readiness and ../code_review
will be connected here. Keep returning Insight objects (see contract.py and docs/CONTRACTS.md).

context received from the orchestrator:
  repository:   {fullName, ...} or None
  pullRequests: open PRs  [{number, title, body, author, files: [{path, patch, ...}], reviews: [...]}]
  history:      past PRs  [{number, author, createdAt, reviews: [{reviewer, state, submittedAt}], ...}]
upstream:
  quality: insights from the quality component in this run (file hotspots)
"""

from contract import AnalyzeRequest, Evidence, ExplanationItem, Insight, Prediction, Target

COMPONENT = "pull-request"
MODEL_VERSION = "pr-stub-0.1"


def analyze(request: AnalyzeRequest) -> list[Insight]:
    prs = request.context.get("pullRequests", [])
    hotspots = {i["target"]["id"] for i in request.upstream.get("quality", []) if i.get("type") == "quality-hotspot"}

    insights = []
    for pr in prs:
        ref = f"{pr.get('repo', '')}#{pr.get('number')}"
        files = [f.get("path") for f in pr.get("files", []) if f.get("path")]
        touched_hotspots = sorted(set(files) & hotspots)
        approvals = [r for r in pr.get("reviews", []) if r.get("state") == "APPROVED"]

        recommendations = ["Replace this stub with the merge-readiness checklist."]
        if touched_hotspots:
            # Intelligence flow: quality hotspots from Quality Intelligence raise review attention.
            recommendations.insert(0, f"Touches quality hotspot(s): {', '.join(touched_hotspots)}. Review these files carefully.")

        insights.append(
            Insight(
                component=COMPONENT,
                type="merge-readiness",
                title=f"PR #{pr.get('number')}: {pr.get('title', '')} (stub)",
                target=Target(type="pullRequest", id=str(pr.get("number")), label=pr.get("title")),
                prediction=Prediction(label="Readiness", value="Needs attention" if not approvals or touched_hotspots else "No blocking issues found"),
                severity="medium" if not approvals or touched_hotspots else "info",
                explanation=[
                    ExplanationItem(feature="approvals", value=len(approvals), impact=float(len(approvals))),
                    ExplanationItem(feature="quality_hotspots_touched", value=len(touched_hotspots), impact=-float(len(touched_hotspots))),
                ],
                recommendations=recommendations,
                evidence=[Evidence(source="github", ref=ref)],
                modelVersion=MODEL_VERSION,
                isStub=True,
            )
        )
    return insights
