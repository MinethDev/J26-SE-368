"""Settings for sprint risk prediction (will this sprint miss its commitment?)."""
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR.parent / "data"

# Generated outputs (ignored by Git).
RESULTS_DIR = DATA_DIR / "risk"
DATASET_PATH = RESULTS_DIR / "dataset.parquet"
SELECTED_CONFIG_PATH = RESULTS_DIR / "selected_config.json"

RANDOM_SEED = 42

# Chronological split within each project: oldest 70% of sprints train, next 15% validate, newest 15% test.
TRAIN_SHARE, VALIDATION_SHARE = 0.70, 0.15
# Projects with fewer sprints than this go entirely to training (too small to split).
MIN_SPRINTS_TO_SPLIT = 7

# Hyper-parameter grid for XGBoost, searched on the validation split only.
XGB_GRID = {
    "max_depth": [2, 3, 4],
    "n_estimators": [100, 300],
    "learning_rate": [0.05, 0.1],
    "min_child_weight": [1, 5],
}
