"""Sprint health settings.

These are first-implementation heuristics, not values calibrated on data. run_sprint_health.py
reports how well the resulting score separates sprints that missed their commitment, so the
risk model (Step 5) has a baseline to beat.
"""
from dataclasses import dataclass, field

# A sprint "missed its commitment" when it delivered less than this share of what it committed.
MISSED_THRESHOLD = 0.8

# Points in the sprint's life where the score is evaluated (share of planned duration elapsed).
CHECKPOINTS = (0.25, 0.5, 0.75)


@dataclass(frozen=True)
class HealthWeights:
    """How much each problem signal (each scaled to 0..1) lowers the 0-100 health score."""

    burndown_gap: float = 0.45      # behind the ideal burndown line
    scope_added: float = 0.2        # work added after the commitment
    scope_removed: float = 0.1      # committed work taken out
    unestimated: float = 0.1        # issues with no story points
    late_work_not_started: float = 0.15  # committed work still in To Do late in the sprint


@dataclass(frozen=True)
class HealthBands:
    healthy_from: float = 70.0
    at_risk_from: float = 40.0  # below this: critical


DEFAULT_WEIGHTS = HealthWeights()
DEFAULT_BANDS = HealthBands()
