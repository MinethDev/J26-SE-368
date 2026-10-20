"""Workload per person in one sprint, from the issues the platform already has.

Input issues use the platform's fields: assignee, story_points, status_category
('To Do' | 'In Progress' | 'Done'). Open work = not Done. Like the health score, load is measured
in story points when the sprint has any, otherwise in issue counts.
"""
from statistics import median

from productivity.config import IMBALANCE_ALERT, OVERLOAD_FACTOR, OVERLOAD_MIN_SHARE, UNASSIGNED, WIP_LIMIT


def gini(values: list[float]) -> float:
    """0 = everyone has the same load, 1 = one person has all of it."""
    values = sorted(v for v in values if v >= 0)
    n, total = len(values), sum(values)
    if n < 2 or total == 0:
        return 0.0
    weighted = sum((i + 1) * v for i, v in enumerate(values))
    return round((2 * weighted) / (n * total) - (n + 1) / n, 3)


def _points(issue: dict) -> float:
    p = issue.get("story_points")
    return float(p) if isinstance(p, (int, float)) and p == p else 0.0


def person_load(issues: list[dict]) -> dict[str, dict]:
    people: dict[str, dict] = {}
    for issue in issues:
        name = issue.get("assignee") or UNASSIGNED
        p = people.setdefault(name, {"open_issues": 0, "open_points": 0.0, "in_progress": 0,
                                     "done_issues": 0, "done_points": 0.0})
        if issue.get("status_category") == "Done":
            p["done_issues"] += 1
            p["done_points"] += _points(issue)
        else:
            p["open_issues"] += 1
            p["open_points"] += _points(issue)
            p["in_progress"] += issue.get("status_category") == "In Progress"
    return people


def team_workload(issues: list[dict]) -> dict:
    """Per-person load plus the team-level signals the recommendations use."""
    people = person_load(issues)
    unit = "points" if any(_points(i) > 0 for i in issues) else "issues"
    key = f"open_{unit}"
    assigned = {n: p for n, p in people.items() if n != UNASSIGNED}
    loads = {n: p[key] for n, p in assigned.items()}
    total_open = sum(loads.values())
    med = median(loads.values()) if loads else 0.0
    for name, p in assigned.items():
        p["share_of_open"] = round(p[key] / total_open, 3) if total_open else 0.0
    overloaded = sorted(
        (n for n, load in loads.items()
         if len(loads) > 1 and load > OVERLOAD_FACTOR * max(med, 1e-9) and assigned[n]["share_of_open"] >= OVERLOAD_MIN_SHARE),
        key=lambda n: -loads[n],
    )
    free = sorted(n for n, load in loads.items() if load == 0)
    unassigned = people.get(UNASSIGNED, {})
    imbalance = gini(list(loads.values()))
    return {
        "unit": unit,
        "people": assigned,
        "assignees": len(assigned),
        "open_total": total_open,
        "imbalance": imbalance,
        "imbalanced": imbalance >= IMBALANCE_ALERT and len(assigned) > 1,
        "overloaded": overloaded,
        "free": free,  # assigned people with no open work left
        "wip_heavy": sorted(n for n, p in assigned.items() if p["in_progress"] > WIP_LIMIT),
        "unassigned_open_issues": unassigned.get("open_issues", 0),
        "unassigned_open_points": unassigned.get("open_points", 0.0),
    }
