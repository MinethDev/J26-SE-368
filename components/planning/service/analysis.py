"""Project Planning Intelligence (owner: Vidusini W. M. O.)

Trained multi-target planning models:
  1. Delay Classification (LogisticRegression pipeline): predicts project delay risk + feature attribution.
  2. Delay Percentage Regression (RandomForestRegressor pipeline): estimates schedule slippage percentage.
  3. Cost Overrun Regression (RandomForestRegressor pipeline): estimates budget overrun percentage.

Returns Contract 2 Insight objects conforming to shared/schemas/insight.schema.json.
"""

from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any
import sys
import os
import joblib
import numpy as np
import pandas as pd

from contract import (
    AnalyzeRequest,
    Evidence,
    ExplanationItem,
    Insight,
    Prediction,
    Severity,
    Target,
)

COMPONENT = "planning"
MODEL_VERSION = "planning-v0.2"

# ── Feature Engineering helper ─────────────────────────────────────────────
def add_features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["Tasks_per_Day"]     = d["Tasks_Planned"] / d["Planned_Duration_Days"]
    d["Tasks_per_Member"]  = d["Tasks_Planned"] / d["Team_Size"]
    d["Budget_per_Task"]   = d["Planned_Budget"] / d["Tasks_Planned"]
    d["Budget_per_Day"]    = d["Planned_Budget"] / d["Planned_Duration_Days"]
    d["Budget_per_Member"] = d["Planned_Budget"] / d["Team_Size"]
    if "Risk_Level" in d.columns:
        risk_map = {"Low": 1, "Medium": 2, "High": 3}
        d["Risk_Score"] = d["Risk_Level"].map(risk_map).fillna(2)
    d["Scope_Intensity"]   = d["Tasks_Planned"] / (d["Planned_Budget"] / 1_000_000 + 1e-9)
    return d

# Inject add_features into __main__ for joblib unpickling compatibility
import __main__
__main__.add_features = add_features


def _find_model_file() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent.parent / "models" / "planning_models_final.pkl",
        Path(__file__).resolve().parent / "planning_models_final.pkl",
        Path(__file__).resolve().parents[3] / "models_planning_models_final.pkl",
        Path("components/planning/models/planning_models_final.pkl"),
        Path("models_planning_models_final.pkl"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_bundle():
    path = _find_model_file()
    if not path:
        print("[planning] Warning: No trained model file found. Falling back to baseline.")
        return None
    try:
        bundle = joblib.load(path)
        print(f"[planning] Loaded model bundle from {path} (version: {bundle.get('model_version')})")
        return bundle
    except Exception as e:
        print(f"[planning] Error loading model bundle from {path}: {e}")
        return None


MODEL_BUNDLE = _load_bundle()
if MODEL_BUNDLE and "model_version" in MODEL_BUNDLE:
    MODEL_VERSION = MODEL_BUNDLE["model_version"]

# Range of the projects the models were trained on (it_project_data.csv, describe() in train1.ipynb).
# A newer bundle can carry its own ranges under "feature_ranges" ({feature: {"min": .., "max": ..}}).
TRAINING_RANGES = {
    "Team_Size": (3, 21),
    "Planned_Duration_Days": (45, 180),
    "Tasks_Planned": (45, 351),
    "Planned_Budget": (354_535, 10_722_998),
}
if MODEL_BUNDLE and isinstance(MODEL_BUNDLE.get("feature_ranges"), dict):
    for _f, _r in MODEL_BUNDLE["feature_ranges"].items():
        if _f in TRAINING_RANGES and {"min", "max"} <= set(_r):
            TRAINING_RANGES[_f] = (_r["min"], _r["max"])


def _out_of_range(params: dict[str, Any]) -> list[str]:
    """Inputs outside the training range: the models would be extrapolating there."""
    notes = []
    for feature, (low, high) in TRAINING_RANGES.items():
        value = params.get(feature)
        if value is not None and not (low <= value <= high):
            notes.append(f"{feature.replace('_', ' ').lower()} {value:g} (trained on {low:g}-{high:g})")
    return notes


def _regressors_are_separate(bundle: dict) -> bool:
    """The two regressors must be separately trained models. In the v0.2 bundle both pipelines
    share one RandomForest object (trained last on cost overrun), so the delay-% model is not usable."""
    try:
        return bundle["delay_pct_regressor"].named_steps["model"] is not bundle["cost_overrun_regressor"].named_steps["model"]
    except Exception:
        return False


def _extract_planning_parameters(ctx: dict[str, Any], project_id: str) -> dict[str, Any]:
    """Extracts or derives planning features from context (issues, sprints, project, requirements)."""
    issues = ctx.get("issues", [])
    sprints = ctx.get("sprints", [])
    project = ctx.get("project") or {}
    requirements = ctx.get("requirements", [])
    custom_params = ctx.get("planningParams") or project.get("planningSettings") or {}

    # 1. Tasks Planned
    tasks_planned = custom_params.get("tasksPlanned") or custom_params.get("Tasks_Planned")
    if not tasks_planned:
        tasks_planned = len(issues) if issues else 20
    tasks_planned = max(int(tasks_planned), 1)

    # 2. Team Size
    team_size = custom_params.get("teamSize") or custom_params.get("Team_Size")
    if not team_size:
        assignees = {i.get("assignee") for i in issues if i.get("assignee")}
        team_size = len(assignees) if assignees else 4
    team_size = max(int(team_size), 1)

    # 3. Planned Duration Days
    planned_duration = custom_params.get("plannedDurationDays") or custom_params.get("Planned_Duration_Days")
    if not planned_duration:
        valid_sprints = [s for s in sprints if s.get("startDate") and s.get("endDate")]
        if valid_sprints:
            try:
                starts = [datetime.fromisoformat(str(s["startDate"]).replace("Z", "+00:00")) for s in valid_sprints]
                ends = [datetime.fromisoformat(str(s["endDate"]).replace("Z", "+00:00")) for s in valid_sprints]
                days = (max(ends) - min(starts)).days
                planned_duration = max(days, 14)
            except Exception:
                planned_duration = len(sprints) * 14
        else:
            planned_duration = 42  # default 3 sprints of 2 weeks
    planned_duration = max(float(planned_duration), 1.0)

    # 4. Planned Budget
    planned_budget = custom_params.get("plannedBudget") or custom_params.get("Planned_Budget")
    if not planned_budget:
        # Benchmark estimation: $350/day per developer
        planned_budget = round(team_size * planned_duration * 350.0, 2)
    planned_budget = max(float(planned_budget), 1000.0)

    # 5. Project Type
    project_type = custom_params.get("projectType") or custom_params.get("Project_Type")
    if not project_type:
        name_desc = f"{project.get('name', '')} {project.get('description', '')}".lower()
        if "mobile" in name_desc or "android" in name_desc or "ios" in name_desc:
            project_type = "Mobile"
        elif "ai" in name_desc or "ml" in name_desc or "intelligence" in name_desc:
            project_type = "AI/ML"
        elif "cloud" in name_desc or "devops" in name_desc:
            project_type = "Cloud"
        elif "data" in name_desc or "analytics" in name_desc:
            project_type = "Data"
        elif "erp" in name_desc:
            project_type = "ERP"
        else:
            project_type = "Web"

    # 6. Department
    department = custom_params.get("department") or custom_params.get("Department") or "Development"

    # 7. Month
    month = custom_params.get("month") or custom_params.get("Month")
    if not month:
        now = datetime.utcnow()
        month = now.strftime("%b")

    return {
        "Project_Type": str(project_type),
        "Department": str(department),
        "Month": str(month),
        "Team_Size": int(team_size),
        "Planned_Duration_Days": float(planned_duration),
        "Tasks_Planned": int(tasks_planned),
        "Planned_Budget": float(planned_budget),
    }


def _human_feature_name(feat: str) -> str:
    name_map = {
        "Scope_Intensity": "Scope intensity (tasks per budget unit)",
        "Tasks_per_Day": "Tasks planned per day",
        "Tasks_per_Member": "Tasks per team member",
        "Budget_per_Task": "Allocated budget per task",
        "Budget_per_Day": "Budget allocation per day",
        "Budget_per_Member": "Budget per team member",
        "Planned_Duration_Days": "Planned duration (days)",
        "Tasks_Planned": "Total planned tasks",
        "Planned_Budget": "Planned budget",
        "Team_Size": "Assigned team size",
        "Project_Type_Web": "Project type: Web",
        "Project_Type_Mobile": "Project type: Mobile",
        "Project_Type_AI/ML": "Project type: AI/ML",
        "Project_Type_Cloud": "Project type: Cloud",
        "Project_Type_Data": "Project type: Data",
        "Project_Type_ERP": "Project type: ERP",
        "Department_Development": "Department: Development",
        "Department_Testing": "Department: Testing",
        "Department_Infrastructure": "Department: Infrastructure",
        "Department_Data": "Department: Data",
    }
    return name_map.get(feat, feat.replace("_", " "))


def _generate_recommendations(proba: float, delay_pct: float, cost_pct: float, params: dict[str, Any], top_drivers: list[tuple[str, float]]) -> list[str]:
    recs = []
    tpm = params["Tasks_Planned"] / max(params["Team_Size"], 1)
    tpd = params["Tasks_Planned"] / max(params["Planned_Duration_Days"], 1)

    if proba >= 0.5:
        recs.append(f"High risk of project delivery delay ({proba:.0%}). Buffer sprint timelines and re-evaluate backlog priorities.")
    elif proba >= 0.3:
        recs.append(f"Moderate delay risk ({proba:.0%}). Track sprint milestone burndowns closely.")

    if tpm > 7.0:
        recs.append(f"Workload concentration: average {tpm:.1f} tasks per developer. Consider adding team capacity or scoping down sprint deliverables.")
    if tpd > 1.2:
        recs.append(f"High throughput expectation: {tpd:.1f} tasks required per calendar day. Break complex stories into smaller demonstrable deliverables.")

    if delay_pct > 10.0:
        extra_days = round(delay_pct / 100.0 * params["Planned_Duration_Days"], 0)
        recs.append(f"Schedule slippage estimate is {delay_pct:.1f}% (~{extra_days:.0f} days extra). Schedule an early architecture and scope review.")

    if cost_pct > 10.0:
        recs.append(f"Estimated budget overrun is {cost_pct:.1f}%. Review third-party API and infrastructure commitments.")

    recs.append("Planning intelligence provides decision support. Verify estimates against team velocity.")
    return recs[:4]


def analyze(request: AnalyzeRequest) -> list[Insight]:
    ctx = request.context
    requirements = ctx.get("requirements", [])
    issues = ctx.get("issues", [])
    project = ctx.get("project") or {}
    project_label = project.get("name") or request.projectId

    # 1. Historical baseline (feeds Sprint Intelligence)
    points = [i["storyPoints"] for i in issues if isinstance(i.get("storyPoints"), (int, float))]
    avg_points = round(mean(points), 2) if points else None

    baseline_insight = Insight(
        component=COMPONENT,
        type="planning-baseline",
        title="Planning baseline from historical issues",
        target=Target(type="project", id=request.projectId, label=project_label),
        prediction=Prediction(label="Average story points per issue", value=avg_points, unit="points"),
        confidence=None,
        severity="info",
        explanation=[ExplanationItem(feature="historical_issues", value=len(points), impact=1.0)] if points else [],
        recommendations=["Planning baseline feeds Sprint Intelligence to calibrate unestimated backlog items."],
        evidence=[Evidence(source="jira", ref=f"issues:{len(issues)}", note=f"Derived from {len(points)} estimated Jira issues")] if points else [],
        modelVersion=MODEL_VERSION,
        isStub=False,
    )

    insights = [baseline_insight]

    # 2. If model bundle is available, execute multi-target prediction
    if MODEL_BUNDLE:
        try:
            params = _extract_planning_parameters(ctx, request.projectId)
            df_raw = pd.DataFrame([params])
            features_list = MODEL_BUNDLE.get("features", [])
            df_fe = add_features(df_raw)[features_list]

            # 2a. Delay Classification
            clf = MODEL_BUNDLE.get("delay_classifier")
            proba = float(clf.predict_proba(df_fe)[0, 1])

            out_of_range = _out_of_range(params)

            # Determine severity
            if proba >= 0.7:
                delay_sev: Severity = "critical"
            elif proba >= 0.45:
                delay_sev: Severity = "high"
            elif proba >= 0.25:
                delay_sev: Severity = "medium"
            else:
                delay_sev: Severity = "info"

            # Compute linear explanations
            explanation_items = []
            try:
                prep = clf.named_steps["prep"]
                model = clf.named_steps["model"]
                x_tf = prep.transform(df_fe)
                cat_names = prep.named_transformers_["cat"].get_feature_names_out(MODEL_BUNDLE["cat_features"]).tolist()
                all_feat_names = cat_names + MODEL_BUNDLE["num_features"]
                contributions = x_tf[0] * model.coef_[0]
                top_indices = np.argsort(np.abs(contributions))[::-1][:4]

                for idx in top_indices:
                    fname = all_feat_names[idx]
                    impact = float(round(contributions[idx], 3))
                    human_name = _human_feature_name(fname)
                    # Extract original value if available
                    val = None
                    if fname in df_fe.columns:
                        val = round(float(df_fe[fname].iloc[0]), 2)
                    explanation_items.append(
                        ExplanationItem(feature=human_name, value=val, impact=impact)
                    )
            except Exception as ex:
                print(f"[planning] Explanation generation warning: {ex}")

            # 2b. Delay % Regressor
            delay_reg = MODEL_BUNDLE.get("delay_pct_regressor")
            delay_pct = float(round(delay_reg.predict(df_fe)[0], 2)) if delay_reg and _regressors_are_separate(MODEL_BUNDLE) else 0.0

            # 2c. Cost Overrun Regressor
            cost_reg = MODEL_BUNDLE.get("cost_overrun_regressor")
            cost_pct = float(round(cost_reg.predict(df_fe)[0], 2)) if cost_reg else 0.0

            recommendations = _generate_recommendations(
                proba, delay_pct, cost_pct, params, []
            )
            if out_of_range:
                # Outside the training data the probability is an extrapolation: say so, don't overstate it.
                if delay_sev in ("high", "critical"):
                    delay_sev = "medium"
                recommendations = [
                    "This project is outside the range the model was trained on ("
                    + "; ".join(out_of_range)
                    + "). Treat this estimate as indicative only."
                ] + recommendations[:3]

            evidence_items = [
                Evidence(
                    source="jira",
                    ref=f"issues:{params['Tasks_Planned']}",
                    note=f"Team size: {params['Team_Size']} members, Planned duration: {int(params['Planned_Duration_Days'])} days"
                )
            ]

            # Delay Risk Insight
            insights.append(
                Insight(
                    component=COMPONENT,
                    type="planning-delay-risk",
                    title="Project Delivery Delay Risk",
                    target=Target(type="project", id=request.projectId, label=project_label),
                    prediction=Prediction(label="Probability of project delay", value=round(proba * 100, 1), unit="%"),
                    confidence=None if out_of_range else float(round(max(proba, 1.0 - proba), 2)),
                    severity=delay_sev,
                    explanation=explanation_items,
                    recommendations=recommendations,
                    evidence=evidence_items,
                    modelVersion=MODEL_VERSION,
                    isStub=False,
                )
            )

            # Schedule Forecast Insight (only when the delay-% regressor is its own trained model)
            extra_days = round(delay_pct / 100.0 * params["Planned_Duration_Days"], 1)
            duration_sev: Severity = "high" if delay_pct >= 20.0 else ("medium" if delay_pct >= 10.0 else "info")
            if _regressors_are_separate(MODEL_BUNDLE):
                insights.append(
                    Insight(
                        component=COMPONENT,
                        type="planning-duration-forecast",
                        title="Estimated Schedule Slippage Forecast",
                        target=Target(type="project", id=request.projectId, label=project_label),
                        prediction=Prediction(label="Estimated schedule slippage", value=delay_pct, unit="%"),
                        confidence=None,
                        severity=duration_sev,
                        explanation=[],
                        recommendations=[
                            f"Expected slippage of ~{extra_days} days beyond planned {int(params['Planned_Duration_Days'])} days.",
                            "Establish bi-weekly sprint velocity checkpoints to prevent compounding schedule variance."
                        ],
                        evidence=evidence_items,
                        modelVersion=MODEL_VERSION,
                        isStub=False,
                    )
                )

            # Cost Overrun Insight
            extra_cost = round(cost_pct / 100.0 * params["Planned_Budget"], 2)
            cost_sev: Severity = "high" if cost_pct >= 20.0 else ("medium" if cost_pct >= 10.0 else "info")
            insights.append(
                Insight(
                    component=COMPONENT,
                    type="planning-budget-forecast",
                    title="Estimated Budget Variance Forecast",
                    target=Target(type="project", id=request.projectId, label=project_label),
                    prediction=Prediction(label="Estimated budget variance", value=cost_pct, unit="%"),
                    confidence=None,
                    severity=cost_sev,
                    explanation=[],
                    recommendations=[
                        f"Projected cost variance is ~${extra_cost:,.2f} on a ${params['Planned_Budget']:,.2f} budget.",
                        "Track infrastructure and contractor expenditure against sprint milestones."
                    ],
                    evidence=evidence_items,
                    modelVersion=MODEL_VERSION,
                    isStub=False,
                )
            )
        except Exception as e:
            print(f"[planning] Inference failed: {e}")
            import traceback
            traceback.print_exc()

    # 3. Requirement documents insights
    for doc in requirements:
        raw_text = doc.get("rawText", "")
        insights.append(
            Insight(
                component=COMPONENT,
                type="requirements-received",
                title=f"Requirement document received: {doc.get('fileName', 'document')}",
                target=Target(type="requirement", id=str(doc.get("sourceId", doc.get("fileName", "doc"))), label=doc.get("fileName")),
                prediction=Prediction(label="Extracted characters of text", value=len(raw_text)),
                severity="info",
                recommendations=["Functional and non-functional requirements extracted for planning scope analysis."],
                modelVersion=MODEL_VERSION,
                isStub=False,
            )
        )

    return insights
