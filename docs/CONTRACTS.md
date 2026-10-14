# DevIntel Contracts

Three agreements that let four people build in parallel without blocking each other.
If you need to change one, raise it with the whole team first: every component depends on them.

| # | Contract | Lives in | Who uses it |
|---|---|---|---|
| 1 | Common data model | `platform/server/src/models/` | Connectors write it, orchestrator reads it |
| 2 | Insight format | `shared/schemas/insight.schema.json` | Every component returns it, the dashboard renders it |
| 3 | Component API | `shared/schemas/analyze.schema.json` | Orchestrator calls it, every component implements it |

---

## Contract 1: Common data model

All tools are normalised into these MongoDB collections. Every document has:

- `projectId`: the DevIntel project it belongs to
- `source`: `github` | `jira` | `sonarqube` | `upload`
- `sourceId`: the ID in the original tool (unique per `projectId` + `source`), so re-running a sync updates instead of duplicating

| Collection | Filled by | Key fields |
|---|---|---|
| `projects` | Dashboard / seed | `key`, `name`, `github {owner, repo}`, `jira {boardId}`, `sonarqube {projectKey}` |
| `developers` | GitHub, Jira | `login`, `name`, `email` |
| `repositories` | GitHub | `fullName`, `defaultBranch` |
| `pullrequests` | GitHub | `number`, `title`, `body`, `author`, `state`, `createdAt`, `mergedAt`, `closedAt`, `files[]`, `reviews[]`, `additions`, `deletions` |
| `issues` | Jira | `key`, `summary`, `type`, `status`, `storyPoints`, `assignee`, `sprintId`, `createdAt`, `resolvedAt` |
| `sprints` | Jira | `name`, `state`, `startDate`, `endDate`, `completeDate`, `goal` |
| `qualitysnapshots` | SonarQube | `path`, `metrics {ncloc, complexity, ...}`, `issueCounts`, `snapshotAt` |
| `requirements` | Upload | `fileName`, `rawText`, `items[]` |

## Contract 2: Insight format

Every component returns a list of insights. Full definition: `shared/schemas/insight.schema.json`.

```json
{
  "component": "pull-request",
  "type": "reviewer-recommendation",
  "title": "Recommended reviewers for PR #123",
  "target": { "type": "pullRequest", "id": "123", "label": "Fix login timeout" },
  "prediction": { "label": "Top reviewers", "value": ["alice", "bob", "carol"] },
  "confidence": 0.82,
  "severity": "info",
  "explanation": [
    { "feature": "author_affinity", "value": 0.9, "impact": 0.41 },
    { "feature": "activity", "value": 0.6, "impact": 0.15 }
  ],
  "recommendations": ["Request a review from alice: reviewed 12 of this author's PRs"],
  "evidence": [{ "source": "github", "ref": "MinethDev/demo#123" }],
  "modelVersion": "rr-v1",
  "isStub": false
}
```

Rules:
- `explanation` is how we show explainability on every page. Use SHAP values for ML models, or signal weights for rule/ranking methods.
- `recommendations` are suggestions only. The human accepts or rejects them in the dashboard (stored as `feedback`).
- The platform adds `projectId`, `runId`, `createdAt` and `feedback`. Components must **not** send those.
- The orchestrator validates every insight against the schema. Invalid insights are rejected and the error is shown on the run status, so check the server log if your insights don't appear.

## Contract 3: Component API

Each component is a FastAPI service with two endpoints:

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | `{ "status": "ok", "component": "...", "modelVersion": "..." }` |
| `POST` | `/analyze` | `{ "component": "...", "modelVersion": "...", "insights": [ ... ] }` |

`POST /analyze` request body:

```json
{
  "projectId": "devintel-demo",
  "context": { "...": "component-specific, see below" },
  "upstream": { "planning": [ "...insights produced earlier in this run..." ] }
}
```

### What each component receives in `context`

| Component | Port | `context` contents | `upstream` |
|---|---|---|---|
| Planning | 8001 | `requirements[]` (uploaded documents with `rawText`), `issues[]` (historical, for calibration) | none |
| Sprint | 8002 | `sprints[]`, `issues[]` | `planning` insights (the planning baseline) |
| Quality | 8003 | `repository`, `qualitySnapshots[]`, `pullRequests[]` (recent, for churn) | none |
| Pull Request | 8004 | `repository`, `pullRequests[]` (with files and reviews) | `quality` insights (file hotspots) |

The order of a run is **planning → sprint → quality → pull-request**, so each component can use the insights of the ones before it. These two links (planning → sprint, quality → pull-request) are the first implementation of the intelligence flow.
