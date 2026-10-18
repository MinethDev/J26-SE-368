from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


def load_dataset(path: Path) -> pd.DataFrame:
    """Load a supported dataset file."""
    extension = path.suffix.lower()

    if extension == ".csv":
        return pd.read_csv(path)

    if extension == ".arff":
        from scipy.io import arff

        data, _ = arff.loadarff(path)
        return pd.DataFrame(data)

    raise ValueError(f"Unsupported file format: {extension}")


def find_csv_files(path: Path) -> list[Path]:
    """Return all CSV files below a file or directory."""
    if path.is_file():
        return [path] if path.suffix.lower() == ".csv" else []

    if path.is_dir():
        return sorted(
            file
            for file in path.rglob("*")
            if file.is_file() and file.suffix.lower() == ".csv"
        )

    raise FileNotFoundError(f"Dataset path does not exist: {path}")


def inspect(path: Path) -> pd.DataFrame:
    """Print an inspection report for one dataset file."""
    path = Path(path)
    dataframe = load_dataset(path)

    print(f"\n{'=' * 80}")
    print(f"Dataset: {path}")
    print(f"{'=' * 80}")

    print("\n=== SHAPE ===")
    print(f"Rows: {dataframe.shape[0]}")
    print(f"Columns: {dataframe.shape[1]}")

    print("\n=== COLUMNS ===")
    print(dataframe.columns.tolist())

    print("\n=== FIRST 5 ROWS ===")
    print(dataframe.head())

    print("\n=== DATA TYPES ===")
    print(dataframe.dtypes)

    print("\n=== MISSING VALUES ===")
    missing_values = dataframe.isna().sum()
    missing_percent = (missing_values / len(dataframe) * 100).round(2)
    print(
        pd.DataFrame(
            {
                "missing_count": missing_values,
                "missing_percent": missing_percent,
            }
        )
    )

    print("\n=== DUPLICATE ROWS ===")
    print(dataframe.duplicated().sum())

    print("\n=== SUMMARY ===")
    if dataframe.empty:
        print("Dataset is empty; no summary statistics available.")
    else:
        print(dataframe.describe(include="all").T)

    return dataframe


def inspect_all_csvs(path: Path) -> int:
    """Inspect every CSV below path and return the number of failures."""
    csv_files = find_csv_files(path)

    if not csv_files:
        raise FileNotFoundError(f"No CSV files found under: {path}")

    failures = 0

    print(f"Found {len(csv_files)} CSV file(s) under {path}")

    for csv_file in csv_files:
        try:
            inspect(csv_file)
        except (OSError, pd.errors.ParserError, ValueError) as error:
            failures += 1
            print(
                f"\nERROR: Could not inspect '{csv_file}': {error}",
                file=sys.stderr,
            )

    print(f"\nInspected {len(csv_files) - failures}/{len(csv_files)} CSV file(s).")

    return failures


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect one dataset file or all CSV files in a directory."
    )
    parser.add_argument(
        "dataset",
        type=Path,
        help="Path to a CSV file or a directory containing CSV files.",
    )

    arguments = parser.parse_args(argv)
    path = arguments.dataset

    if path.is_file():
        try:
            inspect(path)
        except (OSError, pd.errors.ParserError, ValueError) as error:
            print(f"ERROR: Could not inspect '{path}': {error}", file=sys.stderr)
            return 1
        return 0

    try:
        return 1 if inspect_all_csvs(path) else 0
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())