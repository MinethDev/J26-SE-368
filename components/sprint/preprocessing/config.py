"""Dataset location for Sprint Intelligence (TAWOS sprint export). Data is never committed."""
import os
from pathlib import Path

DEFAULT_RAW_DIR = Path(r"C:\Users\Evindu\OneDrive\Desktop\Devintel Dataset")

ISSUES_FILE = "final_sprint_issues.csv"
SPRINTS_FILE = "final_sprint_metadata.csv"
CHANGE_LOGS_FILE = "final_sprint_change_logs.csv"


def raw_dir(cli_path: str | None = None) -> Path:
    """--raw-path, then DEVINTEL_SPRINT_RAW_DATA, then the default above."""
    return Path(cli_path or os.environ.get("DEVINTEL_SPRINT_RAW_DATA") or DEFAULT_RAW_DIR)