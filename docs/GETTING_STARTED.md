# Getting started

Run the whole DevIntel system on your own machine. Commands are shown for Windows PowerShell; on macOS/Linux use `python3` and `source .venv/bin/activate`.

## 1. Install once

- **Node.js 20+** and **Python 3.11+**
- **MongoDB**: either Docker Desktop (`docker compose up -d mongo` from the repo root), or MongoDB Community Server installed locally. Both listen on `localhost:27017`.

## 2. Start the component services (terminal 1)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r components/planning/service/requirements.txt
python components/run_all_services.py
```

This starts all four FastAPI services on ports 8001-8004. Each has interactive API docs at `http://127.0.0.1:<port>/docs`.
To run only yours: `python components/run_all_services.py pull-request`.

## 3. Start the platform API (terminal 2)

```powershell
cd platform/server
npm install
copy .env.example .env        # then edit .env (tokens are optional for a first run)
npm run seed -- --sample      # demo accounts, demo project and a small SAMPLE dataset
npm run dev
```

The API runs on `http://localhost:4000` (check `http://localhost:4000/api/health`).

Demo accounts created by the seed:

| Role | Email | Password |
|---|---|---|
| Manager (can sync and run analyses) | `manager@devintel.local` | `devintel-manager` |
| Developer (can view and give feedback) | `developer@devintel.local` | `devintel-developer` |

Remove the sample data any time with `npm run seed -- --clear-sample`, once real data is synced.

## 4. Start the dashboard (terminal 3)

```powershell
cd platform/client
npm install
npm run dev
```

Open `http://localhost:5173`, sign in as the manager and press **Run analysis** on the Overview page.

## 5. Connect real data

Put tokens in `platform/server/.env`, then use the **Data sources** page:

| Source | What you need |
|---|---|
| GitHub | `GITHUB_TOKEN` (fine-grained token, read-only access to the repo). Set owner/repo on the Data sources page. |
| Jira | A free Jira Cloud site with a Scrum board. `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and the story-points field id. Set the board ID on the Data sources page. |
| SonarQube | `docker compose --profile quality up -d`, open `http://localhost:9000` (admin/admin), create a project, scan your repo with `sonar-scanner`, create a user token and set `SONARQUBE_TOKEN`. Set the project key on the Data sources page. |
| Requirements | Upload a `.pdf`, `.txt` or `.md` SRS on the Data sources page. |

## 6. Tests

```powershell
cd platform/server; npm test                 # insight contract validation
python components/test_contract.py           # every service follows Contracts 2 and 3
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Server exits with "could not connect to MongoDB" | Start MongoDB (step 1) |
| Component card shows a grey dot / run says `ECONNREFUSED` | That component's service isn't running (step 2) |
| Run says "invalid insight(s) rejected" | Your `/analyze` output breaks Contract 2; the run details in the API response list the exact field |
| Sync fails with 401/403 | Token missing or lacks access; check `.env` and restart the server |
