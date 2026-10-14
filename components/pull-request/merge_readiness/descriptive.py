"""
Descriptive statistics: assess every decided PR immediately before its
final merge/close event and summarize the checklist outputs.

These statistics describe how the checklist behaves on historical data.
They are not a validation of readiness: there is no readiness ground truth.
"""

import pandas as pd

from merge_readiness.assessment import ATTENTION, UNKNOWN, assess
from merge_readiness.config import ReadinessThresholds
from merge_readiness.context import decision_outcome
from merge_readiness.signals import compute_signals
from reviewer_recommendation.identity import is_bot


ITEM_KEYS = (
    "human_approval",
    "change_requests",
    "unanswered_threads",
    "review_coverage",
    "recent_activity",
    "change_size",
    "external_checks",
)


def assess_at_decision(contexts, thresholds: ReadinessThresholds = None) -> pd.DataFrame:
    """One row per decided PR: outcome, checklist label and statuses, raw signals."""

    rows = []

    for context in contexts:
        outcome = decision_outcome(context)

        if outcome is None:
            continue

        assessment = assess(context, as_of=outcome.decision_time, thresholds=thresholds)
        signals = compute_signals(context, outcome.decision_time)

        rows.append({
            "repo_full_name": context.repo,
            "pr_number": context.number,
            "created_at": context.created_at,
            "decision_time": outcome.decision_time,
            "outcome": outcome.outcome,
            "author_group": "bot" if is_bot(context.author, context.author_type) else "human",
            "label": assessment.label,
            **{f"status_{item.key}": item.status for item in assessment.items},
            "approvals": len(signals.approvals),
            "change_requests": len(signals.change_requests),
            "reviewers": len(signals.reviewers),
            "review_threads": signals.review_threads,
            "unanswered_threads": signals.unanswered_threads,
            "days_since_activity": signals.days_since_activity,
            "changed_lines": signals.changed_lines,
        })

    return pd.DataFrame(rows)


def _distribution(series) -> dict:
    counts = series.value_counts()
    total = int(counts.sum())

    return {
        str(key): {"n": int(value), "share": round(float(value) / total, 4)}
        for key, value in counts.items()
    }


def _attention_rates(frame) -> dict:
    return {
        key: {
            "attention": round(float((frame[f"status_{key}"] == ATTENTION).mean()), 4),
            "unknown": round(float((frame[f"status_{key}"] == UNKNOWN).mean()), 4),
        }
        for key in ITEM_KEYS
    }


def describe(frame: pd.DataFrame) -> dict:
    """Label and item distributions overall, by outcome, and by author group."""

    groups = {"all": frame}

    for column in ("outcome", "author_group"):
        for value, block in frame.groupby(column):
            groups[f"{column}={value}"] = block

    for (outcome, author_group), block in frame.groupby(["outcome", "author_group"]):
        groups[f"outcome={outcome},author_group={author_group}"] = block

    return {
        name: {
            "n": int(len(block)),
            "labels": _distribution(block["label"]),
            "items": _attention_rates(block),
        }
        for name, block in groups.items()
    }
