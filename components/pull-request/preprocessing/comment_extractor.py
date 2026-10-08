import pandas as pd


def extract_review_comments(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract review_comment events into a clean DataFrame.
    """

    review_comments = events_df[
        events_df["event_type"] == "review_comment"
    ].copy()

    columns = [
        "repo_full_name",
        "pr_number",
        "pr_title",
        "pr_created_at",
        "pr_author",
        "timestamp",
        "reviewer",
        "reviewer_type",
        "body",
        "comment_id",
        "path",
        "diff_hunk",
        "thread_replies",
    ]

    return review_comments[columns].reset_index(drop=True)


def extract_thread_replies(review_comments_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract nested thread replies into individual records.
    """

    records = []

    for _, comment in review_comments_df.iterrows():

        replies = comment["thread_replies"]

        if replies is None:
            continue

        for reply in replies:

            if reply is None:
                continue

            records.append({
                "repo_full_name": comment["repo_full_name"],
                "pr_number": comment["pr_number"],
                "parent_comment_id": comment["comment_id"],
                "reviewer": reply.get("reviewer"),
                "reviewer_type": reply.get("reviewer_type"),
                "body": reply.get("body"),
                "comment_id": reply.get("comment_id"),
            })

    return pd.DataFrame(records)


if __name__ == "__main__":
    from loader import load_parquet
    from cleaner import clean_pr_data
    from extractor import extract_review_events

    file_path = r"D:\Downloads Folder\train-00001.parquet"

    # Load
    df = load_parquet(file_path)

    # Clean
    cleaned_df = clean_pr_data(df)

    # Extract all events
    events_df = extract_review_events(cleaned_df)

    # Extract review comments
    review_comments_df = extract_review_comments(events_df)

    # Extract thread replies
    thread_replies_df = extract_thread_replies(review_comments_df)

    print("\nReview comment extraction completed.")

    print(f"Total review comments: {len(review_comments_df)}")
    print(f"Total thread replies: {len(thread_replies_df)}")

    print("\nReview comment columns:")
    print(review_comments_df.columns.tolist())

    print("\nThread reply columns:")
    print(thread_replies_df.columns.tolist())

    print("\nReview comment sample:")
    print(
        review_comments_df[
            [
                "pr_number",
                "comment_id",
                "reviewer",
                "path",
                "body",
            ]
        ].head()
    )

    print("\nThread reply sample:")

    if len(thread_replies_df) > 0:
        print(thread_replies_df.head())
    else:
        print("No thread replies found.")