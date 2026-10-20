"""Sprint risk prediction: build the dataset, then tune and compare models on the validation split.

Run from components/sprint, after run_sprint_snapshots.py:
    python run_risk_prediction.py build      # dataset + split
    python run_risk_prediction.py tune       # compare models on VALIDATION, save the chosen XGBoost settings
    python run_risk_prediction.py freeze     # fix the chosen model + code fingerprint before testing
    python run_risk_prediction.py test       # the single run on the TEST split
    python run_risk_prediction.py final      # retrain the frozen model on train+validation, save it for the service
"""
import itertools
import json
import sys

import joblib
import numpy as np
import pandas as pd

from risk_prediction import charts
from risk_prediction.config import (DATA_DIR, DATASET_PATH, MODEL_PATH, MODEL_VERSION, RESULTS_DIR,
                                    SELECTED_CONFIG_PATH, TEST_RESULTS_PATH, XGB_GRID)
from risk_prediction.dataset import FEATURES, build_dataset
from risk_prediction.evaluate import bootstrap_auc, metrics, table
from risk_prediction.explain import global_importance
from risk_prediction.freeze import freeze, load_frozen_for_test
from risk_prediction.model import fit_predict, logistic_regression, xgboost

# Health score bands at-risk and critical count as "predicted to miss".
HEALTH_ALERT_BELOW = 70.0

# The main model. Chosen by the project owner to match the research proposal (XGBoost + SHAP);
# on validation logistic regression scored higher (0.898 vs 0.856 AUC), and the test run reports both.
PRIMARY_MODEL = "xgboost"


def _models(frozen: dict) -> dict:
    return {"logistic regression": logistic_regression(), "xgboost": xgboost(**frozen["xgboost"])}
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
        "majority (always 'missed')": metrics(val, np.full(len(val), 0.5), np.ones(len(val), int)),
        "health score (Step 4)": metrics(val, -val["health_score"].to_numpy(), val["health_score"] < HEALTH_ALERT_BELOW),
    }
    lr = fit_predict(logistic_regression(), train, val)
    results["logistic regression"] = metrics(val, lr, lr >= 0.5)

    best, best_auc = None, -1.0
    keys = list(XGB_GRID)
    for values in itertools.product(*XGB_GRID.values()):
        params = dict(zip(keys, values))
        auc = metrics(val, fit_predict(xgboost(**params), train, val))["auc"]
        if auc > best_auc:
            best, best_auc = params, auc
    xg = fit_predict(xgboost(**best), train, val)
    results["xgboost (best on validation)"] = metrics(val, xg, xg >= 0.5)

    print(f"Validation split: {val['sprint_id'].nunique()} sprints, {len(val)} rows\n")
    print(table(results))
    print(f"\nselected XGBoost settings: {best}")
    SELECTED_CONFIG_PATH.write_text(json.dumps({"xgboost": best, "validation": results}, indent=2, default=float))
    print(f"wrote {SELECTED_CONFIG_PATH}")


def freeze_cmd() -> None:
    if not SELECTED_CONFIG_PATH.exists():
        sys.exit("Run `python run_risk_prediction.py tune` first.")
    selected = json.loads(SELECTED_CONFIG_PATH.read_text())
    frozen = freeze({"primary_model": PRIMARY_MODEL, "xgboost": selected["xgboost"], "model_version": MODEL_VERSION})
    print(f"frozen: primary model = {frozen['primary_model']}, xgboost = {frozen['xgboost']}")
    print(f"code fingerprint {frozen['fingerprint'][:12]}... From now on, changing the code blocks the test run.")


def test() -> None:
    frozen = load_frozen_for_test()
    dataset = pd.read_parquet(DATASET_PATH)
    train, test_rows = dataset[dataset["split"] == "train"], dataset[dataset["split"] == "test"]
    scores = {
        "majority (always 'missed')": np.full(len(test_rows), 0.5),
        "health score (Step 4)": -test_rows["health_score"].to_numpy(),
    }
    predicted = {
        "majority (always 'missed')": np.ones(len(test_rows), int),
        "health score (Step 4)": (test_rows["health_score"] < HEALTH_ALERT_BELOW).to_numpy(),
    }
    fitted = {}
    for name, model in _models(frozen).items():
        scores[name] = fit_predict(model, train, test_rows)
        predicted[name] = scores[name] >= 0.5
        fitted[name] = model
    results = {name: metrics(test_rows, scores[name], predicted[name]) for name in scores}
    for name in scores:
        if not name.startswith("majority"):
            results[name]["auc_ci_low"], results[name]["auc_ci_high"] = bootstrap_auc(test_rows, scores[name])
    print(f"TEST split (run once): {test_rows['sprint_id'].nunique()} sprints, {len(test_rows)} rows\n")
    print(table(results))
    importance = global_importance(fitted[frozen["primary_model"]], test_rows)
    print(f"\nWhat drives the {frozen['primary_model']} predictions (mean |contribution|, log-odds):")
    print(importance.round(3).to_string())
    primary = frozen["primary_model"]
    chart_dir = RESULTS_DIR / "charts"
    chart_dir.mkdir(exist_ok=True)
    charts.roc_curves(test_rows, scores, results, chart_dir / "roc_curves.png")
    charts.auc_by_checkpoint(results, chart_dir / "auc_by_checkpoint.png")
    charts.confusion(test_rows, predicted[primary], primary, chart_dir / "confusion_matrix.png")
    charts.feature_importance(importance, primary, chart_dir / "feature_importance.png")
    print(f"\ncharts saved in {chart_dir}")
    TEST_RESULTS_PATH.write_text(json.dumps({"frozen": frozen, "test": results,
                                             "importance": importance.round(4).to_dict()}, indent=2, default=float))
    print(f"\nwrote {TEST_RESULTS_PATH}")


def final() -> None:
    if not TEST_RESULTS_PATH.exists():
        sys.exit("Run the test first, so the reported numbers come from the frozen settings.")
    frozen = json.loads(TEST_RESULTS_PATH.read_text())["frozen"]
    dataset = pd.read_parquet(DATASET_PATH)
    train = dataset[dataset["split"].isin(["train", "validation"])]
    model = _models(frozen)[frozen["primary_model"]]
    model.fit(train[FEATURES], train["missed"])
    joblib.dump({"model": model, "features": FEATURES, "model_version": frozen["model_version"],
                 "primary_model": frozen["primary_model"]}, MODEL_PATH)
    print(f"wrote {MODEL_PATH} ({frozen['primary_model']}, trained on {train['sprint_id'].nunique()} sprints)")


if __name__ == "__main__":
    commands = {"build": build, "tune": tune, "freeze": freeze_cmd, "test": test, "final": final}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(f"usage: python run_risk_prediction.py [{'|'.join(commands)}]")
    commands[sys.argv[1]]()
