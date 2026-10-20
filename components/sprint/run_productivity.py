"""Team productivity and workload on the TAWOS sprints.

Run from components/sprint, after run_sprint_snapshots.py:
    python run_productivity.py

1. Velocity, throughput, say/do and carry-over for every finished sprint.
2. Does committing more than the recent velocity go with missing the sprint?
3. Workload per person halfway through each sprint, where the change logs say who had what.
"""
import numpy as np
import pandas as pd

from productivity.config import OVERCOMMIT_RATIO, RESULTS_DIR
from productivity.history import MISSING, assignee_at, assignee_histories
from productivity.velocity import overcommitment, sprint_velocity, team_trend
from productivity.workload import team_workload
from risk_prediction.dataset import sprint_outcomes
from sprint_health.snapshot import SprintHistory

DATA_DIR = RESULTS_DIR.parent
CLEAN_DIR = DATA_DIR / "clean"
CHECKPOINT = 0.5


def velocity_report(velocity: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    print(f"Finished sprints with a commitment: {len(velocity)}")
    print(f"  measured in story points: {(velocity['unit'] == 'points').mean():.0%}, in issues: {(velocity['unit'] == 'issues').mean():.0%}")
    print(f"  median say/do (delivered / committed): {velocity['say_do'].median():.2f}")
    print(f"  median throughput: {velocity['throughput_per_day'].median():.2f} issues per day")
    print(f"  median carry-over: {velocity['carry_over_issues'].median():.0f} committed issues not finished")

    rows = []
    for sprint_id, v in velocity.iterrows():
        trend = team_trend(velocity[velocity["unit"] == v["unit"]], v["project_id"], v["start_date"])
        over = overcommitment(v["committed"], trend["velocity"])
        rows.append({"sprint_id": sprint_id, **trend, "overcommit_ratio": over["ratio"], "overcommitted": over["overcommitted"]})
    trends = pd.DataFrame(rows).set_index("sprint_id")
    joined = velocity.join(trends).join(outcomes["missed"])

    known = joined.dropna(subset=["overcommit_ratio"])
    print(f"\nCommitment vs the team's recent velocity (last sprints that had ended before this one started),"
          f" {len(known)} sprints with enough history:")
    bins = pd.cut(known["overcommit_ratio"], [0, 0.8, 1.0, OVERCOMMIT_RATIO, 1.5, 2.0, np.inf])
    table = known.groupby(bins, observed=True)["missed"].agg(["size", "mean"])
    print("  commitment / velocity   sprints  share that missed")
    for b, r in table.iterrows():
        print(f"  {str(b):<22} {int(r['size']):>8}  {r['mean']:.0%}")
    return joined


def workload_report(history: SprintHistory, logs: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame | None:
    assignees = assignee_histories(logs)
    print(f"\nIssues with an assignee change in the change logs: {len(assignees)} of {len(history.issues)}")
    if not assignees:
        print("  No assignee history in this dataset, so per-person workload can't be measured on TAWOS.")
        print("  It still works live, because the platform's Jira issues carry the assignee.")
        return None

    rows = []
    for sprint_id, sprint in history.sprints.iterrows():
        if sprint_id not in outcomes.index:
            continue
        t = sprint["start_date"] + CHECKPOINT * (sprint["end_date"] - sprint["start_date"])
        jid = sprint["jira_sprint_id"]
        members = [i for i in history.candidates[sprint_id] if history.in_sprint(i, jid, t)]
        if not members:
            continue
        issues, unknown = [], 0
        for i in members:
            who = assignee_at(assignees, i, t)
            if who is MISSING:
                unknown += 1
                continue
            issues.append({"assignee": who, "story_points": history.story_points(i, t),
                           "status_category": history.category(i, t)})
        w = team_workload(issues)
        rows.append({"sprint_id": sprint_id, "issues": len(members), "known_share": 1 - unknown / len(members),
                     "assignees": w["assignees"], "imbalance": w["imbalance"], "imbalanced": w["imbalanced"],
                     "overloaded": len(w["overloaded"]), "unassigned_open_issues": w["unassigned_open_issues"]})
    work = pd.DataFrame(rows).set_index("sprint_id").join(outcomes["missed"])
    usable = work[(work["known_share"] >= 0.8) & (work["assignees"] >= 2)]
    print(f"  Sprints where at least 80% of issues have a known assignee and 2+ people work: {len(usable)} of {len(work)}")
    if len(usable) >= 20:
        print(f"\nHalfway through the sprint, on those {len(usable)} sprints:")
        print("  workload               sprints  share that missed")
        for label, mask in [("imbalanced", usable["imbalanced"]), ("balanced", ~usable["imbalanced"]),
                            ("someone overloaded", usable["overloaded"] > 0), ("nobody overloaded", usable["overloaded"] == 0)]:
            part = usable[mask]
            if len(part):
                print(f"  {label:<22} {len(part):>7}  {part['missed'].mean():.0%}")
    else:
        print("  Too few sprints to compare workload with missed sprints; report this as a data limitation.")
    return work


def main() -> None:
    snapshots = pd.read_parquet(DATA_DIR / "snapshots" / "sprint_days.parquet")
    sprints = pd.read_parquet(CLEAN_DIR / "sprints.parquet")
    issues = pd.read_parquet(CLEAN_DIR / "issues.parquet")
    logs = pd.read_parquet(CLEAN_DIR / "change_logs.parquet")
    outcomes = sprint_outcomes(snapshots).dropna(subset=["delivered"])  # sprints with no commitment have no outcome

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    velocity = velocity_report(sprint_velocity(snapshots, sprints), outcomes)
    velocity.to_parquet(RESULTS_DIR / "sprint_velocity.parquet")
    print(f"\nwrote {RESULTS_DIR / 'sprint_velocity.parquet'}")

    work = workload_report(SprintHistory(issues, sprints, logs), logs, outcomes)
    if work is not None:
        work.to_parquet(RESULTS_DIR / "sprint_workload.parquet")
        print(f"wrote {RESULTS_DIR / 'sprint_workload.parquet'}")


if __name__ == "__main__":
    main()
