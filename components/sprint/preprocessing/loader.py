"""Loads the three TAWOS sprint CSVs exactly as exported (no cleaning)."""
from pathlib import Path

import pandas as pd

from preprocessing.config import CHANGE_LOGS_FILE, ISSUES_FILE, SPRINTS_FILE, raw_dir

# The MySQL export writes missing values as the text NULL.
NA_VALUES = ["NULL", ""]


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    return pd.read_csv(path, encoding="utf-8-sig", na_values=NA_VALUES, keep_default_na=False, low_memory=False)


def load_raw(cli_path: str | None = None) -> dict[str, pd.DataFrame]:
    """Returns {"issues", "sprints", "change_logs"} DataFrames."""
    folder = raw_dir(cli_path)
    return {
        "issues": _read(folder / ISSUES_FILE),
        "sprints": _read(folder / SPRINTS_FILE),
        "change_logs": _read(folder / CHANGE_LOGS_FILE),
    }


if __name__ == "__main__":
    for name, df in load_raw().items():
        print(f"{name}: {len(df)} rows, {len(df.columns)} columns")
