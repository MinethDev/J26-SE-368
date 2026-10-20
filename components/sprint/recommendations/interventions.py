"""Turns the risk prediction, its SHAP drivers, the health signals, velocity and workload into
concrete actions for the team. Decision support only: a person decides what to do.

Every recommendation says what to do, why (the numbers behind it) and which signal triggered it,
so it can be traced back to data. Nothing is fixed text without a data condition behind it.
"""
from recommendations.config import (
    BEHIND_GAP, DRIVER_BOOST, HIGH_RISK, MEDIUM_RISK, NOT_STARTED_FROM, NOT_STARTED_SHARE,
    OVERCOMMIT_RATIO, SCOPE_ADDED_SHARE, TEAM_MISSED_RATE, UNESTIMATED_SHARE,
)

# Which model features each rule speaks to (used to rank rules by the SHAP drivers).
RULE_FEATURES = {
    "reduce-scope": {"delivered_so_far", "burndown_gap", "health_score"},
    "start-or-drop-unstarted": {"todo_share", "in_progress_share"},
    "overcommitted": {"committed_points", "committed_issues", "planned_days"},
    "freeze-scope": {"scope_added"},
    "estimate-issues": {"unestimated"},
    "plan-from-history": {"team_prev_missed_rate", "team_prev_delivered_mean", "team_prev_sprints"},
}


def risk_level(probability: float) -> str:
    return "high" if probability >= HIGH_RISK else "medium" if probability >= MEDIUM_RISK else "low"


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def _rec(rule, title, action, reason, severity, evidence):
    return {"id": rule, "title": title, "action": action, "reason": reason,
            "severity": severity, "evidence": evidence}


def _sprint_rules(f: dict) -> list[dict]:
    recs = []
    elapsed, delivered = f["elapsed_fraction"], f.get("delivered_so_far") or 0.0
    left = 1 - elapsed
    if f["burndown_gap"] >= BEHIND_GAP and elapsed >= 0.25:
        # At the current pace the sprint delivers delivered/elapsed of its commitment.
        projected = min(delivered / elapsed, 1.0) if elapsed else 0.0
        cut = 1 - projected
        action = (f"Agree with the product owner which lowest-priority items to move out, about {_pct(cut)} of the commitment."
                  if cut <= 0.5 else
                  "Re-plan the rest of the sprint with the product owner: keep only the most important items that can still be finished.")
        recs.append(_rec(
            "reduce-scope", "Reduce the sprint scope", action,
            f"{_pct(elapsed)} of the sprint has gone but only {_pct(delivered)} of the commitment is done; "
            f"at this pace the sprint delivers about {_pct(projected)}.",
            3, {"elapsed_fraction": elapsed, "delivered_so_far": delivered, "projected_delivery": round(projected, 3)}))
    if elapsed >= NOT_STARTED_FROM and f["todo_share"] >= NOT_STARTED_SHARE:
        n = round(f["todo_share"] * f.get("issues", f.get("committed_issues", 0)))
        recs.append(_rec(
            "start-or-drop-unstarted", "Decide on work that hasn't started",
            "For each issue still in To Do, either start it today or move it to the next sprint.",
            f"{_pct(f['todo_share'])} of the sprint's issues" + (f" (about {n})" if n else "")
            + f" haven't started with {_pct(left)} of the sprint left.",
            2, {"todo_share": f["todo_share"], "time_left": round(left, 3)}))
    if f["scope_added"] >= SCOPE_ADDED_SHARE:
        recs.append(_rec(
            "freeze-scope", "Stop adding work mid-sprint",
            "Freeze the sprint scope; when something urgent comes in, swap out work of the same size.",
            f"Work added after the start is {_pct(f['scope_added'])} of the original commitment.",
            2, {"scope_added": f["scope_added"]}))
    if f["unestimated"] >= UNESTIMATED_SHARE:
        recs.append(_rec(
            "estimate-issues", "Estimate the unestimated issues",
            "Add story points to the unestimated issues so progress and capacity can be tracked.",
            f"{_pct(f['unestimated'])} of the sprint's issues have no story points.",
            1, {"unestimated": f["unestimated"]}))
    rate = f.get("team_prev_missed_rate")
    if rate is not None and rate == rate and rate >= TEAM_MISSED_RATE and f.get("team_prev_sprints", 0) >= 3:
        mean = f.get("team_prev_delivered_mean")
        recs.append(_rec(
            "plan-from-history", "Plan the next sprint from past delivery",
            "In the next planning meeting, commit to what the team has actually been delivering, not to the wish list.",
            f"The team missed {_pct(rate)} of its {int(f['team_prev_sprints'])} earlier sprints"
            + (f", delivering {_pct(mean)} of the commitment on average." if mean == mean and mean is not None else "."),
            1, {"team_prev_missed_rate": rate, "team_prev_delivered_mean": mean}))
    return recs


def _velocity_rules(v: dict | None) -> list[dict]:
    if not v or not v.get("overcommitted"):
        return []
    unit, ratio, velocity, committed = v.get("unit", "points"), v["ratio"], v.get("velocity"), v.get("committed")
    excess = f" (about {committed - velocity:.0f} {unit})" if velocity and committed else ""
    return [_rec(
        "overcommitted", "The sprint is bigger than the team's recent pace",
        f"Move the lowest-priority work out{excess}, so the sprint matches what the team has been completing.",
        f"The commitment is {ratio:.1f}× the average of the team's last finished sprints "
        f"(over {OVERCOMMIT_RATIO}× counts as over-committed).",
        3, {"overcommit_ratio": ratio, "velocity": velocity, "committed": committed})]


def _workload_rules(w: dict | None) -> list[dict]:
    if not w or not w.get("people"):
        return []
    recs, unit = [], w["unit"]
    key = f"open_{unit}"
    if w["overloaded"]:
        busiest = w["overloaded"][0]
        p = w["people"][busiest]
        to = (" to " + ", ".join(w["free"][:2])) if w["free"] else " to the people with the least open work"
        recs.append(_rec(
            "rebalance-work", f"Rebalance work from {busiest}",
            f"Move some of {busiest}'s open issues{to}.",
            f"{busiest} holds {_pct(p['share_of_open'])} of the team's open work ({p[key]:g} {unit}).",
            2, {"person": busiest, "share_of_open": p["share_of_open"], "imbalance": w["imbalance"]}))
    for name in w["wip_heavy"]:
        recs.append(_rec(
            "limit-wip", f"Help {name} finish before starting more",
            f"Ask {name} to finish or hand over in-progress issues before picking up new ones.",
            f"{name} has {w['people'][name]['in_progress']} issues in progress at once.",
            1, {"person": name, "in_progress": w["people"][name]["in_progress"]}))
    if w["unassigned_open_issues"]:
        n = w["unassigned_open_issues"]
        recs.append(_rec(
            "assign-work", "Give unassigned work an owner",
            "Assign an owner to each open issue that has none" + (f", starting with {', '.join(w['free'][:2])}." if w["free"] else "."),
            f"{n} open issue{'s' if n != 1 else ''} in the sprint ha{'ve' if n != 1 else 's'} no assignee.",
            1, {"unassigned_open_issues": n}))
    return recs


def recommend(features: dict, probability: float, drivers: list[dict] | None = None,
              velocity: dict | None = None, workload: dict | None = None, limit: int = 5) -> dict:
    """Returns {risk_level, probability, recommendations[]}, most important first.

    features:  the sprint's model features (risk_prediction.dataset.FEATURES), plus 'issues' if known
    drivers:   explain_row() output, [{feature, value, impact}]; positive impact pushes risk up
    velocity:  productivity.velocity.overcommitment() plus 'velocity', 'committed', 'unit'
    workload:  productivity.workload.team_workload()
    """
    recs = _sprint_rules(features) + _velocity_rules(velocity) + _workload_rules(workload)
    pushing_up = {d["feature"] for d in (drivers or []) if d["impact"] > 0}
    for r in recs:
        r["driver"] = sorted(RULE_FEATURES.get(r["id"], set()) & pushing_up) or None
        r["priority"] = r["severity"] + (DRIVER_BOOST if r["driver"] else 0)
    recs.sort(key=lambda r: -r["priority"])
    level = risk_level(probability)
    if level == "low":
        # Low predicted risk: only keep strong signals, so the team isn't nagged about a healthy sprint.
        recs = [r for r in recs if r["priority"] >= 3]
    if not recs and level == "low":
        recs = [_rec("on-track", "Sprint is on track", "Keep the current plan; no change needed.",
                     f"The model gives a {_pct(probability)} chance of missing the commitment and no strong warning signs fired.",
                     0, {})]
        recs[0].update(driver=None, priority=0)
    return {"risk_level": level, "probability": round(float(probability), 3), "recommendations": recs[:limit]}
