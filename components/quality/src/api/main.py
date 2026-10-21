from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.preprocessing.extract_features import (
    extract_source_features,
)
from src.intelligence.generate_recommendations import (
    generate_file_recommendations,
    priority_from_risk,
)


FEATURES = [
    "total_lines",
    "blank_lines",
    "code_lines",
    "source_chars",
    "class_count",
    "interface_count",
    "enum_count",
    "import_count",
    "method_count",
    "if_count",
    "for_count",
    "while_count",
    "switch_count",
    "case_count",
    "catch_count",
    "return_count",
    "throw_count",
    "new_count",
    "decision_points",
    "approx_cyclomatic_complexity",
]


MODEL_PATH = Path(
    "models/defect_prediction/random_forest.joblib"
)


app = FastAPI(
    title="DevIntel Quality Intelligence API",
    version="0.1.0",
    description=(
        "Prototype API for AI-assisted software "
        "defect-risk intelligence."
    ),
)


model = None
explainer = None


class QualityAnalyzeRequest(BaseModel):
    project_id: str = Field(
        ...,
        min_length=1,
    )

    file_path: str = Field(
        ...,
        min_length=1,
    )

    source_code: str = Field(
        ...,
        min_length=1,
    )

    context: dict[str, Any] = Field(
        default_factory=dict
    )


def load_model():
    global model
    global explainer

    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"Model not found: {MODEL_PATH}"
        )

    model = joblib.load(
        MODEL_PATH
    )

    explainer = shap.TreeExplainer(
        model
    )


@app.on_event("startup")
def startup_event():
    load_model()


def get_positive_class_shap(
    shap_values,
    feature_count,
):
    if isinstance(shap_values, list):
        if len(shap_values) >= 2:
            values = np.asarray(
                shap_values[1]
            )
        else:
            values = np.asarray(
                shap_values[0]
            )
    else:
        values = np.asarray(
            shap_values
        )

    if values.ndim == 2:
        return values

    if values.ndim == 3:
        if values.shape[1] == feature_count:
            return values[:, :, 1]

        if values.shape[2] == feature_count:
            return values[1, :, :]

    raise RuntimeError(
        f"Unsupported SHAP dimensions: "
        f"{values.shape}"
    )


def assign_risk_band(probability):
    # Prototype display bands only.
    # These are not calibrated risk thresholds.

    if probability >= 0.75:
        return "very_high"

    if probability >= 0.50:
        return "high"

    if probability >= 0.25:
        return "moderate"

    return "low"


def explain_prediction(
    x,
    feature_values,
):
    raw_shap = explainer.shap_values(
        x
    )

    positive_shap = get_positive_class_shap(
        raw_shap,
        len(FEATURES),
    )

    contributions = pd.Series(
        positive_shap[0],
        index=FEATURES,
    )

    risk_drivers = contributions[
        contributions > 0
    ].sort_values(
        ascending=False
    ).head(5)

    risk_reducers = contributions[
        contributions < 0
    ].sort_values(
        ascending=True
    ).head(5)

    drivers = []

    for feature, shap_value in (
        risk_drivers.items()
    ):
        drivers.append({
            "feature": feature,
            "value": feature_values[
                feature
            ],
            "contribution": float(
                shap_value
            ),
        })

    reducers = []

    for feature, shap_value in (
        risk_reducers.items()
    ):
        reducers.append({
            "feature": feature,
            "value": feature_values[
                feature
            ],
            "contribution": float(
                shap_value
            ),
        })

    return drivers, reducers


def build_recommendation_row(
    drivers,
    probability,
):
    record = {
        "risk_probability": probability
    }

    for index, driver in enumerate(
        drivers,
        start=1,
    ):
        record[
            f"risk_driver_{index}_feature"
        ] = driver["feature"]

        record[
            f"risk_driver_{index}_shap"
        ] = driver["contribution"]

        record[
            f"risk_driver_{index}_value"
        ] = driver["value"]

    return pd.Series(record)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "component": "quality",
    }


@app.post("/api/quality/analyze")
def analyze_quality(
    request: QualityAnalyzeRequest,
):
    if model is None or explainer is None:
        raise HTTPException(
            status_code=503,
            detail="Quality model is unavailable.",
        )

    try:
        feature_values = (
            extract_source_features(
                request.source_code
            )
        )

        x = pd.DataFrame(
            [
                {
                    feature:
                        feature_values[feature]
                    for feature in FEATURES
                }
            ],
            columns=FEATURES,
        )

        probability = float(
            model.predict_proba(
                x
            )[0, 1]
        )

        prediction = int(
            model.predict(
                x
            )[0]
        )

        risk_band = assign_risk_band(
            probability
        )

        drivers, reducers = (
            explain_prediction(
                x,
                feature_values,
            )
        )

        recommendation_row = (
            build_recommendation_row(
                drivers,
                probability,
            )
        )

        recommendations = (
            generate_file_recommendations(
                recommendation_row
            )
        )

        return {
            "component": "quality",
            "status": "success",

            "results": {
                "projectId":
                    request.project_id,

                "file":
                    request.file_path,

                "predictedDefect":
                    bool(prediction),

                "riskProbability":
                    round(
                        probability,
                        6,
                    ),

                "riskBand":
                    risk_band,

                "priority":
                    priority_from_risk(
                        probability
                    ),
            },

            "explanations": {
                "riskDrivers": drivers,
                "riskReducers": reducers,
            },

            "recommendations":
                recommendations,

            "metadata": {
                "model":
                    "random_forest",

                "featureCount":
                    len(FEATURES),

                "threshold":
                    0.5,

                "probabilityCalibration":
                    "not_calibrated",

                "riskBandStatus":
                    "prototype",
            },
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc