import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent

# The raw dataset is stored outside the repository.
RAW_DATA_ENV_VAR = "DEVINTEL_PR_RAW_DATA"
DEFAULT_RAW_DATA_PATH = Path(r"D:\Downloads Folder\train-00001.parquet")

# Generated outputs (ignored by Git).
OUTPUT_DIR = PACKAGE_DIR / "data"
RESULTS_DIR = OUTPUT_DIR / "results"
SELECTED_CONFIG_PATH = RESULTS_DIR / "selected_config.json"
FROZEN_CONFIG_PATH = RESULTS_DIR / "frozen_config.json"

RANDOM_SEED = 42


def get_raw_data_path(override=None) -> Path:
    """Resolve the raw dataset path: argument, then environment, then default."""

    if override:
        return Path(override)

    from_env = os.environ.get(RAW_DATA_ENV_VAR)

    if from_env:
        return Path(from_env)

    return DEFAULT_RAW_DATA_PATH
