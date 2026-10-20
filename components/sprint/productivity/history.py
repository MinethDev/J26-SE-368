"""Who each issue was assigned to at any moment, from the TAWOS change logs (research data only).

The TAWOS export has no assignee column, so the only source is the change log. An issue that was
assigned when it was created and never re-assigned has no assignee change, so its assignee is unknown.
run_productivity.py prints how many issues that leaves out.
"""
import pandas as pd

from sprint_health.snapshot import _histories


def assignee_histories(logs: pd.DataFrame) -> dict:
    field = logs["field"].astype(str).str.lower() == "assignee"
    rows = logs[field].assign(field="assignee")
    return _histories(rows, "assignee", lambda v: None if pd.isna(v) or not str(v).strip() else str(v).strip())


MISSING = object()


def assignee_at(histories: dict, issue_id, t):
    """The assignee at time t, None if unassigned, MISSING if the change log never mentions it."""
    h = histories.get(issue_id)
    return h.at(t) if h else MISSING
