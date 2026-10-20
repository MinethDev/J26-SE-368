"""Cleans the raw TAWOS tables: types, dates, story points and status categories.
 
Status categories use the same names as the platform's Jira connector
('To Do' | 'In Progress' | 'Done'), so the model sees the same values in research and live.
"""
import pandas as pd
 
# Won't Fix / Invalid are closed but not delivered: Jira files them under Done, and `resolution` keeps the difference.
DONE_STATUSES = {"done", "closed", "resolved", "complete", "completed", "fixed", "waiting for release", "won't fix", "invalid"}
IN_PROGRESS_STATUSES = {"in progress", "in review", "review", "code review", "testing", "in testing", "qa", "in qa", "reopened",
                        "development in progress", "in qe test", "reviewable", "reviewed"}
 
ISSUE_DATES = ["creation_date", "estimation_date", "resolution_date", "last_updated"]
SPRINT_DATES = ["start_date", "end_date", "activated_date", "complete_date"]
ISSUE_NUMBERS = [
    "story_points", "timespent", "in_progress_minutes", "total_effort_minutes", "resolution_time_minutes",
    "title_changed_after_estimation", "description_changed_after_estimation", "story_point_changed_after_estimation",
]
 
 
def status_category(status: object) -> str | None:
    if pd.isna(status):
        return None
    s = str(status).strip().lower()
    if s in DONE_STATUSES:
        return "Done"
    if s in IN_PROGRESS_STATUSES:
        return "In Progress"
    return "To Do"
 
 
def clean_issues(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ISSUE_DATES:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ISSUE_NUMBERS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["title", "issue_type", "priority", "status", "resolution"]:
        df[col] = df[col].astype("string").str.strip()
    df["status_category"] = df["status"].map(status_category)
    df = df.drop_duplicates(subset="issue_id")
    return df
 
 
def clean_sprints(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in SPRINT_DATES:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["sprint_name"] = df["sprint_name"].astype("string").str.strip()
    df["sprint_state"] = df["sprint_state"].astype("string").str.strip().str.lower()  # platform uses 'active' / 'closed'
    df["planned_days"] = (df["end_date"] - df["start_date"]).dt.total_seconds() / 86400
    df = df.drop_duplicates(subset="sprint_id")
    return df
 
 
def clean_change_logs(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["creation_date"] = pd.to_datetime(df["creation_date"], errors="coerce")
    df["field"] = df["field"].astype("string").str.strip()
    df = df.drop_duplicates(subset="change_id").sort_values(["issue_id", "creation_date", "change_id"])
    return df
 
 
def report(issues: pd.DataFrame, sprints: pd.DataFrame, change_logs: pd.DataFrame) -> None:
    """Prints what a person should check before trusting the data."""
    print("\nIssue status -> category (check that every status landed in the right bucket):")
    print(issues.groupby(["status", "status_category"], dropna=False).size().to_string())
    print("\nIssues without story points:", int(issues["story_points"].isna().sum()))
    print("Issues whose sprint_id is not in sprints:", int((~issues["sprint_id"].isin(sprints["sprint_id"])).sum()))
    print("Sprints with no issues:", int((~sprints["sprint_id"].isin(issues["sprint_id"])).sum()))
    print("Sprints with missing start/end date:", int(sprints[["start_date", "end_date"]].isna().any(axis=1).sum()))
    print("\nTop 15 change-log fields (we need 'status', 'Sprint' and 'Story Points' history for snapshots):")
    print(change_logs["field"].value_counts().head(15).to_string())