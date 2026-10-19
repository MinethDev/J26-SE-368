"""One-off look at the change-log formats Step 3 depends on (run from components/sprint).

    python research/inspect_change_logs.py
"""
import pandas as pd

CLEAN = "data/clean"
issues = pd.read_parquet(f"{CLEAN}/issues.parquet")
sprints = pd.read_parquet(f"{CLEAN}/sprints.parquet")
logs = pd.read_parquet(f"{CLEAN}/change_logs.parquet")
pd.set_option("display.width", 200, "display.max_colwidth", 60)

print("Change-log issue_ids found in issues:", logs["issue_id"].isin(issues["issue_id"]).mean().round(3))
print("Issues with any change log:", issues["issue_id"].isin(logs["issue_id"]).mean().round(3))

for field in ["Sprint", "status", "Story Points"]:
    rows = logs[logs["field"] == field]
    print(f"\n=== {field}: {len(rows)} rows, change_type values: {rows['change_type'].unique().tolist()}")
    print(rows[["issue_id", "from_value", "to_value", "creation_date"]].sample(min(8, len(rows)), random_state=1).to_string(index=False))

print("\n=== sprints (to match against Sprint change-log values)")
print(sprints[["sprint_id", "jira_sprint_id", "sprint_name", "project_id", "start_date", "end_date"]].head(5).to_string(index=False))

# How often does an issue join or leave its sprint after the sprint started? (scope change)
s = logs[logs["field"] == "Sprint"].merge(issues[["issue_id", "sprint_id"]], on="issue_id").merge(sprints[["sprint_id", "start_date"]], on="sprint_id")
print("\nSprint changes made after the issue's sprint started:", int((s["creation_date"] > s["start_date"]).sum()), "of", len(s))
