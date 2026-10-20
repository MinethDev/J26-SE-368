"""Turns the platform's Jira data (the /analyze context) into the tables the research code uses,
so a live sprint goes through exactly the same snapshot, health and feature code as TAWOS did.

Platform issue fields: key, sprintId, storyPoints, status, statusCategory, assignee, createdAt,
resolvedAt and, once the Jira connector fetches it, changelog: [{field, from, to, at}] with
field 'Sprint' (from/to = comma-separated Jira sprint ids), 'status' (status ids) or
'Story Points' (numbers). Without a changelog, every issue is taken to have always been in its
current sprint, which is less accurate for added/removed work (see README).
"""
import pandas as pd

from sprint_health.snapshot import SprintHistory

PROJECT_ID = 1
STORY_POINT_FIELDS = {"story points", "story point estimate"}


def to_time(value) -> pd.Timestamp | None:
    """Platform dates are ISO strings in UTC; the research code uses naive UTC timestamps."""
    if value in (None, ""):
        return None
    t = pd.Timestamp(value)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def _jira_id(source_id, fallback: int) -> int:
    try:
        return int(source_id)
    except (TypeError, ValueError):
        return -fallback  # non-numeric ids (sample data): never match a changelog entry


def build_tables(context: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Returns (issues, sprints, change_logs, lookup) shaped like data/clean/*.parquet.

    lookup maps internal ids back to the platform: {'sprint': {id: sprint dict}, 'issue': {id: issue dict}}.
    Sprints without start and end dates are left out (they can't be measured over time).
    """
    sprint_rows, sprint_of_source, sprint_lookup = [], {}, {}
    for n, s in enumerate(context.get("sprints", []), start=1):
        start, end = to_time(s.get("startDate")), to_time(s.get("endDate"))
        if start is None or end is None or end <= start:
            continue
        sprint_of_source[str(s.get("sourceId"))] = n
        sprint_lookup[n] = s
        sprint_rows.append({
            "sprint_id": n, "jira_sprint_id": _jira_id(s.get("sourceId"), n), "sprint_name": s.get("name"),
            "sprint_state": (s.get("state") or "").lower(), "start_date": start, "end_date": end,
            "complete_date": to_time(s.get("completeDate")), "project_id": PROJECT_ID,
            "planned_days": (end - start).total_seconds() / 86400,
        })

    issue_rows, log_rows, issue_lookup = [], [], {}
    for n, i in enumerate(context.get("issues", []), start=1):
        sprint_id = sprint_of_source.get(str(i.get("sprintId")))
        created = to_time(i.get("createdAt"))
        if sprint_id is None or created is None:
            continue
        issue_lookup[n] = i
        points = i.get("storyPoints")
        issue_rows.append({
            "issue_id": n, "issue_key": i.get("key"), "status": i.get("status") or i.get("statusCategory"),
            "status_category": i.get("statusCategory"), "assignee": i.get("assignee"),
            "creation_date": created, "resolution_date": to_time(i.get("resolvedAt")),
            "story_points": float(points) if isinstance(points, (int, float)) else None,
            "project_id": PROJECT_ID, "sprint_id": sprint_id,
        })
        for change in i.get("changelog") or []:
            field = str(change.get("field", ""))
            if field.lower() in STORY_POINT_FIELDS:
                field = "Story Points"
            if field not in ("Sprint", "status", "Story Points") or to_time(change.get("at")) is None:
                continue
            log_rows.append({"change_id": len(log_rows) + 1, "issue_id": n, "field": field,
                             "from_value": change.get("from"), "to_value": change.get("to"),
                             "creation_date": to_time(change.get("at"))})

    columns = ["change_id", "issue_id", "field", "from_value", "to_value", "creation_date"]
    issues = pd.DataFrame(issue_rows, columns=[
        "issue_id", "issue_key", "status", "status_category", "assignee", "creation_date", "resolution_date",
        "story_points", "project_id", "sprint_id"])
    sprints = pd.DataFrame(sprint_rows, columns=[
        "sprint_id", "jira_sprint_id", "sprint_name", "sprint_state", "start_date", "end_date",
        "complete_date", "project_id", "planned_days"])
    logs = pd.DataFrame(log_rows, columns=columns)
    for df, cols in ((issues, ["creation_date", "resolution_date"]), (sprints, ["start_date", "end_date", "complete_date"]),
                     (logs, ["creation_date"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c])
    return issues, sprints, logs, {"sprint": sprint_lookup, "issue": issue_lookup}


class LiveHistory(SprintHistory):
    """SprintHistory for live data: an issue with no status changes recorded is in its CURRENT
    status category from `now` on (Jira tells us that directly), instead of only Done/To Do."""

    def __init__(self, issues: pd.DataFrame, sprints: pd.DataFrame, logs: pd.DataFrame, now: pd.Timestamp):
        super().__init__(issues, sprints, logs)
        self.now = now
        self.current_category = issues.set_index("issue_id")["status_category"].to_dict()

    def category(self, issue_id: int, t) -> str:
        if issue_id not in self.status and t >= self.now and self.current_category.get(issue_id):
            return self.current_category[issue_id]
        return super().category(issue_id, t)
