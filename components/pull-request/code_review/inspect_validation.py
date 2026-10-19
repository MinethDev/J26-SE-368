
from pathlib import Path

import pandas as pd


DATASET_PATH = Path(
    "components/pull-request/code_review/data/splits/validation.parquet"
)


def main():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}")
        return

    df = pd.read_parquet(DATASET_PATH)

    print("VALIDATION DATASET SUMMARY")
    print("=" * 60)
    print(f"Total examples: {len(df)}")
    print(f"Unique pull requests: {df['pr_number'].nunique()}")
    print(f"Unique repositories: {df['repo_full_name'].nunique()}")
    print()

    print("SAMPLE HUMAN REVIEW COMMENTS")
    print("=" * 60)

    sample = df.sample(n=min(10, len(df)), random_state=42)

    for number, (_, row) in enumerate(sample.iterrows(), start=1):
        print(f"\nExample {number}")
        print("-" * 40)
        print(f"Repository: {row['repo_full_name']}")
        print(f"PR title: {row['pr_title']}")
        print(f"File: {row['path']}")
        print(f"Human review comment: {row['body']}")
        print(f"Code diff:\n{row['diff_hunk'][:700]}")

    print("\nInspection complete.")


if __name__ == "__main__":
    main()
