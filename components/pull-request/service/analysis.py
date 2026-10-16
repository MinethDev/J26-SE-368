"""Pull Request Intelligence (owner: Perera W. M. M.)

Connects the evaluated research code in ../reviewer_recommendation and
../merge_readiness to live PR data synced from GitHub by the platform.

context received from the orchestrator:
  repository:   {fullName, ...} or None
  pullRequests: open PRs  [{repo, number, title, author, createdAt, additions,
                            deletions, files: [...], reviews: [...]}]
  history:      past PRs  [{repo, number, title, author, createdAt,
                            reviews: [{reviewer, reviewerIsBot, state, submittedAt}]}]
upstream:
  quality: insights from the quality component in this run (file hotspots)
"""

import hashlib
import os
import sys
from pathlib import Path

import pandas as pd

# The research packages live one folder up (components/pull-request/).
COMPONENT_ROOT = Path(__file__).resolve().parent.parent
if str(COMPONENT_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPONENT_ROOT))

from merge_readiness.assessment import ATTENTION, BLOCKING, LABEL_INSUFFICIENT, LABEL_READY, PASS, assess  # noqa: E402
from code_review.ai_reviewer import (  # noqa: E402
    DEFAULT_PROMPT_VERSION,
    MODEL_NAME,
    STATUS_FINDINGS,
    STATUS_INVALID,
    STATUS_MODEL_ERROR,
    OllamaClient,
    run_review,
)
from merge_readiness.context import PRContext, PREvent, to_utc  # noqa: E402
from reviewer_recommendation.identity import is_bot, normalize_login, same_login  # noqa: E402
from reviewer_recommendation.recommender import (  # noqa: E402
    RecommenderConfig,
    ReviewerRecommender,
    ReviewHistory,
    fit_title_vectorizer,
)

from contract import AnalyzeRequest, Evidence, ExplanationItem, Insight, Prediction, Target  # noqa: E402

COMPONENT = "pull-request"
MODEL_VERSION = "pr-0.2 (rr-v1, mr-v1)"

# Settings selected on the validation split and frozen before the single test
# run (see components/pull-request/README.md, "Reviewer Recommendation").
REVIEWER_CONFIG = RecommenderConfig(
    activity_weight=0.25,
    author_weight=1.0,
    similarity_weight=0.25,
    half_life_days=90.0,
)
TOP_K_REVIEWERS = 3

# AI code review runs a local LLM (Ollama), which takes seconds per file, so each
# run reviews only the most recent open PRs and their smallest code changes.
# Set DEVINTEL_CODE_REVIEW=off to skip it (e.g. when Ollama is not installed).
CODE_REVIEW_ENABLED = os.environ.get("DEVINTEL_CODE_REVIEW", "on").lower() != "off"
CODE_REVIEW_MAX_PRS = int(os.environ.get("DEVINTEL_CODE_REVIEW_MAX_PRS", "3"))
CODE_REVIEW_MAX_FILES = 2
CODE_REVIEW_MAX_PATCH_LINES = 120
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cs", ".php", ".go", ".rb",
    ".kt", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".swift", ".scala",
}
SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _repo_of(pr: dict, request: AnalyzeRequest) -> str:
    repository = request.context.get("repository") or {}
    return pr.get("repo") or repository.get("fullName") or "unknown/unknown"


def _pr_ref(pr: dict, repo: str) -> str:
    return f"{repo}#{pr.get('number')}"


# ---------------------------------------------------------------------------
# 1. Reviewer recommendation
# ---------------------------------------------------------------------------

def build_review_pairs(prs: list) -> pd.DataFrame:
    """
    One row per (PR, human reviewer), timestamped at the reviewer's first review.

    Same definition as reviewer_recommendation/dataset.py, built from the
    platform's GitHub data instead of the offline dataset.
    """

    rows = []
    for pr in prs:
        author = normalize_login(pr.get("author"))
        first_review = {}
        for review in pr.get("reviews") or []:
            reviewer = normalize_login(review.get("reviewer"))
            submitted = review.get("submittedAt")
            if reviewer is None or submitted is None:
                continue
            if review.get("reviewerIsBot") or is_bot(reviewer) or same_login(reviewer, author):
                continue
            timestamp = to_utc(submitted)
            if reviewer not in first_review or timestamp < first_review[reviewer]:
                first_review[reviewer] = timestamp

        for reviewer, reviewed_at in first_review.items():
            rows.append({
                "repo_full_name": pr.get("repo"),
                "pr_number": pr.get("number"),
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
                "pr_author": author,
                "pr_title": pr.get("title") or "",
            })

    columns = ["repo_full_name", "pr_number", "reviewer", "reviewed_at", "pr_author", "pr_title"]
    return pd.DataFrame(rows, columns=columns)


def recommend_reviewers(open_prs: list, history: list, request: AnalyzeRequest) -> list:
    all_prs = history + open_prs
    pairs = build_review_pairs(all_prs)

    # Title vocabulary from PRs already reviewed (no information from the future
    # is used: the history filter below keeps only reviews before each PR opened).
    titles = [pr.get("title") or "" for pr in all_prs] or [""]
    recommender = ReviewerRecommender(ReviewHistory(pairs, fit_title_vectorizer(titles)), REVIEWER_CONFIG)

    insights = []
    for pr in open_prs:
        repo = _repo_of(pr, request)
        author = normalize_login(pr.get("author"))
        recommendations = (
            recommender.recommend(repo, author, pr.get("title"), pr.get("createdAt"), k=TOP_K_REVIEWERS)
            if not pairs.empty and pr.get("createdAt")
            else []
        )
        target = Target(type="pullRequest", id=str(pr.get("number")), label=pr.get("title"))
        evidence = [Evidence(source="github", ref=_pr_ref(pr, repo))]

        if not recommendations:
            insights.append(Insight(
                component=COMPONENT,
                type="reviewer-recommendation",
                title=f"PR #{pr.get('number')}: no reviewer history yet",
                target=target,
                prediction=Prediction(label="Recommended reviewers", value=[]),
                severity="info",
                recommendations=["Nobody has reviewed earlier PRs in this repository yet, so there is no history to recommend from."],
                evidence=evidence,
                modelVersion=MODEL_VERSION,
            ))
            continue

        top = recommendations[0]
        weights = {
            "activity": REVIEWER_CONFIG.activity_weight,
            "author_affinity": REVIEWER_CONFIG.author_weight,
            "title_similarity": REVIEWER_CONFIG.similarity_weight,
        }
        insights.append(Insight(
            component=COMPONENT,
            type="reviewer-recommendation",
            title=f"PR #{pr.get('number')}: recommended reviewers",
            target=target,
            prediction=Prediction(label="Recommended reviewers", value=[r.reviewer for r in recommendations]),
            severity="info",
            # Why the top candidate ranks first: weight x scaled signal, the terms of the score.
            explanation=[
                ExplanationItem(feature=f"{top.reviewer}: {name}", value=top.signals[name], impact=round(weights[name] * top.signals[name], 4))
                for name in weights
            ],
            recommendations=[f"{r.reviewer} (score {r.score:.2f}): " + "; ".join(r.reasons) for r in recommendations],
            evidence=evidence,
            modelVersion=MODEL_VERSION,
        ))
    return insights


# ---------------------------------------------------------------------------
# 2. Merge-readiness decision support
# ---------------------------------------------------------------------------

def to_pr_context(pr: dict, repo: str) -> PRContext:
    """Build the checklist input from the platform's GitHub data."""

    events = []
    for review in pr.get("reviews") or []:
        if not review.get("submittedAt"):
            continue
        events.append(PREvent(
            event_type="review",
            actor=normalize_login(review.get("reviewer")),
            actor_type="Bot" if review.get("reviewerIsBot") else "User",
            timestamp=to_utc(review["submittedAt"]),
                        state=review.get("state"),
        ))

    # Inline review threads: a thread starts with a comment that is not a reply;
    # its replies tell us whether the PR author has answered it.
    comments = pr.get("reviewComments") or []
    replies = {}
    for c in comments:
        if c.get("inReplyTo") is not None:
            replies.setdefault(c["inReplyTo"], []).append(normalize_login(c.get("author")))
    for c in comments:
        if c.get("inReplyTo") is not None or not c.get("createdAt"):
            continue
        events.append(PREvent(
            event_type="review_comment",
            actor=normalize_login(c.get("author")),
            actor_type="Bot" if c.get("authorIsBot") else "User",
            timestamp=to_utc(c["createdAt"]),
            reply_actors=tuple(r for r in replies.get(c.get("id"), []) if r),
        ))

    return PRContext(
        repo=repo,
        number=int(pr.get("number")),
        title=pr.get("title") or "",
        author=normalize_login(pr.get("author")),
        author_type="Bot" if pr.get("authorIsBot") else "User",
        created_at=to_utc(pr["createdAt"]) if pr.get("createdAt") else None,
        additions=pr.get("additions"),
        deletions=pr.get("deletions"),
        events=sorted(events, key=lambda e: e.timestamp),
        external_checks=pr.get("checks"),  # filled when the connector provides CI / conflict status
    )


def _severity(assessment) -> str:
    if assessment.label == LABEL_READY:
        return "info"
    if assessment.label == LABEL_INSUFFICIENT:
        return "low"
    if any(item.status == ATTENTION and item.severity == BLOCKING for item in assessment.items):
        return "high"
    return "medium"


def _impact(item) -> float:
    if item.status == PASS:
        return 1.0
    if item.status == ATTENTION:
        return -2.0 if item.severity == BLOCKING else -1.0
    return 0.0


def merge_readiness(open_prs: list, request: AnalyzeRequest) -> list:
    hotspots = {i["target"]["id"] for i in request.upstream.get("quality", []) if i.get("type") == "quality-hotspot"}

    insights = []
    for pr in open_prs:
        repo = _repo_of(pr, request)
        assessment = assess(to_pr_context(pr, repo))

        attention = [item for item in assessment.items if item.status == ATTENTION]
        recommendations = [f"{item.name}: {item.evidence}" for item in attention]

        # Intelligence flow: quality hotspots from Software Quality Intelligence.
        touched = sorted({f.get("path") for f in pr.get("files") or []} & hotspots)
        if touched:
            recommendations.append(f"Touches quality hotspot(s) flagged by Quality Intelligence: {', '.join(touched)}. Review these files carefully.")

        checks = pr.get("checks") or {}
        details = checks.get("details") or {}
        if checks.get("ci") or checks.get("merge_conflicts"):
            ci_text = {
                "pass": f"passing ({details.get('ciTotal', 0)} check(s))",
                "fail": f"failing: {', '.join(details.get('ciFailing') or [])}",
                "pending": f"still running: {', '.join(details.get('ciPending') or [])}",
            }.get(checks.get("ci"), "no CI configured")
            conflict_text = {"pass": "none", "fail": "conflicts with the base branch"}.get(checks.get("merge_conflicts"), "not yet computed by GitHub")
            recommendations.append(f"Live GitHub status: CI {ci_text}; merge conflicts: {conflict_text}.")

        recommendations.append(assessment.disclaimer)

        insights.append(Insight(
            component=COMPONENT,
            type="merge-readiness",
            title=f"PR #{pr.get('number')}: merge readiness",
            target=Target(type="pullRequest", id=str(pr.get("number")), label=pr.get("title")),
            prediction=Prediction(label="Readiness", value=assessment.label),
            severity=_severity(assessment),
            explanation=[ExplanationItem(feature=item.name, value=item.status, impact=_impact(item)) for item in assessment.items],
            recommendations=recommendations,
            evidence=[Evidence(source="github", ref=_pr_ref(pr, repo))]
            + [Evidence(source="component", ref=f"quality:{path}", note="Quality hotspot") for path in touched],
            modelVersion=MODEL_VERSION,
        ))
    return insights


# ---------------------------------------------------------------------------
# 3. AI-assisted code review (local LLM, prompt from code_review/ai_reviewer.py)
# ---------------------------------------------------------------------------

# Results are cached per (prompt, title, file, diff), so re-running the analysis
# does not ask the model again about code it has already reviewed.
_review_cache = {}


def reviewable_files(pr: dict) -> list:
    """Code files with a complete, reasonably small diff, smallest first."""

    files = []
    for f in pr.get("files") or []:
        patch = f.get("patch") or ""
        if not patch or f.get("status") == "removed" or "(truncated)" in patch:
            continue
        if Path(f.get("path") or "").suffix.lower() not in CODE_EXTENSIONS:
            continue
        if patch.count("\n") > CODE_REVIEW_MAX_PATCH_LINES:
            continue
        files.append(f)
    return sorted(files, key=lambda f: len(f["patch"]))[:CODE_REVIEW_MAX_FILES]


def review_file(client, pr: dict, f: dict):
    key = hashlib.sha256(f"{DEFAULT_PROMPT_VERSION}|{pr.get('title')}|{f['path']}|{f['patch']}".encode("utf-8")).hexdigest()
    if key in _review_cache:
        return _review_cache[key]
    result = run_review(pr.get("title") or "", f["path"], f["patch"], client=client)
    if result.status != STATUS_MODEL_ERROR:  # never cache a connection failure
        _review_cache[key] = result
    return result


def code_review(open_prs: list, request: AnalyzeRequest) -> list:
    if not CODE_REVIEW_ENABLED:
        return []

    client = OllamaClient()
    candidates = [(pr, files) for pr in open_prs if (files := reviewable_files(pr))][:CODE_REVIEW_MAX_PRS]

    insights = []
    for pr, files in candidates:
        repo = _repo_of(pr, request)
        target = Target(type="pullRequest", id=str(pr.get("number")), label=pr.get("title"))
        results = []
        for f in files:
            result = review_file(client, pr, f)
            if result.status == STATUS_MODEL_ERROR:
                # The model is unreachable: report it once instead of failing the whole analysis.
                insights.append(Insight(
                    component=COMPONENT,
                    type="code-review",
                    title="AI code review unavailable",
                    target=target,
                    prediction=Prediction(label="AI review findings", value="not run"),
                    severity="info",
                    recommendations=[f"The local model could not be reached ({result.error}). Start Ollama and re-run the analysis."],
                    evidence=[Evidence(source="github", ref=_pr_ref(pr, repo))],
                    modelVersion=MODEL_VERSION,
                ))
                return insights
            results.append((f, result))

        findings = [(f, item) for f, result in results if result.status == STATUS_FINDINGS for item in result.findings]
        invalid = [f["path"] for f, result in results if result.status == STATUS_INVALID]
        worst = max((SEVERITY_ORDER.get(item.get("severity"), 1) for _, item in findings), default=0)

        recommendations = [
            f"{f['path']}:{item.get('line') or '?'} [{item.get('severity')}, {item.get('category')}] "
            f"{item['finding']} Suggestion: {item['suggestion']}"
            for f, item in findings
        ]
        if not findings:
            recommendations.append("No supported issues found in the reviewed changes.")
        if invalid:
            recommendations.append(f"Skipped {len(invalid)} file(s) where the model returned an invalid response: {', '.join(invalid)}.")
        recommendations.append(
            f"Reviewed {len(results)} file(s): {', '.join(f['path'] for f, _ in results)}. Findings come from a local LLM "
            f"({MODEL_NAME}, prompt {DEFAULT_PROMPT_VERSION}); confidence is the model's own estimate, not a calibrated "
            "probability. A human reviewer decides."
        )

        insights.append(Insight(
            component=COMPONENT,
            type="code-review",
            title=f"PR #{pr.get('number')}: AI code review",
            target=target,
            prediction=Prediction(label="AI review findings", value=len(findings), unit="finding(s)"),
            severity={0: "info", 1: "low", 2: "medium", 3: "high"}[worst],
            # Each finding as a bar: a longer red bar means the model is more confident the issue is real.
            explanation=[
                ExplanationItem(
                    feature=f"{Path(f['path']).name}:{item.get('line') or '?'} {item.get('category')}",
                    value=item.get("severity"),
                    impact=-float(item["confidence"]),
                )
                for f, item in findings
            ],
            recommendations=recommendations,
            evidence=[Evidence(source="github", ref=f"{_pr_ref(pr, repo)}:{f['path']}") for f, _ in results],
            modelVersion=MODEL_VERSION,
        ))
    return insights


# ---------------------------------------------------------------------------
# Entry point called by app.py
# ---------------------------------------------------------------------------

def analyze(request: AnalyzeRequest) -> list[Insight]:
    open_prs = [pr for pr in request.context.get("pullRequests", []) if pr.get("number") is not None]
    history = request.context.get("history", [])
    return (
        recommend_reviewers(open_prs, history, request)
        + merge_readiness(open_prs, request)
        + code_review(open_prs, request)
    )