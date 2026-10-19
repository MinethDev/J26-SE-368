"""Settings for team productivity and workload. These are decision-support thresholds, not learned values."""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR.parent / "data"
RESULTS_DIR = DATA_DIR / "productivity"

# Velocity = average work completed in the team's last N finished sprints.
VELOCITY_WINDOW = 3
# Trend = slope of completed work over the team's last N finished sprints.
TREND_WINDOW = 6
# A commitment this many times the recent velocity counts as over-committed.
OVERCOMMIT_RATIO = 1.2

# Someone is overloaded when their open work is this many times the team median...
OVERLOAD_FACTOR = 1.5
# ...and they hold at least this share of the team's open work.
OVERLOAD_MIN_SHARE = 0.25
# More issues than this in progress at once for one person is a WIP warning.
WIP_LIMIT = 3
# Gini of open work across assignees (0 = perfectly even, 1 = one person has everything).
IMBALANCE_ALERT = 0.4

UNASSIGNED = "Unassigned"
