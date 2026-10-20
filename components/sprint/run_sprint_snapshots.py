"""Builds the daily sprint snapshots used by sprint health and risk prediction.

Run from components/sprint, after preprocessing.build_clean_dataset:
    python run_sprint_snapshots.py
"""
from pathlib import Path

import pandas as pd

from sprint_health.snapshot import SprintHistory, build_daily_snapshots

DATA_DIR = Path(__file__).resolve().parent / "data"


def main() -> None:
    clean = DATA_DIR / "clean"
    history = SprintHistory(
        pd.read_parquet(clean / "issues.parquet"),
        pd.read_parquet(clean / "sprints.parquet"),
        pd.read_parquet(clean / "change_logs.parquet"),
    )
    print("Status id -> name learned from the data (check these look right):")
    for status_id, name in sorted(history.status_map.items(), key=lambda kv: float(kv[0])):
        print(f"  {status_id:>6} -> {name}")

    snapshots = build_daily_snapshots(history)
    out = DATA_DIR / "snapshots"
    out.mkdir(parents=True, exist_ok=True)
    snapshots.to_parquet(out / "sprint_days.parquet", index=False)

    final = snapshots.sort_values("day").groupby("sprint_id").tail(1)
    ratio = (final["committed_done_points"] / final["committed_points"]).where(final["committed_points"] > 0)
    print(f"\nwrote {out / 'sprint_days.parquet'} ({len(snapshots)} rows, {snapshots['sprint_id'].nunique()} sprints)")
    print("Sprints with nothing committed after the 24h grace period:", int((final["committed_issues"] == 0).sum()))
    print("Issues added after start (median per sprint):", final["added_issues"].median())
    print("Committed points delivered by the last day (committed done / committed):")
    print(ratio.describe().round(2).to_string())


if __name__ == "__main__":
    main()
