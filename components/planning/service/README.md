# planning service (port 8001)

The platform's AI Orchestrator calls this service. It currently returns **stub** insights
(marked with a dashed "stub" badge on the dashboard) so the whole system works end to end today.

## Files

| File | Edit it? | Purpose |
|---|---|---|
| `analysis.py` | **Yes** | Your logic. `analyze(request)` receives the context and returns a list of `Insight` |
| `app.py` | Rarely | HTTP endpoints `GET /health` and `POST /analyze` (Contract 3) |
| `contract.py` | **No** | Identical in every service. The shared output format (Contract 2) |

## Run on its own

```powershell
cd components/planning/service
pip install -r requirements.txt
uvicorn app:app --reload --port 8001
```

Open `http://127.0.0.1:8001/docs` to send a test request from the browser.

## Replacing the stub with your model

1. Train and evaluate your model in `../research/`. Save the trained model (e.g. `joblib.dump`) to a file the service can load; don't commit large files.
2. In `analysis.py`, load the model **once** at module level, then in `analyze()` build features from `request.context`, predict, and compute explanations (e.g. SHAP values).
3. Return one `Insight` per thing you predict about. Put SHAP values in `explanation`, suggested actions in `recommendations`, and set `isStub=False`.
4. Bump `MODEL_VERSION` whenever the model or its settings change.
5. Add new Python packages to `requirements.txt`.
6. Check you still follow the contracts: `python components/test_contract.py` from the repo root.

What arrives in `request.context` is listed at the top of `analysis.py` and in `docs/CONTRACTS.md`. If you need more data, change `platform/server/src/orchestrator/contextBuilders.js` and tell the team.
