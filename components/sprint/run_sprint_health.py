"""Scores every sprint snapshot and checks how well the health score warns about missed sprints.

Run from components/sprint, after run_sprint_snapshots.py:
    python run_sprint_health.py
"""
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score

from sprint_health.config import CHECKPOINTS, MISSED_THRESHOLD
from sprint_health.health import assess, delivered_share

DATA_DIR = Path(__file__).resolve().parent / "data"


def main() -> None:
    snapshots = pd.read_parquet(DATA_DIR / "snapshots" / "sprint_days.parquet")
    snapshots = snapshots[snapshots["committed_issues"] > 0]  # sprints with no real commitment

    results = [assess(row) for row in snapshots.to_dict("records")]
    snapshots = snapshots.assign(health_score=[r["score"] for r in results], health_band=[r["band"] for r in results])

    final = snapshots.sort_values("day").groupby("sprint_id").tail(1).set_index("sprint_id")
    delivered = final.apply(lambda r: delivered_share(r.to_dict()), axis=1)
    missed = (delivered < MISSED_THRESHOLD).rename("missed")
    print(f"Sprints: {len(final)}, missed their commitment (<{MISSED_THRESHOLD:.0%} delivered): {missed.mean():.0%}")

    print("\nHow well the health score warns early (AUC: 0.5 = no better than chance, 1.0 = perfect):")
    for cp in CHECKPOINTS:
        # The first snapshot at or after the checkpoint, per sprint.
        at = snapshots[snapshots["elapsed_fraction"] >= cp].sort_values("day").groupby("sprint_id").head(1)
        at = at.join(missed, on="sprint_id")
        auc = roc_auc_score(at["missed"], -at["health_score"])
        bands = at.groupby("health_band")["missed"].agg(["size", "mean"]).round(2)
        print(f"\n  {cp:.0%} through the sprint: AUC {auc:.3f}")
        print("  band       sprints  share that missed")
        for band, r in bands.iterrows():
            print(f"  {band:<10} {int(r['size']):>7}  {r['mean']:.0%}")

    out = DATA_DIR / "health"
    out.mkdir(parents=True, exist_ok=True)
    snapshots.to_parquet(out / "sprint_health.parquet", index=False)
    print(f"\nwrote {out / 'sprint_health.parquet'} ({len(snapshots)} rows)")


if __name__ == "__main__":
    main()
