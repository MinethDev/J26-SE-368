"""One training row per (sprint, checkpoint): what was known at that moment -> did the sprint miss?

Leakage controls:
  - in-sprint features come from the snapshot at the checkpoint (only changes made up to then);
  - team-history features use only sprints of the same project that had ENDED before the checkpoint.
"""
import numpy as np
import pandas as pd

from sprint_health.config import CHECKPOINTS, MISSED_THRESHOLD
from sprint_health.health import assess, delivered_share

FEATURES = [
    "elapsed_fraction",
    "planned_days",
    "committed_issues",
    "committed_points",
    "delivered_so_far",
    "burndown_gap",
    "scope_added",
    "scope_removed",
    "unestimated",
    "todo_share",
    "in_progress_share",
    "health_score",
    "team_prev_sprints",
    "team_prev_delivered_mean",
    "team_prev_missed_rate",
]


def _share(part, whole):
    return part / whole if whole else 0.0


def sprint_outcomes(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Per sprint: final delivered share and whether it missed the commitment."""
    final = snapshots.sort_values("day").groupby("sprint_id").tail(1).set_index("sprint_id")
    delivered = final.apply(lambda r: delivered_share(r.to_dict()), axis=1).astype(float)
    return pd.DataFrame({"delivered": delivered, "missed": (delivered < MISSED_THRESHOLD).astype(int)})


def _team_history(sprints: pd.DataFrame, outcomes: pd.DataFrame, sprint_id, at) -> dict:
    me = sprints.loc[sprint_id]
    past = sprints[(sprints["project_id"] == me["project_id"]) & (sprints["end_date"] < at) & (sprints.index != sprint_id)]
    past = outcomes.reindex(past.index).dropna()
    return {
        "team_prev_sprints": len(past),
        "team_prev_delivered_mean": past["delivered"].mean() if len(past) else np.nan,
        "team_prev_missed_rate": past["missed"].mean() if len(past) else np.nan,
    }


def build_dataset(snapshots: pd.DataFrame, sprints: pd.DataFrame) -> pd.DataFrame:
    snapshots = snapshots[snapshots["committed_issues"] > 0]
    sprints = sprints.set_index("sprint_id")
    outcomes = sprint_outcomes(snapshots)
    rows = []
    for cp in CHECKPOINTS:
        at_cp = snapshots[snapshots["elapsed_fraction"] >= cp].sort_values("day").groupby("sprint_id").head(1)
        for s in at_cp.to_dict("records"):
            health = assess(s)
            sig = health["signals"]
            row = {
                "sprint_id": s["sprint_id"],
                "project_id": s["project_id"],
                "checkpoint": cp,
                "at": s["at"],
                "start_date": sprints.loc[s["sprint_id"], "start_date"],
                "elapsed_fraction": s["elapsed_fraction"],
                "planned_days": sprints.loc[s["sprint_id"], "planned_days"],
                "committed_issues": s["committed_issues"],
                "committed_points": s["committed_points"],
                "delivered_so_far": delivered_share(s),
                "burndown_gap": sig["burndown_gap"],
                "scope_added": sig["scope_added"],
                "scope_removed": sig["scope_removed"],
                "unestimated": sig["unestimated"],
                "todo_share": _share(s["todo_issues"], s["issues"]),
                "in_progress_share": _share(s["in_progress_issues"], s["issues"]),
                "health_score": health["score"],
                **_team_history(sprints, outcomes, s["sprint_id"], s["at"]),
                "missed": outcomes.loc[s["sprint_id"], "missed"],
            }
            rows.append(row)
    return pd.DataFrame(rows)
