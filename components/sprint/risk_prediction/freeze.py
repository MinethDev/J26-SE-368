"""Freeze-before-test: the settings and code are fixed (fingerprinted) before the single test run."""
import hashlib
import json
from datetime import datetime, timezone

from risk_prediction.config import FROZEN_CONFIG_PATH, PACKAGE_DIR, TEST_RESULTS_PATH

# Code that decides what the test numbers will be.
FINGERPRINTED = ["risk_prediction", "sprint_health", "preprocessing"]


def code_fingerprint() -> str:
    h = hashlib.sha256()
    root = PACKAGE_DIR.parent
    for folder in FINGERPRINTED:
        for path in sorted((root / folder).glob("*.py")):
            h.update(path.name.encode())
            h.update(path.read_bytes().replace(b"\r\n", b"\n"))  # same hash on Windows and Linux
    return h.hexdigest()


def freeze(selected: dict) -> dict:
    frozen = {**selected, "fingerprint": code_fingerprint(), "frozen_at": datetime.now(timezone.utc).isoformat()}
    FROZEN_CONFIG_PATH.write_text(json.dumps(frozen, indent=2, default=float))
    return frozen


def load_frozen_for_test() -> dict:
    if not FROZEN_CONFIG_PATH.exists():
        raise SystemExit("Nothing frozen yet: run `python run_risk_prediction.py freeze` first.")
    frozen = json.loads(FROZEN_CONFIG_PATH.read_text())
    if frozen["fingerprint"] != code_fingerprint():
        raise SystemExit("Code changed after freezing. The test split must be run with the frozen code: "
                         "revert the change, or re-tune on validation and freeze again.")
    if TEST_RESULTS_PATH.exists():
        raise SystemExit(f"The test split was already evaluated with these settings ({TEST_RESULTS_PATH}). "
                         "It is run once only.")
    return frozen
