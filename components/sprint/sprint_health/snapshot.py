"""Rebuilds each sprint's state on every day it ran, from the issue change logs.
 
A snapshot only uses changes made up to that moment, so features built from it never
see the future (no leakage). TAWOS change-log formats (checked in research/inspect_change_logs.py):
  Sprint        from/to = comma-separated Jira sprint ids, e.g. "2486, 2670"
  status        from/to = numeric Jira status ids, e.g. "3"
  Story Points  from/to = numbers (often empty)
"""
from bisect import bisect_right
from dataclasses import dataclass, field
 
import numpy as np
import pandas as pd
 
from preprocessing.cleaner import status_category
 
# Teams often add the sprint's issues just after pressing "Start sprint": in TAWOS, 154 of the
# 199 sprints with nothing in them at the start date had their first issue within 24 hours
# (research/inspect_commitment.py). So the commitment is what the sprint holds 24 hours in.
COMMITMENT_GRACE = pd.Timedelta(hours=24)
 
 
def parse_sprint_ids(value) -> frozenset[int]:
    if value is None or (isinstance(value, float) and np.isnan(value)) or pd.isna(value):
        return frozenset()
    return frozenset(int(float(v)) for v in str(value).split(",") if v.strip())
 
 
def _number(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(n) else n
 
 
def build_status_map(issues: pd.DataFrame, logs: pd.DataFrame) -> dict[str, str]:
    """Learns status id -> status name: an issue's last status change lands on its final status."""
    status_logs = logs[logs["field"] == "status"]
    last = status_logs.sort_values("creation_date").groupby("issue_id").tail(1)
    pairs = last[["issue_id", "to_value"]].merge(issues[["issue_id", "status"]], on="issue_id")
    pairs["to_value"] = pairs["to_value"].astype(str)
    return pairs.groupby("to_value")["status"].agg(lambda s: s.mode().iloc[0]).to_dict()
 
 
@dataclass
class _History:
    """Time-ordered values of one field for one issue."""
    times: list = field(default_factory=list)
    values: list = field(default_factory=list)
    initial: object = None  # value before the first change
 
    def at(self, t, default=None):
        if not self.times:
            return default
        i = bisect_right(self.times, t)
        return self.values[i - 1] if i else self.initial
 
 
def _histories(logs: pd.DataFrame, field_name: str, parse) -> dict[int, _History]:
    out: dict[int, _History] = {}
    rows = logs[logs["field"] == field_name].sort_values(["issue_id", "creation_date", "change_id"])
    for issue_id, group in rows.groupby("issue_id", sort=False):
        h = _History(times=list(group["creation_date"]), values=[parse(v) for v in group["to_value"]])
        h.initial = parse(group["from_value"].iloc[0])
        out[issue_id] = h
    return out
 
 
class SprintHistory:
    """Answers 'what did sprint S look like at time t?' for the TAWOS data."""
 
    def __init__(self, issues: pd.DataFrame, sprints: pd.DataFrame, logs: pd.DataFrame):
        self.sprints = sprints.set_index("sprint_id")
        self.issues = issues.set_index("issue_id")
        jira_of = sprints.set_index("sprint_id")["jira_sprint_id"]
        self.final_jira_sprint = issues.set_index("issue_id")["sprint_id"].map(jira_of)
        self.status_map = build_status_map(issues, logs)
        self.membership = _histories(logs, "Sprint", parse_sprint_ids)
        self.status = _histories(logs, "status", lambda v: None if pd.isna(v) else str(v))
        self.points = _histories(logs, "Story Points", _number)
        self.candidates = self._candidates()
        # Plain dicts: pandas .loc is too slow for the millions of lookups a full build makes.
        self.created = self.issues["creation_date"].to_dict()
        self.resolved = self.issues["resolution_date"].to_dict()
        self.final_points = self.issues["story_points"].to_dict()
        self.final_jira_sprint = self.final_jira_sprint.to_dict()
 
    def _candidates(self) -> dict[int, list[int]]:
        """Issues that were ever in each sprint (same project only: Jira sprint ids repeat across projects)."""
        by_project_jira = {(r.project_id, r.jira_sprint_id): sid for sid, r in self.sprints.iterrows()}
        out: dict[int, set[int]] = {sid: set() for sid in self.sprints.index}
        for issue_id, issue in self.issues.iterrows():
            out[issue["sprint_id"]].add(issue_id)
            h = self.membership.get(issue_id)
            if h:
                for ids in [h.initial, *h.values]:
                    for jid in ids:
                        sid = by_project_jira.get((issue["project_id"], jid))
                        if sid is not None:
                            out[sid].add(issue_id)
        return {sid: sorted(ids) for sid, ids in out.items()}
 
    def in_sprint(self, issue_id: int, jira_sprint_id: int, t) -> bool:
        if t < self.created[issue_id]:
            return False
        h = self.membership.get(issue_id)
        if h is None:  # never moved: it was always in its final sprint
            return self.final_jira_sprint[issue_id] == jira_sprint_id
        return jira_sprint_id in h.at(t)
 
    def category(self, issue_id: int, t) -> str:
        h = self.status.get(issue_id)
        if h is None:  # no status changes: use resolution time
            resolved = self.resolved[issue_id]
            done = pd.notna(resolved) and resolved <= t
            return "Done" if done else "To Do"
        status_id = h.at(t)
        return status_category(self.status_map.get(status_id, "To Do")) or "To Do"
 
    def story_points(self, issue_id: int, t) -> float | None:
        h = self.points.get(issue_id)
        value = h.at(t) if h else None
        if value is None:
            value = _number(self.final_points[issue_id])
        return value
 
    def snapshot(self, sprint_id: int, t, committed: set[int] | None = None, count_removed: bool = True) -> dict:
        sprint = self.sprints.loc[sprint_id]
        jid = sprint["jira_sprint_id"]
        members = {i for i in self.candidates[sprint_id] if self.in_sprint(i, jid, t)}
        committed = members if committed is None else committed
        cats = {i: self.category(i, t) for i in members}
        pts = {i: self.story_points(i, t) for i in members | committed}
        sp = lambda ids: float(sum(pts[i] or 0 for i in ids))
        # Before the commitment is fixed, committed issues not yet added are not "removed".
        removed = committed - members if count_removed else set()
        done = {i for i in members if cats[i] == "Done"}
        committed_done = done & committed  # delivered from what was promised at the start
        return {
            "issues": len(members),
            "points": sp(members),
            "done_issues": len(done),
            "done_points": sp(done),
            "committed_done_issues": len(committed_done),
            "committed_done_points": sp(committed_done),
            "in_progress_issues": sum(c == "In Progress" for c in cats.values()),
            "todo_issues": sum(c == "To Do" for c in cats.values()),
            "unestimated_issues": sum(pts[i] is None for i in members),
            "added_issues": len(members - committed),
            "added_points": sp(members - committed),
            "removed_issues": len(removed),
            "removed_points": sp(removed),
        }
 
    def commitment_time(self, sprint_id: int):
        return self.sprints.loc[sprint_id, "start_date"] + COMMITMENT_GRACE
 
    def committed_at_start(self, sprint_id: int) -> set[int]:
        jid = self.sprints.loc[sprint_id, "jira_sprint_id"]
        t = self.commitment_time(sprint_id)
        return {i for i in self.candidates[sprint_id] if self.in_sprint(i, jid, t)}
 
 
def build_daily_snapshots(history: SprintHistory) -> pd.DataFrame:
    """One row per sprint per day, from the start date to the end date."""
    rows = []
    for sprint_id, sprint in history.sprints.iterrows():
        start, end = sprint["start_date"], sprint["end_date"]
        committed = history.committed_at_start(sprint_id)
        commit_t = history.commitment_time(sprint_id)
        committed_points = float(sum(history.story_points(i, commit_t) or 0 for i in committed))
        days = max(int(np.ceil((end - start).total_seconds() / 86400)), 1)
        for day in range(days + 1):
            t = min(start + pd.Timedelta(days=day), end)
            row = {
                "sprint_id": sprint_id,
                "project_id": sprint["project_id"],
                "day": day,
                "at": t,
                "elapsed_fraction": round(day / days, 4),
                "committed_issues": len(committed),
                "committed_points": committed_points,
            }
            row.update(history.snapshot(sprint_id, t, committed, count_removed=t >= commit_t))
            rows.append(row)
    return pd.DataFrame(rows)