"""Team productivity per sprint: velocity, throughput, say/do ratio and carry-over.

Work is measured in story points when the sprint's commitment has points, otherwise in issues,
the same rule the health score uses. Team trends only look at sprints that had finished before
the moment asked about, so they are safe to use live and as model features.
"""
import numpy as np
import pandas as pd

from productivity.config import OVERCOMMIT_RATIO, TREND_WINDOW, VELOCITY_WINDOW


def _final_snapshots(snapshots: pd.DataFrame) -> pd.DataFrame:
    snapshots = snapshots[snapshots["committed_issues"] > 0]
    return snapshots.sort_values("day").groupby("sprint_id").tail(1).set_index("sprint_id")


def sprint_velocity(snapshots: pd.DataFrame, sprints: pd.DataFrame) -> pd.DataFrame:
    """One row per finished sprint."""
    final = _final_snapshots(snapshots)
    meta = sprints.set_index("sprint_id").reindex(final.index)
    points = final["committed_points"] > 0
    pick = lambda pts, iss: np.where(points, final[pts], final[iss]).astype(float)
    committed = pick("committed_points", "committed_issues")
    delivered = pick("committed_done_points", "committed_done_issues")
    days = meta["planned_days"].clip(lower=1)
    out = pd.DataFrame({
        "project_id": final["project_id"],
        "start_date": meta["start_date"],
        "end_date": meta["end_date"],
        "unit": np.where(points, "points", "issues"),
        "committed": committed,
        "delivered": delivered,  # from the original commitment
        "completed": pick("done_points", "done_issues"),  # everything finished, added work included
        "completed_issues": final["done_issues"].astype(int),
        "throughput_per_day": final["done_issues"] / days,
        "carry_over_issues": (final["committed_issues"] - final["committed_done_issues"]).astype(int),
        "added": pick("added_points", "added_issues"),
    }, index=final.index)
    out["say_do"] = np.where(out["committed"] > 0, out["delivered"] / out["committed"], np.nan)
    return out.sort_values(["project_id", "end_date"])


def team_trend(velocity: pd.DataFrame, project_id, before) -> dict:
    """What the team's finished sprints (ended before `before`) say about its pace."""
    past = velocity[(velocity["project_id"] == project_id) & (velocity["end_date"] < before)].sort_values("end_date")
    recent = past.tail(VELOCITY_WINDOW)
    trend_rows = past.tail(TREND_WINDOW)["completed"].to_numpy()
    slope = float(np.polyfit(np.arange(len(trend_rows)), trend_rows, 1)[0]) if len(trend_rows) >= 3 else np.nan
    return {
        "sprints_seen": len(past),
        "velocity": float(recent["completed"].mean()) if len(recent) else np.nan,
        "velocity_trend": slope,  # change in completed work per sprint
        "recent_say_do": float(recent["say_do"].mean()) if len(recent) else np.nan,
        "recent_throughput_per_day": float(recent["throughput_per_day"].mean()) if len(recent) else np.nan,
    }


def overcommitment(committed: float, velocity: float) -> dict:
    """How the new commitment compares with what the team has recently completed."""
    if not velocity or np.isnan(velocity):
        return {"ratio": np.nan, "overcommitted": False}
    ratio = committed / velocity
    return {"ratio": round(float(ratio), 2), "overcommitted": bool(ratio > OVERCOMMIT_RATIO)}
