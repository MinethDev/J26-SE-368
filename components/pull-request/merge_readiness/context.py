"""
Pull request context: the input shared by the readiness checklist.

The same structure can be built from the offline dataset (below) or, later,
from the DevIntel data integration layer.
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from preprocessing.extractor import extract_review_events
from reviewer_recommendation.dataset import PR_KEY, build_pr_table
from reviewer_recommendation.identity import normalize_login


DECISION_EVENT_TYPES = ("merged", "closed")


@dataclass(frozen=True)
class PREvent:
    event_type: str
    actor: Optional[str]
    actor_type: Optional[str]
    timestamp: pd.Timestamp
    state: Optional[str] = None
    # Logins that replied in an inline review thread. The dataset has no
    # timestamps for replies, so they cannot be filtered by assessment time.
    reply_actors: tuple = ()


@dataclass
class PRContext:
    repo: str
    number: int
    title: str
    author: Optional[str]
    author_type: Optional[str]
    created_at: pd.Timestamp
    additions: Optional[int]
    deletions: Optional[int]
    events: list = field(default_factory=list)
    # Optional results from external systems, e.g.
    # {"ci": "pass", "quality_gate": "fail", "merge_conflicts": "pass"}.
    external_checks: Optional[dict] = None

    def events_before(self, as_of) -> list:
        """Events strictly before the assessment time."""

        return [event for event in self.events if event.timestamp < as_of]


@dataclass(frozen=True)
class PROutcome:
    repo: str
    number: int
    outcome: str
    decision_time: pd.Timestamp


def to_utc(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")

    return timestamp.tz_convert("UTC")


def _optional_int(value):
    if value is None or pd.isna(value):
        return None

    return int(value)


def _reply_actors(replies) -> tuple:
    if replies is None:
        return ()

    actors = (
        normalize_login(reply.get("reviewer"))
        for reply in replies
        if reply is not None
    )

    return tuple(actor for actor in actors if actor is not None)


def contexts_from_raw(raw_df: pd.DataFrame):
    """
    Build PR contexts from the raw shard.

    Returns (contexts, stats). Duplicate PR rows are removed and events
    without a valid timestamp are dropped.
    """

    prs = build_pr_table(raw_df)
    events = extract_review_events(prs)
    events["timestamp"] = pd.to_datetime(
        events["timestamp"], utc=True, errors="coerce"
    )

    undated = int(events["timestamp"].isna().sum())
    events = events.dropna(subset=["timestamp"]).sort_values(
        PR_KEY + ["timestamp"], kind="mergesort"
    )

    events_by_pr = {
        key: [
            PREvent(
                event_type=row.event_type,
                actor=normalize_login(row.reviewer),
                actor_type=row.reviewer_type,
                timestamp=row.timestamp,
                state=row.state if isinstance(row.state, str) else None,
                reply_actors=_reply_actors(row.thread_replies),
            )
            for row in group.itertuples(index=False)
        ]
        for key, group in events.groupby(PR_KEY, sort=False)
    }

    contexts = [
        PRContext(
            repo=row.repo_full_name,
            number=int(row.pr_number),
            title=row.title,
            author=normalize_login(row.created_by),
            author_type=row.created_by_type,
            created_at=row.created_at,
            additions=_optional_int(row.additions),
            deletions=_optional_int(row.deletions),
            events=events_by_pr.get((row.repo_full_name, row.pr_number), []),
        )
        for row in prs.itertuples(index=False)
    ]

    stats = {
        "raw_pr_rows": int(len(raw_df)),
        "unique_prs": int(len(prs)),
        "undated_events_dropped": undated,
    }

    return contexts, stats


def decision_outcome(context: PRContext) -> Optional[PROutcome]:
    """
    Final outcome and decision time of a closed PR.

    Merged PRs use the last merge event (a close event may follow it);
    closed PRs use the last close event. Returns None for undecided PRs.
    """

    merges = [e.timestamp for e in context.events if e.event_type == "merged"]

    if merges:
        return PROutcome(context.repo, context.number, "merged", max(merges))

    closes = [e.timestamp for e in context.events if e.event_type == "closed"]

    if closes:
        return PROutcome(context.repo, context.number, "closed", max(closes))

    return None
