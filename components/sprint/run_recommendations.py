"""Recommendations and sprint reports for the TEST sprints, halfway through each sprint.

Run from components/sprint, after run_risk_prediction.py final and run_productivity.py:
    python run_recommendations.py

Uses the final model (trained on train + validation), so the test sprints are still unseen.
Prints three example reports and, for each rule, how often it fired and how many of those sprints
really missed. That table is the evidence that a recommendation points at a real problem.
"""
import json

import joblib
import pandas as pd

from recommendations.config import HIGH_RISK
from recommendations.interventions import recommend
from recommendations.report import sprint_report
from risk_prediction.config import DATASET_PATH, MODEL_PATH
from risk_prediction.explain import explain_row

DATA_DIR = MODEL_PATH.parent.parent
VELOCITY_PATH = DATA_DIR / "productivity" / "sprint_velocity.parquet"
OUT_DIR = DATA_DIR / "recommendations"
CHECKPOINT = 0.5


def _velocity(row: pd.Series | None) -> dict | None:
    if row is None or pd.isna(row["overcommit_ratio"]):
        return None
    return {"ratio": row["overcommit_ratio"], "overcommitted": bool(row["overcommitted"]),
            "velocity": row["velocity"], "committed": row["committed"], "unit": row["unit"]}


def main() -> None:
    saved = joblib.load(MODEL_PATH)
    model, features = saved["model"], saved["features"]
    dataset = pd.read_parquet(DATASET_PATH)
    rows = dataset[(dataset["split"] == "test") & (dataset["checkpoint"] == CHECKPOINT)].reset_index(drop=True)
    velocity = pd.read_parquet(VELOCITY_PATH) if VELOCITY_PATH.exists() else None
    if velocity is None:
        print("(no productivity results found: run run_productivity.py first for over-commitment advice)\n")

    probabilities = model.predict_proba(rows[features].astype(float))[:, 1]
    results = []
    for (_, row), p in zip(rows.iterrows(), probabilities):
        drivers = explain_row(model, row, top=5)
        v = velocity.loc[row["sprint_id"]] if velocity is not None and row["sprint_id"] in velocity.index else None
        result = recommend(row.to_dict(), p, drivers, velocity=_velocity(v))
        results.append({"sprint_id": int(row["sprint_id"]), "missed": int(row["missed"]),
                        "drivers": drivers, **result})

    print(f"Test sprints, {CHECKPOINT:.0%} through the sprint: {len(results)}")
    by_risk = sorted(results, key=lambda r: -r["probability"])
    for pick in (by_risk[0], by_risk[len(by_risk) // 2], by_risk[-1]):
        row = rows[rows["sprint_id"] == pick["sprint_id"]].iloc[0]
        health = assess_from_row(row)
        report = sprint_report(f"test sprint {pick['sprint_id']}", pick, pick["drivers"], health)
        outcome = "MISSED" if pick["missed"] else "delivered"
        print("\n" + "=" * 70 + f"\n(what really happened: {outcome})\n" + report["text"])

    fired = pd.DataFrame([{"sprint_id": r["sprint_id"], "rule": rec["id"], "missed": r["missed"]}
                          for r in results for rec in r["recommendations"]])
    base = sum(r["missed"] for r in results) / len(results)
    print("\n" + "=" * 70)
    print(f"How often each recommendation fired (all test sprints missed: {base:.0%})")
    print("  rule                       sprints  share that missed")
    table = fired.groupby("rule")["missed"].agg(["size", "mean"]).sort_values("size", ascending=False)
    for rule, r in table.iterrows():
        print(f"  {rule:<26} {int(r['size']):>7}  {r['mean']:.0%}")
    high = [r for r in results if r["probability"] >= HIGH_RISK]
    with_action = sum(any(rec["id"] != "on-track" for rec in r["recommendations"]) for r in high)
    print(f"\nHigh-risk sprints with at least one action: {with_action} of {len(high)}")
    no_action = [r for r in results if not r["recommendations"]]
    print(f"Sprints with no recommendation at all: {len(no_action)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "test_recommendations.json").write_text(json.dumps(results, indent=2, default=float))
    print(f"\nwrote {OUT_DIR / 'test_recommendations.json'}")


def assess_from_row(row: pd.Series) -> dict:
    """The health score is already a feature; return it in the shape the report expects."""
    score = float(row["health_score"])
    band = "healthy" if score >= 70 else "at-risk" if score >= 40 else "critical"
    return {"score": score, "band": band}


if __name__ == "__main__":
    main()
