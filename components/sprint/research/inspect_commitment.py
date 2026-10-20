"""Why do some sprints have nothing committed at their start date? (run from components/sprint)

    python research/inspect_commitment.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # components/sprint, for sprint_health
from sprint_health.snapshot import SprintHistory

CLEAN = "data/clean"
h = SprintHistory(*(pd.read_parquet(f"{CLEAN}/{n}.parquet") for n in ["issues", "sprints", "change_logs"]))

rows = []
for sprint_id, sprint in h.sprints.iterrows():
    start, jid = sprint["start_date"], sprint["jira_sprint_id"]
    committed = h.committed_at_start(sprint_id)
    joins = []  # hours after start when each issue first appears in the sprint
    for i in h.candidates[sprint_id]:
        for hours in [0, 1, 6, 24, 48, 72, 168]:
            if h.in_sprint(i, jid, start + pd.Timedelta(hours=hours)):
                joins.append(hours)
                break
    rows.append({"sprint_id": sprint_id, "project_id": sprint["project_id"], "committed": len(committed),
                 "candidates": len(h.candidates[sprint_id]), "first_join_hours": min(joins) if joins else None})
df = pd.DataFrame(rows)
empty = df[df["committed"] == 0]
print(f"Sprints with nothing committed at start: {len(empty)} of {len(df)}")
print("\nFor those, hours after start when the first issue shows up in the sprint (None = never within a week):")
print(empty["first_join_hours"].value_counts(dropna=False).sort_index().to_string())
print("\nBy project (empty / all sprints):")
print(pd.concat([empty.groupby("project_id").size(), df.groupby("project_id").size()], axis=1, keys=["empty", "all"]).fillna(0).astype(int).to_string())
