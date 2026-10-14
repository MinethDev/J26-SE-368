"""
Build the reviewer-recommendation dataset from the raw pull request shard.

Ground truth for a pull request is the set of human accounts, other than the
author, that submitted a review or an inline review comment on it.
"""

from dataclasses import dataclass

import pandas as pd

from preprocessing.cleaner import clean_pr_data
from preprocessing.extractor import extract_review_events
from reviewer_recommendation.identity import is_bot, normalize_login, same_login


PR_KEY = ["repo_full_name", "pr_number"]
REVIEW_EVENT_TYPES = ("review", "review_comment")

ACTIVITY_COLUMNS = PR_KEY + ["reviewer", "event_type", "timestamp"]


@dataclass
class ReviewerDataset:
    prs: pd.DataFrame
    pairs: pd.DataFrame
    evaluation_prs: pd.DataFrame
    stats: dict


def build_pr_table(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Clean PR records, drop undated PRs, and remove duplicate PR rows."""

    prs = clean_pr_data(raw_df)
    prs = prs.dropna(subset=["created_at"])
    prs = prs.drop_duplicates(subset=PR_KEY, keep="first")

    return prs.reset_index(drop=True)


def build_review_activity(prs: pd.DataFrame) -> pd.DataFrame:
    """Extract review events by eligible human reviewers."""

    events = extract_review_events(prs)

    if events.empty:
        return pd.DataFrame(columns=ACTIVITY_COLUMNS)

    events = events[events["event_type"].isin(REVIEW_EVENT_TYPES)].copy()
    events["reviewer"] = events["reviewer"].map(normalize_login)
    events = events[events["reviewer"].notna()]

    bot_mask = pd.Series(
        [
            is_bot(login, account_type)
            for login, account_type in zip(
                events["reviewer"], events["reviewer_type"]
            )
        ],
        index=events.index,
        dtype=bool,
    )

    author_mask = pd.Series(
        [
            same_login(reviewer, author)
            for reviewer, author in zip(events["reviewer"], events["pr_author"])
        ],
        index=events.index,
        dtype=bool,
    )

    events = events[~bot_mask & ~author_mask].copy()

    events["timestamp"] = pd.to_datetime(
        events["timestamp"], utc=True, errors="coerce"
    )
    events = events.dropna(subset=["timestamp"])

    events = events.drop_duplicates(
        subset=PR_KEY + [
            "event_type",
            "reviewer",
            "timestamp",
            "review_id",
            "comment_id",
        ]
    )

    return events[ACTIVITY_COLUMNS].reset_index(drop=True)


def build_review_pairs(
    activity: pd.DataFrame, prs: pd.DataFrame
) -> pd.DataFrame:
    """One row per (PR, reviewer), timestamped at the reviewer's first review."""

    pairs = (
        activity
        .groupby(PR_KEY + ["reviewer"], as_index=False)["timestamp"]
        .min()
        .rename(columns={"timestamp": "reviewed_at"})
    )

    pr_details = prs[PR_KEY + ["created_by", "title", "created_at"]].rename(
        columns={
            "created_by": "pr_author",
            "title": "pr_title",
            "created_at": "pr_created_at",
        }
    )

    pairs = pairs.merge(
        pr_details, on=PR_KEY, how="inner", validate="many_to_one"
    )

    return pairs.sort_values(
        ["repo_full_name", "reviewed_at", "pr_number", "reviewer"],
        kind="mergesort",
    ).reset_index(drop=True)


def build_evaluation_prs(
    prs: pd.DataFrame, pairs: pd.DataFrame
) -> pd.DataFrame:
    """PRs with at least one eligible reviewer, with their true reviewers."""

    truth = (
        pairs
        .groupby(PR_KEY)["reviewer"]
        .agg(lambda reviewers: sorted(set(reviewers)))
        .rename("true_reviewers")
        .reset_index()
    )

    evaluation_prs = prs[
        PR_KEY + ["title", "created_by", "created_by_type", "created_at"]
    ].merge(truth, on=PR_KEY, how="inner", validate="one_to_one")

    return evaluation_prs.sort_values(
        ["repo_full_name", "created_at", "pr_number"], kind="mergesort"
    ).reset_index(drop=True)


def build_reviewer_dataset(raw_df: pd.DataFrame) -> ReviewerDataset:
    """Run the full pipeline from raw shard to evaluation-ready tables."""

    prs = build_pr_table(raw_df)
    activity = build_review_activity(prs)
    pairs = build_review_pairs(activity, prs)
    evaluation_prs = build_evaluation_prs(prs, pairs)

    stats = {
        "raw_pr_rows": int(len(raw_df)),
        "unique_prs": int(len(prs)),
        "duplicate_or_undated_pr_rows_removed": int(len(raw_df) - len(prs)),
        "eligible_review_events": int(len(activity)),
        "review_pairs": int(len(pairs)),
        "prs_with_eligible_reviewer": int(len(evaluation_prs)),
        "prs_without_eligible_reviewer": int(len(prs) - len(evaluation_prs)),
        "unique_reviewers": int(pairs["reviewer"].nunique()),
    }

    return ReviewerDataset(
        prs=prs,
        pairs=pairs,
        evaluation_prs=evaluation_prs,
        stats=stats,
    )
