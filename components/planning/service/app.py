"""HTTP layer for the planning component (Contract 3). You normally don't need to edit this file:
put your model logic in analysis.py.

Run:  uvicorn app:app --reload --port PORT   (from this folder; see README.md)
"""

from fastapi import FastAPI

from analysis import COMPONENT, MODEL_VERSION, analyze
from contract import AnalyzeRequest, AnalyzeResponse, Health

app = FastAPI(title=f"DevIntel {COMPONENT} intelligence", version=MODEL_VERSION)


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(component=COMPONENT, modelVersion=MODEL_VERSION)


@app.post("/analyze", response_model=AnalyzeResponse, response_model_exclude_none=True)
def analyze_endpoint(request: AnalyzeRequest) -> AnalyzeResponse:
    insights = analyze(request)
    return AnalyzeResponse(component=COMPONENT, modelVersion=MODEL_VERSION, insights=insights)
