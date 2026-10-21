# sprint service (port 8002)

The platform's AI Orchestrator calls this service. It runs the full Sprint Intelligence pipeline
(see [../README.md](../README.md)) on the platform's Jira data and returns real insights (`isStub` false).

## Files

| File | Purpose |
|---|---|
| `analysis.py` | Builds insights from `live/pipeline.py`: risk, health, burndown, workload, report |
| `app.py` | HTTP endpoints `GET /health` and `POST /analyze` (Contract 3) |
| `contract.py` | Identical in every service. The shared output format (Contract 2) |

## Run on its own

```powershell
cd components/sprint/service
pip install -r requirements.txt
uvicorn app:app --reload --port 8002
```

Open `http://127.0.0.1:8002/docs` to send a test request. `GET /health` shows the model version:
`sprint-risk-v1` when the trained model is found, `sprint-health-rules-v1` when it falls back to the
health score.

## Model file

Loaded once, from the first of: `DEVINTEL_SPRINT_MODEL`, `../data/risk/risk_model.joblib` (a local
training run), `../models/risk_model.joblib` (the released model in Git).

## Checks

```powershell
python -m unittest discover -s tests      # from components/sprint: 34 tests
python components/test_contract.py        # from the repo root: all four services follow the contracts
```
