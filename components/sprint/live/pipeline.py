"""The live sprint pipeline behind the sprint service:

    platform Jira data -> snapshots (same code as research) -> health score -> risk model + SHAP
    -> velocity and workload -> recommendations -> sprint report

Returns plain dicts; service/analysis.py turns them into platform insights.
"""
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from live.context import PROJECT_ID, LiveHistory, build_tables, to_time
from productivity.velocity import overcommitment, sprint_velocity, team_trend
from productivity.workload import team_workload
from recommendations.interventions import recommend
from recommendations.report import sprint_report
from risk_prediction.config import MODEL_PATH
from risk_prediction.dataset import _share, _team_history
from risk_prediction.explain import explain_row
from sprint_health.config import MISSED_THRESHOLD
from sprint_health.health import assess, delivered_share


@lru_cache(maxsize=1)
def load_model() -> dict | None:
    """The trained risk model (run_risk_prediction.py final). None when it hasn't been trained on
    this machine: data/ is not in Git, so teammates and CI run on the health score only."""
    path = Path(os.getenv("DEVINTEL_SPRINT_MODEL", MODEL_PATH))
    if not path.exists():
        return None
    import joblib
    return joblib.load(path)


def _state(history: LiveHistory, sprint_id: int, t: pd.Timestamp) -> dict:
    """One snapshot row, in the same shape as data/snapshots/sprint_days.parquet."""
    sprint = history.sprints.loc[sprint_id]
    commit_t = history.commitment_time(sprint_id)
    committed = history.committed_at_start(sprint_id) if t >= commit_t else None
    snap = history.snapshot(sprint_id, t, committed, count_removed=t >= commit_t)
    committed = committed if committed is not None else {
        i for i in history.candidates[sprint_id] if history.in_sprint(i, sprint["jira_sprint_id"], t)}
    commit_at = min(t, commit_t)
    elapsed = (t - sprint["start_date"]) / (sprint["end_date"] - sprint["start_date"])
    return {
        "sprint_id": sprint_id, "project_id": PROJECT_ID, "day": int((t - sprint["start_date"]).days), "at": t,
        "elapsed_fraction": round(float(np.clip(elapsed, 0, 1)), 4),
        "committed_issues": len(committed),
        "committed_points": float(sum(history.story_points(i, commit_at) or 0 for i in committed)),
        **snap,
    }


def _closed_outcomes(history: LiveHistory, now: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Final state and outcome of every sprint that has ended (the team's history)."""
    finals = [_state(history, sid, s["end_date"]) for sid, s in history.sprints.iterrows() if s["end_date"] < now]
    finals = pd.DataFrame(finals)
    if finals.empty:
        return finals, pd.DataFrame(columns=["delivered", "missed"])
    finals = finals[finals["committed_issues"] > 0]
    delivered = finals.set_index("sprint_id").apply(lambda r: delivered_share(r.to_dict()), axis=1).astype(float)
    return finals, pd.DataFrame({"delivered": delivered, "missed": (delivered < MISSED_THRESHOLD).astype(int)})


def _features(s: dict, health: dict, sprints: pd.DataFrame, outcomes: pd.DataFrame) -> dict:
    """The model's feature row: same definitions as risk_prediction.dataset.build_dataset."""
    sig = health["signals"]
    return {
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
        "issues": s["issues"],
    }


def _velocity(finals: pd.DataFrame, sprints: pd.DataFrame, s: dict) -> dict | None:
    if finals.empty:
        return None
    velocity = sprint_velocity(finals, sprints)
    unit = "points" if s["committed_points"] > 0 else "issues"
    trend = team_trend(velocity[velocity["unit"] == unit], PROJECT_ID, sprints.set_index("sprint_id").loc[s["sprint_id"], "start_date"])
    committed = s["committed_points"] if unit == "points" else s["committed_issues"]
    return {**overcommitment(committed, trend["velocity"]), **trend, "committed": committed, "unit": unit}


def _burndown(history: LiveHistory, sprint_id: int, now: pd.Timestamp) -> list[dict]:
    sprint = history.sprints.loc[sprint_id]
    days = max(int(np.ceil((sprint["end_date"] - sprint["start_date"]).total_seconds() / 86400)), 1)
    rows = []
    for day in range(days + 1):
        t = min(sprint["start_date"] + pd.Timedelta(days=day), sprint["end_date"])
        if t > now:
            break
        s = _state(history, sprint_id, t)
        unit = "points" if s["committed_points"] > 0 else "issues"
        committed = s[f"committed_{unit}"]
        rows.append({"day": day, "date": t.isoformat(), "unit": unit,
                     "remaining": committed - s[f"committed_done_{unit}"],
                     "ideal": round(committed * (1 - day / days), 2),
                     "scope": s[unit], "done": s[f"done_{unit}"]})
    return rows


def analyze_sprints(context: dict, planning_avg_points: float | None = None) -> list[dict]:
    """One result per active sprint that has dates. `context.asOf` (ISO time) overrides 'now' for tests."""
    now = to_time(context.get("asOf")) or pd.Timestamp.now(tz="UTC").tz_localize(None)
    issues, sprints, logs, lookup = build_tables(context)
    if sprints.empty:
        return []
    history = LiveHistory(issues, sprints, logs, now)
    finals, outcomes = _closed_outcomes(history, now)
    saved = load_model()
    results = []
    for sprint_id, sprint in history.sprints.iterrows():
        if sprint["sprint_state"] != "active" or not (sprint["start_date"] <= now):
            continue
        t = min(now, sprint["end_date"])
        s = _state(history, sprint_id, t)
        health = assess(s)
        members = [i for i in history.candidates[sprint_id] if history.in_sprint(i, sprint["jira_sprint_id"], t)]
        workload = team_workload([{"assignee": lookup["issue"][i].get("assignee"),
                                   "story_points": lookup["issue"][i].get("storyPoints"),
                                   "status_category": lookup["issue"][i].get("statusCategory")} for i in members])
        result = {"sprint": lookup["sprint"][sprint_id], "snapshot": s, "health": health, "workload": workload,
                  "burndown": _burndown(history, sprint_id, t), "has_changelog": not logs.empty,
                  "closed_sprints_seen": len(outcomes)}
        if s["committed_issues"] == 0:
            results.append({**result, "risk": None, "recommendations": None, "report": None})
            continue
        features = _features(s, health, sprints.set_index("sprint_id"), outcomes)
        velocity = _velocity(finals, sprints, s)
        if saved:
            row = pd.Series({f: features[f] for f in saved["features"]}, dtype=float)
            probability = float(saved["model"].predict_proba(row.to_frame().T)[:, 1][0])
            drivers = explain_row(saved["model"], row, top=5)
            model_version = saved["model_version"]
        else:  # no trained model on this machine: fall back to the health score, mapped so its bands
            # line up with the risk levels (health 70 -> 0.5 medium, 40 -> 0.7 high). Not a calibrated probability.
            probability = round(float(np.clip(0.5 + (70 - health["score"]) / 150, 0, 1)), 3)
            drivers = [{"feature": k, "value": round(health["signals"][k], 3), "impact": round(-v / 100, 4)}
                       for k, v in sorted(health["impacts"].items(), key=lambda kv: kv[1]) if v][:5]
            model_version = None
        recs = recommend(features, probability, drivers, velocity=velocity, workload=workload)
        if planning_avg_points and s["unestimated_issues"]:
            extra = s["unestimated_issues"] * planning_avg_points
            for r in recs["recommendations"]:
                if r["id"] == "estimate-issues":
                    r["reason"] += f" Using the planning baseline ({planning_avg_points:g} points per issue), that's about {extra:.0f} untracked points."
        report = sprint_report(sprint.get("sprint_name") or "Sprint", recs, drivers, health)
        results.append({**result, "risk": {"probability": probability, "level": recs["risk_level"],
                                           "drivers": drivers, "model_version": model_version},
                        "features": features, "velocity": velocity, "recommendations": recs["recommendations"],
                        "report": report})
    return results
