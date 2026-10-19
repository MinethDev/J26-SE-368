"""Sprint risk prediction: build the dataset, then tune and compare models on the validation split.

Run from components/sprint, after run_sprint_snapshots.py:
    python run_risk_prediction.py build      # dataset + split
    python run_risk_prediction.py tune       # compare models on VALIDATION, save the chosen XGBoost settings
The test split is not touched here; Step 5b freezes the settings and runs it once.
"""
import itertools
import json
import sys

import numpy as np
import pandas as pd

from risk_prediction.config import DATA_DIR, DATASET_PATH, RESULTS_DIR, SELECTED_CONFIG_PATH, XGB_GRID
from risk_prediction.dataset import build_dataset
from risk_prediction.evaluate import metrics, table
from risk_prediction.model import fit_predict, logistic_regression, xgboost
from risk_prediction.split import assign_splits, check_no_leakage


def build() -> None:
    snapshots = pd.read_parquet(DATA_DIR / "snapshots" / "sprint_days.parquet")
    sprints = pd.read_parquet(DATA_DIR / "clean" / "sprints.parquet")
    dataset = build_dataset(snapshots, sprints)
    dataset = dataset.join(assign_splits(dataset), on="sprint_id")
    check_no_leakage(dataset)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(DATASET_PATH, index=False)
    summary = dataset.drop_duplicates("sprint_id").groupby("split")["missed"].agg(["size", "mean"]).round(2)
    print(f"wrote {DATASET_PATH} ({len(dataset)} rows = sprints x checkpoints)")
    print("\nsprints per split and share that missed:")
    print(summary.rename(columns={"size": "sprints", "mean": "missed"}).to_string())
    print("\nleakage check passed: held-out sprints start after all training sprints in their project")


def tune() -> None:
    dataset = pd.read_parquet(DATASET_PATH)
    train, val = dataset[dataset["split"] == "train"], dataset[dataset["split"] == "validation"]

    results = {
        "majority (always 'missed')": metrics(val, np.full(len(val), 0.5)),
        "health score (Step 4)": metrics(val, -val["health_score"].to_numpy()),
        "logistic regression": metrics(val, fit_predict(logistic_regression(), train, val)),
    }

    best, best_auc = None, -1.0
    keys = list(XGB_GRID)
    for values in itertools.product(*XGB_GRID.values()):
        params = dict(zip(keys, values))
        auc = metrics(val, fit_predict(xgboost(**params), train, val))["auc"]
        if auc > best_auc:
            best, best_auc = params, auc
    results["xgboost (best on validation)"] = metrics(val, fit_predict(xgboost(**best), train, val))

    print(f"Validation split: {val['sprint_id'].nunique()} sprints, {len(val)} rows\n")
    print(table(results))
    print(f"\nselected XGBoost settings: {best}")
    SELECTED_CONFIG_PATH.write_text(json.dumps({"xgboost": best, "validation": results}, indent=2, default=float))
    print(f"wrote {SELECTED_CONFIG_PATH}")


if __name__ == "__main__":
    commands = {"build": build, "tune": tune}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(f"usage: python run_risk_prediction.py [{'|'.join(commands)}]")
    commands[sys.argv[1]]()
