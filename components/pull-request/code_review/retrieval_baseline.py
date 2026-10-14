
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "splits"

TRAIN_FILE = DATA_DIR / "train.parquet"
VALIDATION_FILE = DATA_DIR / "validation.parquet"

TOP_K = 3


def build_search_text(df):
    """Combine PR title, file path, and code diff into searchable text."""
    title = df["pr_title"].fillna("").astype(str)
    path = df["path"].fillna("").astype(str)
    diff = df["diff_hunk"].fillna("").astype(str)

    return (
        "title: " + title
        + " file: " + path
        + " code: " + diff
    )


def main():
    # 1. Load training and validation datasets
    if not TRAIN_FILE.exists() or not VALIDATION_FILE.exists():
        raise FileNotFoundError(
            "Split files not found. Run split_dataset.py first."
        )

    train_df = pd.read_parquet(TRAIN_FILE)
    validation_df = pd.read_parquet(VALIDATION_FILE)

    if train_df.empty or validation_df.empty:
        raise ValueError("Training or validation dataset is empty.")

    required_columns = [
        "repo_full_name",
        "pr_number",
        "pr_title",
        "path",
        "diff_hunk",
        "body",
    ]

    for name, df in [
        ("training", train_df),
        ("validation", validation_df),
    ]:
        missing = set(required_columns) - set(df.columns)
        if missing:
            raise ValueError(
                f"{name} dataset is missing columns: {sorted(missing)}"
            )

    # 2. Create searchable text using training data only
    train_text = build_search_text(train_df)
    validation_text = build_search_text(validation_df)

    # 3. Convert historical examples into TF-IDF vectors
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        max_features=100_000,
        sublinear_tf=True,
    )

    train_vectors = vectorizer.fit_transform(train_text)
    validation_vectors = vectorizer.transform(validation_text)

    print("TF-IDF index created.")
    print(f"Training examples: {len(train_df):,}")
    print(f"Validation examples: {len(validation_df):,}")

    # 4. Retrieve similar historical review comments
    # Demonstrate the baseline on one validation example.
    query_index = 0
    query = validation_vectors[query_index]

    similarities = cosine_similarity(
        query,
        train_vectors
    ).flatten()

    top_indices = similarities.argsort()[::-1][:TOP_K]

    query_row = validation_df.iloc[query_index]

    print("\n" + "=" * 70)
    print("NEW PULL REQUEST")
    print("=" * 70)
    print(f"Title: {query_row['pr_title']}")
    print(f"File:  {query_row['path']}")
    print(f"Diff:\n{query_row['diff_hunk']}")

    print("\n" + "=" * 70)
    print(f"TOP {TOP_K} HISTORICAL MATCHES")
    print("=" * 70)

    for rank, index in enumerate(top_indices, start=1):
        result = train_df.iloc[index]

        print(f"\nMATCH {rank}")
        print(f"Similarity: {similarities[index]:.4f}")
        print(
            f"Historical PR: "
            f"{result['repo_full_name']}#{result['pr_number']}"
        )
        print(f"Title: {result['pr_title']}")
        print(f"File: {result['path']}")
        print(f"Historical review comment:\n{result['body']}")

    print("\n" + "=" * 70)
    print("Retrieval demonstration completed.")


if __name__ == "__main__":
    main()
