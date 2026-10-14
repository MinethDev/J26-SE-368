import pandas as pd


TEXT_COLUMNS = [
    "repo_full_name",
    "title",
    "repo_url",
    "pr_url",
    "created_by",
    "created_by_type",
    "state",
    "merged_by",
    "merged_by_type",
]


DATETIME_COLUMNS = [
    "created_at",
    "closed_at",
    "merged_at",
]


NUMERIC_COLUMNS = [
    "pr_number",
    "additions",
    "deletions",
]


def clean_pr_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean top-level Pull Request data.

    Nested review conversations are intentionally left untouched
    and will be processed separately.
    """

    df = df.copy()

    # ---------------------------------------------------------
    # 1. Normalize text columns
    # ---------------------------------------------------------
    for column in TEXT_COLUMNS:
        if column in df.columns:
            df[column] = df[column].fillna("").astype(str).str.strip()

    # ---------------------------------------------------------
    # 2. Convert datetime columns
    # ---------------------------------------------------------
    for column in DATETIME_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_datetime(
                df[column],
                errors="coerce",
                utc=True
            )

    # ---------------------------------------------------------
    # 3. Convert numeric columns
    # ---------------------------------------------------------
    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    # ---------------------------------------------------------
    # 4. Create total changes
    # ---------------------------------------------------------
    df["total_changes"] = (
        df["additions"].fillna(0)
        + df["deletions"].fillna(0)
    )

    # ---------------------------------------------------------
    # 5. Normalize PR state
    # ---------------------------------------------------------
    if "state" in df.columns:
        df["state"] = (
            df["state"]
            .str.lower()
            .str.strip()
        )

    return df


if __name__ == "__main__":
    from loader import load_parquet

    file_path = r"D:\Downloads Folder\train-00001.parquet"

    df = load_parquet(file_path)

    cleaned_df = clean_pr_data(df)

    print("\nCleaning completed.")

    print("\nData types:")
    print(cleaned_df.dtypes)

    print("\nPR state distribution:")
    print(cleaned_df["state"].value_counts(dropna=False))

    print("\nSample:")
    print(
        cleaned_df[
            [
                "repo_full_name",
                "pr_number",
                "title",
                "additions",
                "deletions",
                "total_changes",
                "state",
            ]
        ].head()
    )