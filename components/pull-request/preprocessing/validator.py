import pandas as pd

from loader import load_parquet
from cleaner import clean_pr_data
from extractor import extract_review_events
from comment_extractor import (
    extract_review_comments,
    extract_thread_replies,
)


def validate_pr_data(df: pd.DataFrame):
    print("\n========== PR DATA VALIDATION ==========")

    print(f"Total PRs: {len(df)}")

    print("\nMissing important PR fields:")

    important_columns = [
        "repo_full_name",
        "pr_number",
        "title",
        "created_at",
        "created_by",
        "state",
    ]

    for column in important_columns:
        missing = df[column].isna().sum()
        empty = (df[column] == "").sum() if df[column].dtype == "object" else 0

        print(
            f"{column}: "
            f"missing={missing}, "
            f"empty={empty}"
        )


def validate_events(events_df: pd.DataFrame):
    print("\n========== EVENT VALIDATION ==========")

    print(f"Total events: {len(events_df)}")

    print("\nEvent counts:")
    print(events_df["event_type"].value_counts())

    print("\nMissing timestamps:")
    print(events_df["timestamp"].isna().sum())

    print("\nMissing event types:")
    print(events_df["event_type"].isna().sum())


def validate_review_comments(review_comments_df: pd.DataFrame):
    print("\n========== REVIEW COMMENT VALIDATION ==========")

    print(f"Total review comments: {len(review_comments_df)}")

    # Empty bodies
    empty_body = (
        review_comments_df["body"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    print(f"Empty comment bodies: {empty_body}")

    # Empty diff hunks
    empty_diff = (
        review_comments_df["diff_hunk"]
        .fillna("")
        .astype(str)
        .eq("")
        .sum()
    )

    print(f"Empty diff hunks: {empty_diff}")

    # Missing reviewers
    missing_reviewers = (
        review_comments_df["reviewer"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    print(f"Missing reviewers: {missing_reviewers}")

    # Duplicate comment IDs
    duplicate_ids = (
        review_comments_df["comment_id"]
        .dropna()
        .duplicated()
        .sum()
    )

    print(f"Duplicate review comment IDs: {duplicate_ids}")

    # Unique reviewers
    unique_reviewers = (
        review_comments_df["reviewer"]
        .dropna()
        .nunique()
    )

    print(f"Unique reviewers: {unique_reviewers}")

    # Unique files
    unique_files = (
        review_comments_df["path"]
        .dropna()
        .nunique()
    )

    print(f"Unique reviewed files: {unique_files}")


def validate_thread_replies(
    review_comments_df: pd.DataFrame,
    thread_replies_df: pd.DataFrame,
):
    print("\n========== THREAD REPLY VALIDATION ==========")

    print(f"Total thread replies: {len(thread_replies_df)}")

    if len(thread_replies_df) == 0:
        print("No thread replies found.")
        return

    # Check whether every parent comment exists
    comment_ids = set(
        review_comments_df["comment_id"]
        .dropna()
        .tolist()
    )

    parent_ids = set(
        thread_replies_df["parent_comment_id"]
        .dropna()
        .tolist()
    )

    orphan_parents = parent_ids - comment_ids

    print(
        f"Replies with missing parent comments: "
        f"{len(orphan_parents)}"
    )

    # Empty reply bodies
    empty_reply_body = (
        thread_replies_df["body"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
        .sum()
    )

    print(f"Empty reply bodies: {empty_reply_body}")

    # Unique reply reviewers
    unique_reply_reviewers = (
        thread_replies_df["reviewer"]
        .dropna()
        .nunique()
    )

    print(
        f"Unique reply reviewers: "
        f"{unique_reply_reviewers}"
    )


if __name__ == "__main__":

    file_path = r"D:\Downloads Folder\train-00001.parquet"

    # -----------------------------
    # Load
    # -----------------------------
    df = load_parquet(file_path)

    # -----------------------------
    # Clean
    # -----------------------------
    cleaned_df = clean_pr_data(df)

    # -----------------------------
    # Extract events
    # -----------------------------
    events_df = extract_review_events(cleaned_df)

    # -----------------------------
    # Extract comments/replies
    # -----------------------------
    review_comments_df = extract_review_comments(events_df)

    thread_replies_df = extract_thread_replies(
        review_comments_df
    )

    # -----------------------------
    # Validate
    # -----------------------------
    validate_pr_data(cleaned_df)

    validate_events(events_df)

    validate_review_comments(
        review_comments_df
    )

    validate_thread_replies(
        review_comments_df,
        thread_replies_df,
    )

    print("\n========== VALIDATION COMPLETE ==========")