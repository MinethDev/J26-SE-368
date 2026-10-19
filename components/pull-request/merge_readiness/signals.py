"""Readiness signals computed from PR events strictly before the assessment time."""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from merge_readiness.context import DECISION_EVENT_TYPES, PRContext, to_utc
from reviewer_recommendation.identity import is_bot, same_login


REVIEW_EVENT_TYPES = ("review", "review_comment")
SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class ReadinessSignals:
    as_of: pd.Timestamp
    approvals: tuple
    change_requests: tuple
    reviewers: tuple
    review_threads: int
    unanswered_threads: int
    last_human_activity: Optional[pd.Timestamp]
    days_since_activity: Optional[float]
    changed_lines: Optional[int]


def _is_human(event) -> bool:
    return event.actor is not None and not is_bot(event.actor, event.actor_type)


def effective_review_states(review_events, author) -> dict:
    """
    Latest effective review state per human reviewer.

    APPROVED and CHANGES_REQUESTED replace earlier states, COMMENTED leaves
    the state unchanged, and DISMISSED withdraws it (GitHub semantics).
    """

    states = {}

    for event in sorted(review_events, key=lambda e: e.timestamp):
        if event.event_type != "review" or same_login(event.actor, author):
            continue

        state = (event.state or "").upper()

        if state in ("APPROVED", "CHANGES_REQUESTED"):
            states[event.actor] = state
        elif state == "DISMISSED":
            states.pop(event.actor, None)

    return states


def compute_signals(context: PRContext, as_of) -> ReadinessSignals:
    as_of = to_utc(as_of)
    events = [e for e in context.events_before(as_of) if _is_human(e)]

    review_events = [
        e for e in events
        if e.event_type in REVIEW_EVENT_TYPES
        and not same_login(e.actor, context.author)
    ]

    states = effective_review_states(review_events, context.author)

    threads = [e for e in review_events if e.event_type == "review_comment"]
    unanswered = sum(
        not any(same_login(actor, context.author) for actor in thread.reply_actors)
        for thread in threads
    )

    activity = [
        e.timestamp for e in events if e.event_type not in DECISION_EVENT_TYPES
    ]
    last_activity = max(activity) if activity else None

    changed_lines = (
        context.additions + context.deletions
        if context.additions is not None and context.deletions is not None
        else None
    )

    return ReadinessSignals(
        as_of=as_of,
        approvals=tuple(sorted(r for r, s in states.items() if s == "APPROVED")),
        change_requests=tuple(sorted(r for r, s in states.items() if s == "CHANGES_REQUESTED")),
        reviewers=tuple(sorted({e.actor for e in review_events})),
        review_threads=len(threads),
        unanswered_threads=int(unanswered),
        last_human_activity=last_activity,
        days_since_activity=(
            (as_of - last_activity).total_seconds() / SECONDS_PER_DAY
            if last_activity is not None
            else None
        ),
        changed_lines=changed_lines,
    )
