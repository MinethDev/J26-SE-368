import os
import sys

import pandas as pd


PREPROCESSING_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "preprocessing"
    )
)

sys.path.insert(0, PREPROCESSING_DIR)


from loader import load_parquet
from cleaner import clean_pr_data
from extractor import extract_review_events
from comment_extractor import extract_review_comments

INPUT_FILE = r"D:\Downloads Folder\train-00001.parquet"

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__),
    "data"
)

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "code_review_dataset.parquet"
)


def build_code_review_dataset(
    review_comments_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Build the initial Code Review research dataset.

    Only review comments with usable diff context are included.
    """

    dataset = review_comments_df.copy()

    # ---------------------------------------------------------
    # 1. Keep only review comments with actual diff context
    # ---------------------------------------------------------
    dataset["diff_hunk"] = (
        dataset["diff_hunk"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    dataset = dataset[
        dataset["diff_hunk"] != ""
    ].copy()

    # ---------------------------------------------------------
    # 2. Normalize review comment text
    # ---------------------------------------------------------
    dataset["body"] = (
        dataset["body"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # ---------------------------------------------------------
    # 3. Normalize file path
    # ---------------------------------------------------------
    dataset["path"] = (
        dataset["path"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # ---------------------------------------------------------
    # 4. Convert comment timestamp
    # ---------------------------------------------------------
    dataset["timestamp"] = pd.to_datetime(
        dataset["timestamp"],
        errors="coerce",
        utc=True
    )

    # ---------------------------------------------------------
    # 5. Select fields needed for Code Review
    # ---------------------------------------------------------
    columns = [
        "repo_full_name",
        "pr_number",
        "pr_title",
        "pr_author",
        "pr_created_at",
        "path",
        "diff_hunk",
        "reviewer",
        "timestamp",
        "body",
        "comment_id",
    ]

    dataset = dataset[columns].reset_index(drop=True)

    return dataset


if __name__ == "__main__":

    print("Loading raw dataset...")

    # ---------------------------------------------------------
    # Load
    # ---------------------------------------------------------
    df = load_parquet(INPUT_FILE)

    # ---------------------------------------------------------
    # Clean
    # ---------------------------------------------------------
    cleaned_df = clean_pr_data(df)

    # ---------------------------------------------------------
    # Extract events
    # ---------------------------------------------------------
    events_df = extract_review_events(cleaned_df)

    # ---------------------------------------------------------
    # Extract review comments
    # ---------------------------------------------------------
    review_comments_df = extract_review_comments(
        events_df
    )

    # ---------------------------------------------------------
    # Build Code Review dataset
    # ---------------------------------------------------------
    code_review_df = build_code_review_dataset(
        review_comments_df
    )

    # ---------------------------------------------------------
    # Create output directory
    # ---------------------------------------------------------
    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # ---------------------------------------------------------
    # Save dataset
    # ---------------------------------------------------------
    code_review_df.to_parquet(
        OUTPUT_FILE,
        index=False
    )

    # ---------------------------------------------------------
    # Report
    # ---------------------------------------------------------
    print("\n========== CODE REVIEW DATASET ==========")

    print(
        f"Original review comments: "
        f"{len(review_comments_df)}"
    )

    print(
        f"Usable Code Review examples: "
        f"{len(code_review_df)}"
    )

    print(
        f"Excluded comments: "
        f"{len(review_comments_df) - len(code_review_df)}"
    )

    print(
        f"\nOutput file:\n{OUTPUT_FILE}"
    )

    print("\nColumns:")
    print(code_review_df.columns.tolist())

    print("\nSample:")
    print(
        code_review_df[
            [
                "pr_number",
                "pr_title",
                "path",
                "diff_hunk",
                "body",
            ]
        ].head(3)
    )