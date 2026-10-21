from pathlib import Path
import argparse
import re

import pandas as pd


FILE_PATTERN = re.compile(
    r"^(?P<project>.+)-(?P<version>\d+(?:\.\d+)*)_ground-truth-files_dataset\.csv$"
)


def parse_dataset_name(path: Path):
    match = FILE_PATTERN.match(path.name)

    if match:
        return match.group("project"), match.group("version")

    return path.stem, "unknown"


def summarize_file(path: Path):
    df = pd.read_csv(path)

    project, version = parse_dataset_name(path)

    rows = len(df)

    if rows == 0:
        return {
            "project": project,
            "version": version,
            "rows": 0,
            "buggy": 0,
            "clean": 0,
            "bug_percent": None,
            "status": "EMPTY",
            "file": path.name,
        }

    if "Bug" not in df.columns:
        return {
            "project": project,
            "version": version,
            "rows": rows,
            "buggy": None,
            "clean": None,
            "bug_percent": None,
            "status": "NO_BUG_COLUMN",
            "file": path.name,
        }

    bug = df["Bug"]

    # Normalize boolean-like values if necessary.
    if bug.dtype != bool:
        bug = (
            bug.astype(str)
            .str.strip()
            .str.lower()
            .map({
                "true": True,
                "false": False,
                "1": True,
                "0": False,
            })
        )

    valid_bug = bug.dropna()

    buggy = int(valid_bug.sum())
    clean = int((~valid_bug).sum())
    valid_rows = len(valid_bug)

    bug_percent = (buggy / valid_rows * 100) if valid_rows else None

    if valid_rows == 0:
        status = "INVALID_LABELS"
    elif buggy == 0 or clean == 0:
        status = "SINGLE_CLASS"
    elif min(buggy, clean) / valid_rows < 0.05:
        status = "SEVERE_IMBALANCE"
    else:
        status = "OK"

    return {
        "project": project,
        "version": version,
        "rows": rows,
        "buggy": buggy,
        "clean": clean,
        "bug_percent": round(bug_percent, 2) if bug_percent is not None else None,
        "status": status,
        "file": path.name,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Summarize benchmark defect datasets."
    )
    parser.add_argument(
        "dataset_dir",
        type=Path,
        help="Directory containing benchmark CSV files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/jureczko_dataset_summary.csv"),
        help="Output CSV path.",
    )

    args = parser.parse_args()

    csv_files = sorted(args.dataset_dir.rglob("*.csv"))

    if not csv_files:
        raise SystemExit(f"No CSV files found under {args.dataset_dir}")

    summaries = []

    for path in csv_files:
        try:
            summaries.append(summarize_file(path))
        except Exception as exc:
            project, version = parse_dataset_name(path)

            summaries.append({
                "project": project,
                "version": version,
                "rows": None,
                "buggy": None,
                "clean": None,
                "bug_percent": None,
                "status": f"ERROR: {exc}",
                "file": path.name,
            })

    summary_df = pd.DataFrame(summaries)

    print("\n=== DATASET RELEASE SUMMARY ===\n")

    display_columns = [
        "project",
        "version",
        "rows",
        "buggy",
        "clean",
        "bug_percent",
        "status",
    ]

    print(summary_df[display_columns].to_string(index=False))

    usable = summary_df[
        ~summary_df["status"].isin(
            ["EMPTY", "SINGLE_CLASS", "INVALID_LABELS"]
        )
        & ~summary_df["status"].astype(str).str.startswith("ERROR")
    ]

    print("\n=== OVERALL SUMMARY ===")
    print(f"CSV files found:        {len(summary_df)}")
    print(f"Usable releases:        {len(usable)}")
    print(f"Empty releases:         {(summary_df['status'] == 'EMPTY').sum()}")
    print(f"Single-class releases:  {(summary_df['status'] == 'SINGLE_CLASS').sum()}")
    print(
        "Severe imbalance:       "
        f"{(summary_df['status'] == 'SEVERE_IMBALANCE').sum()}"
    )

    if not usable.empty:
        total_rows = int(usable["rows"].sum())
        total_buggy = int(usable["buggy"].sum())
        total_clean = int(usable["clean"].sum())

        print(f"\nUsable observations:    {total_rows}")
        print(f"Buggy observations:     {total_buggy}")
        print(f"Clean observations:     {total_clean}")

        if total_rows:
            print(
                f"Overall buggy %:        "
                f"{total_buggy / total_rows * 100:.2f}%"
            )

    print("\n=== FLAGGED RELEASES ===\n")

    flagged = summary_df[summary_df["status"] != "OK"]

    if flagged.empty:
        print("None")
    else:
        print(flagged[display_columns].to_string(index=False))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(args.output, index=False)

    print(f"\nSummary written to: {args.output}")


if __name__ == "__main__":
    main()