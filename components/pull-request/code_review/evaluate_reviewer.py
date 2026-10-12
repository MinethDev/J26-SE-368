
import json
import random
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = (
    PROJECT_ROOT
    / "components"
    / "pull-request"
    / "code_review"
    / "data"
)

DATASET_PATH = DATA_DIR / "splits" / "validation.parquet"

SAMPLE_SIZE = 30
RANDOM_SEED = 42

# Generate a different output file for each run.
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_PATH = DATA_DIR / f"evaluation_results_{RUN_TIMESTAMP}.csv"


def select_sample(df, sample_size, random_seed):
    """Select reproducible examples from distinct pull requests."""

    # A pull request is identified by repository and PR number.
    pr_keys = ["repo_full_name", "pr_number"]

    # Keep one comment per pull request to improve PR-level diversity.
    unique_prs = df[pr_keys].drop_duplicates()

    if len(unique_prs) < sample_size:
        print(
            f"Warning: Only {len(unique_prs)} unique pull requests "
            f"are available for a sample of {sample_size}."
        )

    selected_prs = unique_prs.sample(
        n=min(sample_size, len(unique_prs)),
        random_state=random_seed,
    )

    # Randomly select one available comment for each selected PR.
    selected_rows = []

    for _, pr in selected_prs.iterrows():
        matching_rows = df[
            (df["repo_full_name"] == pr["repo_full_name"])
            & (df["pr_number"] == pr["pr_number"])
        ]

        selected_rows.append(
            matching_rows.sample(n=1, random_state=random_seed)
        )

    if not selected_rows:
        return df.iloc[0:0].copy()

    return pd.concat(selected_rows).reset_index(drop=True)


def main():
    """Run a small, reproducible AI code-review evaluation."""

    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}")
        return

    # Import the existing reviewer.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    try:
        from ai_reviewer import review_code
    except ImportError as error:
        print(f"Could not import ai_reviewer.py: {error}")
        return

    df = pd.read_parquet(DATASET_PATH)

    required_columns = {
        "repo_full_name",
        "pr_number",
        "pr_title",
        "path",
        "diff_hunk",
        "body",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        print(f"Dataset is missing columns: {sorted(missing_columns)}")
        return

    sample = select_sample(
        df=df,
        sample_size=SAMPLE_SIZE,
        random_seed=RANDOM_SEED,
    )

    if sample.empty:
        print("No examples available for evaluation.")
        return

    results = []

    print("DEVINTEL - AI CODE REVIEW EVALUATION")
    print("=" * 60)
    print(f"Validation comments available: {len(df)}")
    print(
        "Unique pull requests available: "
        f"{df[['repo_full_name', 'pr_number']].drop_duplicates().shape[0]}"
    )
    print(f"Examples selected: {len(sample)}")
    print(f"Random seed: {RANDOM_SEED}")
    print("Selection: one comment from each distinct pull request")

    for index, (_, row) in enumerate(sample.iterrows(), start=1):
        repo = str(row["repo_full_name"])
        pr_number = row["pr_number"]
        title = str(row["pr_title"])
        file_path = str(row["path"])
        diff = str(row["diff_hunk"])
        human_comment = str(row["body"])

        print(f"\nProcessing example {index}/{len(sample)}")
        print(f"PR: {repo}#{pr_number}")
        print(f"Title: {title}")
        print(f"File: {file_path}")

        try:
            review = review_code(
                pr_title=title,
                file_path=file_path,
                code_diff=diff,
            )

            findings = review["findings"]
            status = "success"
            error_message = ""

            print(f"AI findings: {len(findings)}")

        except Exception as error:
            print(f"Review failed: {error}")
            findings = []
            status = "error"
            error_message = str(error)

        results.append(
            {
                "repo_full_name": repo,
                "pr_number": pr_number,
                "pr_title": title,
                "file_path": file_path,
                "human_review_comment": human_comment,
                "ai_findings_json": json.dumps(
                    findings,
                    ensure_ascii=False,
                ),
                "finding_count": len(findings),
                "status": status,
                "error": error_message,
                "random_seed": RANDOM_SEED,
            }
        )

    # Do not overwrite an existing results file.
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_PATH.exists():
        raise FileExistsError(
            f"Output file already exists: {OUTPUT_PATH}"
        )

    results_df = pd.DataFrame(results)
    results_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    successful = int((results_df["status"] == "success").sum())
    failed = int((results_df["status"] == "error").sum())
    no_findings = int(
        (
            (results_df["status"] == "success")
            & (results_df["finding_count"] == 0)
        ).sum()
    )

    print("\n" + "=" * 60)
    print("EVALUATION RUN COMPLETE")
    print(f"Total examples: {len(results_df)}")
    print(f"Successful reviews: {successful}")
    print(f"Failed reviews: {failed}")
    print(f"Successful reviews with no findings: {no_findings}")
    print(f"Results saved to: {OUTPUT_PATH}")

    print(
        "\nNote: These counts measure execution and generated findings, "
        "not bug-detection accuracy."
    )


if __name__ == "__main__":
    main()
