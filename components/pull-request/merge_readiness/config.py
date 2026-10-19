from dataclasses import dataclass
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent

# Generated outputs (ignored by Git).
OUTPUT_DIR = PACKAGE_DIR / "data"
RESULTS_DIR = OUTPUT_DIR / "results"
SELECTED_CONFIG_PATH = RESULTS_DIR / "selected_config.json"
FROZEN_CONFIG_PATH = RESULTS_DIR / "frozen_config.json"

RANDOM_SEED = 42


@dataclass(frozen=True)
class ReadinessThresholds:
    """
    Initial checklist thresholds.

    These are unvalidated heuristics chosen for the first implementation,
    not values taken from the proposal or from empirical calibration.
    """

    min_approvals: int = 1
    min_reviewers: int = 1
    stale_after_days: float = 14.0
    large_change_lines: int = 500
