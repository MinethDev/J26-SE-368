"""Raw TAWOS CSVs -> cleaned Parquet files used by every later step.

Run from components/sprint:
    python -m preprocessing.build_clean_dataset [--raw-path "D:\\my data folder"]
"""
import argparse
from pathlib import Path

from preprocessing.cleaner import clean_change_logs, clean_issues, clean_sprints, report
from preprocessing.loader import load_raw

# Generated outputs (ignored by Git).
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "clean"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-path", help="Folder with the three TAWOS CSV files")
    args = parser.parse_args()

    raw = load_raw(args.raw_path)
    issues = clean_issues(raw["issues"])
    sprints = clean_sprints(raw["sprints"])
    change_logs = clean_change_logs(raw["change_logs"])
    report(issues, sprints, change_logs)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in {"issues": issues, "sprints": sprints, "change_logs": change_logs}.items():
        df.to_parquet(OUTPUT_DIR / f"{name}.parquet", index=False)
        print(f"wrote {OUTPUT_DIR / f'{name}.parquet'} ({len(df)} rows)")


if __name__ == "__main__":
    main()
