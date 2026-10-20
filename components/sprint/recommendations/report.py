"""The sprint report: a template version that always works, and an optional LLM-written version.

The LLM only rewrites the facts it is given (prediction, drivers, recommendations) in plain
language; if it is switched off or unreachable, the template report is returned instead.
"""
import json
import urllib.request

from recommendations.config import LLM_PROVIDER, LLM_TIMEOUT_SECONDS, OLLAMA_MODEL, OLLAMA_URL

FEATURE_NAMES = {
    "delivered_so_far": "share of the commitment delivered so far",
    "burndown_gap": "gap behind the ideal burndown",
    "health_score": "sprint health score",
    "committed_points": "story points committed",
    "committed_issues": "issues committed",
    "planned_days": "sprint length in days",
    "elapsed_fraction": "share of the sprint gone",
    "scope_added": "work added after the start",
    "scope_removed": "work removed after the start",
    "unestimated": "share of issues without story points",
    "todo_share": "share of issues not started",
    "in_progress_share": "share of issues in progress",
    "team_prev_sprints": "number of earlier sprints by this team",
    "team_prev_delivered_mean": "team's average delivery in earlier sprints",
    "team_prev_missed_rate": "team's share of missed earlier sprints",
}


def template_report(sprint_name: str, result: dict, drivers: list[dict], health: dict | None = None) -> str:
    lines = [f"# Sprint report: {sprint_name}", ""]
    lines.append(f"**Risk of missing the commitment: {result['risk_level']} ({100 * result['probability']:.0f}%).**")
    if health:
        lines.append(f"Health score: {health['score']:.0f}/100 ({health['band']}).")
    lines += ["", "## Why"]
    for d in drivers:
        direction = "raises" if d["impact"] > 0 else "lowers"
        value = "unknown" if d["value"] is None else f"{d['value']:.2f}".rstrip("0").rstrip(".")
        lines.append(f"- {FEATURE_NAMES.get(d['feature'], d['feature'])} = {value}: {direction} the risk")
    lines += ["", "## Recommended actions"]
    for i, r in enumerate(result["recommendations"], 1):
        lines.append(f"{i}. **{r['title']}.** {r['action']} _Why: {r['reason']}_")
    lines += ["", "_Suggestions only: the team decides what to change._"]
    return "\n".join(lines)


def _ollama(prompt: str) -> str:
    body = json.dumps({"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.2}}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read())["response"].strip()


def sprint_report(sprint_name: str, result: dict, drivers: list[dict], health: dict | None = None) -> dict:
    """Returns {text, source}: source is 'llm' or 'template'."""
    facts = template_report(sprint_name, result, drivers, health)
    if LLM_PROVIDER != "ollama":
        return {"text": facts, "source": "template"}
    prompt = (
        "You are helping a Scrum team. Rewrite the sprint report below as a short, friendly summary for the "
        "team (at most 150 words), then the recommended actions as a numbered list. Use ONLY the facts and "
        "numbers given; do not invent names, numbers or actions.\n\n" + facts
    )
    try:
        return {"text": _ollama(prompt), "source": "llm"}
    except Exception:  # LLM off or unreachable: the template report is still complete
        return {"text": facts, "source": "template"}
