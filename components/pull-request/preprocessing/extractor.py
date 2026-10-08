import pandas as pd


def extract_review_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract nested review_conversations into a flat DataFrame.
    """

    records = []

    for _, pr in df.iterrows():

        conversations = pr["review_conversations"]

        if conversations is None:
            continue

        for conversation in conversations:

            if conversation is None:
                continue

            records.append({
                "repo_full_name": pr["repo_full_name"],
                "pr_number": pr["pr_number"],
                "pr_title": pr["title"],
                "pr_created_at": pr["created_at"],
                "pr_author": pr["created_by"],

                "event_type": conversation.get("type"),
                "timestamp": conversation.get("timestamp"),
                "reviewer": conversation.get("reviewer"),
                "reviewer_type": conversation.get("reviewer_type"),
                "body": conversation.get("body"),
                "event_title": conversation.get("title"),
                "state": conversation.get("state"),
                "review_id": conversation.get("review_id"),
                "comment_id": conversation.get("comment_id"),
                "path": conversation.get("path"),
                "diff_hunk": conversation.get("diff_hunk"),
                "thread_replies": conversation.get("thread_replies"),
            })

    return pd.DataFrame(records)


if __name__ == "__main__":
    from loader import load_parquet
    from cleaner import clean_pr_data

    file_path = r"D:\Downloads Folder\train-00001.parquet"

    df = load_parquet(file_path)

    cleaned_df = clean_pr_data(df)

    events_df = extract_review_events(cleaned_df)

    print("\nReview event extraction completed.")

    print(f"PR records: {len(cleaned_df)}")
    print(f"Review/conversation events: {len(events_df)}")

    print("\nEvent types:")
    print(events_df["event_type"].value_counts())

    print("\nColumns:")
    print(events_df.columns.tolist())

    print("\nSample:")
    print(
        events_df[
            [
                "pr_number",
                "event_type",
                "reviewer",
                "body",
                "path",
            ]
        ].head()
    )