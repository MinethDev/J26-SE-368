# DevIntel

**AI-Driven Integrated Development Analytics and Decision Support** (Project J26-SE-368)

DevIntel brings software-engineering data from GitHub, Jira, SonarQube and requirement documents into one place, and runs four AI components over it to give explainable, human-in-the-loop decision support.

| Component | Owner | Folder |
|---|---|---|
| Project Planning Intelligence | Vidusini W. M. O. | `components/planning/` |
| Sprint Intelligence | Wahalathanthri E. I. | `components/sprint/` |
| Software Quality Intelligence | Senura Virantha S.J. | `components/quality/` |
| Pull Request Intelligence | Perera W. M. M. | `components/pull-request/` |

## Architecture

```text
 GitHub   Jira   SonarQube   SRS upload        Data sources
    \       |        |         /
     Data Integration Layer                    platform/server/src/connectors/
  (connectors + common data model)             platform/server/src/models/
                 |
           AI Orchestrator                     platform/server/src/orchestrator/
   planning -> sprint -> quality -> pull-request   (each receives earlier insights: intelligence flow)
     |          |          |            |
  :8001      :8002      :8003        :8004     components/*/service/  (Python FastAPI)
                 |
       Knowledge Repository                    MongoDB "insights" collection
                 |
        Unified Dashboard                      platform/client/  (React)
```

Stack: **MERN** (MongoDB, Express, React, Node.js) for the platform, and **Python + FastAPI** for the AI components.

## Repository structure

```text
platform/server/     Express API: auth, connectors, orchestrator, knowledge repository
platform/client/     React dashboard (one page per component + overview + data sources)
components/<name>/   Each AI component: research code + service/ (FastAPI, Contract 3)
shared/schemas/      The contracts as JSON Schema (single source of truth)
docs/                CONTRACTS.md (read this first), GETTING_STARTED.md
docker-compose.yml   MongoDB and SonarQube for local development
```

## Start here

1. **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**: run the whole system on your machine.
2. **[docs/CONTRACTS.md](docs/CONTRACTS.md)**: the three agreements every component follows.
3. Your component's `service/README.md`: how to plug your model in.

## Branching rules

- `main`: stable, presentation-ready versions only
- `develop`: integration branch
- `feature/<component>`: your own work, merged into `develop` through a pull request with at least one teammate's review
- Never commit `.env` files, datasets (`*.parquet`) or `node_modules/`
