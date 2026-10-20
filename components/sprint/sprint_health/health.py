"""Explainable sprint health score (0-100) from one daily snapshot. No training needed.

Each signal measures one problem on a 0..1 scale; the score is 100 minus the weighted problems.
The per-signal impacts are what the dashboard shows as the explanation.
"""
from dataclasses import asdict

from sprint_health.config import DEFAULT_BANDS, DEFAULT_WEIGHTS, HealthBands, HealthWeights

HEALTHY, AT_RISK, CRITICAL = "healthy", "at-risk", "critical"


def _share(part: float, whole: float) -> float:
    return min(max(part / whole, 0.0), 1.0) if whole else 0.0


def _committed_basis(s: dict) -> tuple[str, str]:
    """Measure in story points when the commitment has points, otherwise in issue counts."""
    return ("points", "committed_points") if s["committed_points"] > 0 else ("issues", "committed_issues")


def delivered_share(s: dict) -> float | None:
    unit, total = _committed_basis(s)
    if not s[total]:
        return None
    return _share(s[f"committed_done_{unit}"], s[total])


def signals(s: dict) -> dict[str, float]:
    unit, total = _committed_basis(s)
    elapsed = s["elapsed_fraction"]
    delivered = delivered_share(s) or 0.0
    return {
        # How far behind the ideal burndown, relative to where it should be by now
        # (floored at 25% of the sprint so the first days don't swing the score).
        "burndown_gap": min(max(elapsed - delivered, 0.0) / max(elapsed, 0.25), 1.0),
        "scope_added": _share(s[f"added_{unit}"], s[total]),
        "scope_removed": _share(s[f"removed_{unit}"], s[total]),
        "unestimated": _share(s["unestimated_issues"], s["issues"]),
        # To Do work only matters once the sprint is well under way.
        "late_work_not_started": _share(s["todo_issues"], s["issues"]) * elapsed,
    }


def assess(s: dict, weights: HealthWeights = DEFAULT_WEIGHTS, bands: HealthBands = DEFAULT_BANDS) -> dict:
    """Returns {score, band, signals, impacts}. Impacts are the points each signal took off the score."""
    sig = signals(s)
    w = asdict(weights)
    impacts = {k: -round(100 * w[k] * v, 2) for k, v in sig.items()}
    score = round(max(100 + sum(impacts.values()), 0.0), 1)
    band = HEALTHY if score >= bands.healthy_from else AT_RISK if score >= bands.at_risk_from else CRITICAL
    return {"score": score, "band": band, "signals": sig, "impacts": impacts}
