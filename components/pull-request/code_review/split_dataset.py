
from pathlib import Path

import pandas as pd


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "data" / "code_review_dataset.parquet"
OUTPUT_DIR = BASE_DIR / "data" / "splits"

TRAIN_RATIO = 0.70
VALIDATION_RATIO = 0.15
TEST_RATIO = 0.15

GROUP_COLUMNS = ["repo_full_name", "pr_number"]
DATE_COLUMN = "pr_created_at"


def main():
    # 1. Validate the input dataset
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {INPUT_FILE}"
        )

    if abs(
        TRAIN_RATIO + VALIDATION_RATIO + TEST_RATIO - 1.0
    ) > 1e-9:
        raise ValueError("Split ratios must add up to 1.0")

    df = pd.read_parquet(INPUT_FILE)

    required_columns = GROUP_COLUMNS + [DATE_COLUMN]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    if df.empty:
        raise ValueError("The dataset is empty.")

    # 2. Normalize dates and validate PR identifiers
    df[DATE_COLUMN] = pd.to_datetime(
        df[DATE_COLUMN],
        utc=True,
        errors="coerce"
    )

    if df[DATE_COLUMN].isna().any():
        raise ValueError(
            "Some PR creation dates are missing or invalid. "
            "Inspect and resolve them before splitting."
        )

    if df[GROUP_COLUMNS].isna().any().any():
        raise ValueError(
            "Some repository names or PR numbers are missing."
        )

    # 3. Build one record per PR
    prs = (
        df[GROUP_COLUMNS + [DATE_COLUMN]]
        .drop_duplicates(subset=GROUP_COLUMNS)
        .sort_values(
            [DATE_COLUMN] + GROUP_COLUMNS,
            kind="mergesort"
        )
        .reset_index(drop=True)
    )

    total_prs = len(prs)

    if total_prs < 3:
        raise ValueError(
            "At least 3 unique PRs are required for splitting."
        )

    # 4. Split chronologically by PR, not by comment
    train_end = int(total_prs * TRAIN_RATIO)
    validation_end = int(
        total_prs * (TRAIN_RATIO + VALIDATION_RATIO)
    )

    train_prs = prs.iloc[:train_end]
    validation_prs = prs.iloc[train_end:validation_end]
    test_prs = prs.iloc[validation_end:]

    split_groups = {
        "train": train_prs,
        "validation": validation_prs,
        "test": test_prs,
    }

    # 5. Assign every comment to its PR's split
    df["split"] = ""

    for split_name, split_prs in split_groups.items():
        keys = pd.MultiIndex.from_frame(
            split_prs[GROUP_COLUMNS]
        )

        row_keys = pd.MultiIndex.from_frame(
            df[GROUP_COLUMNS]
        )

        df.loc[row_keys.isin(keys), "split"] = split_name

    if (df["split"] == "").any():
        raise RuntimeError(
            "Some examples were not assigned to a split."
        )

    # 6. Verify there is no PR overlap between splits
    pr_sets = {
        name: set(
            map(
                tuple,
                split_df[GROUP_COLUMNS].drop_duplicates().to_numpy()
            )
        )
        for name, split_df in (
            (name, df[df["split"] == name])
            for name in split_groups
        )
    }

    if (
        pr_sets["train"] & pr_sets["validation"]
        or pr_sets["train"] & pr_sets["test"]
        or pr_sets["validation"] & pr_sets["test"]
    ):
        raise RuntimeError(
            "PR leakage detected: a PR appears in multiple splits."
        )

    # 7. Save split files
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for split_name in split_groups:
        split_df = df[df["split"] == split_name].drop(
            columns=["split"]
        )

        output_file = OUTPUT_DIR / f"{split_name}.parquet"
        split_df.to_parquet(output_file, index=False)

    # 8. Print statistics
    print("\nCODE REVIEW DATASET SPLIT")
    print("=" * 55)
    print(f"Total examples: {len(df):,}")
    print(f"Unique PRs:     {total_prs:,}")

    for split_name in split_groups:
        split_df = df[df["split"] == split_name]

        print(f"\n{split_name.upper()}")
        print(f"  Examples: {len(split_df):,}")
        print(
            "  Unique PRs:",
            split_df[GROUP_COLUMNS].drop_duplicates().shape[0]
        )
        print(f"  Output: {OUTPUT_DIR / (split_name + '.parquet')}")

        print(
            "  Date range:",
            split_df[DATE_COLUMN].min(),
            "to",
            split_df[DATE_COLUMN].max()
        )

    print("\nLeakage check: PASSED")
    print("Dataset splitting completed successfully.")


if __name__ == "__main__":
    main()
