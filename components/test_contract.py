"""Checks that every component service follows Contract 3 and returns valid Contract 2 insights.

Run from the repository root (no running services needed):
    python -m pytest components/test_contract.py      # or: python components/test_contract.py
"""

import importlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent
SCHEMA = json.loads((ROOT.parent / "shared" / "schemas" / "insight.schema.json").read_text(encoding="utf-8"))
REQUIRED = set(SCHEMA["required"])
ALLOWED = set(SCHEMA["properties"])

SAMPLE_CONTEXT = {
    "planning": {"requirements": [{"sourceId": "doc1", "fileName": "srs.txt", "rawText": "The system shall..."}], "issues": [{"storyPoints": 3}, {"storyPoints": 5}]},
    "sprint": {"sprints": [{"sourceId": "s1", "name": "Sprint 1", "state": "active"}], "issues": [{"sprintId": "s1", "storyPoints": 5, "statusCategory": "Done"}, {"sprintId": "s1", "storyPoints": 3, "statusCategory": "In Progress"}]},
    "quality": {"qualitySnapshots": [{"sourceId": "f1", "path": "src/a.py", "metrics": {"complexity": 12, "bugs": 1, "code_smells": 4}}]},
    "pull-request": {"pullRequests": [{"repo": "o/r", "number": 1, "title": "Fix bug", "files": [{"path": "src/a.py"}], "reviews": []}], "history": []},
}


def load_app(component: str):
    service_dir = ROOT / component / "service"
    for name in ("app", "analysis", "contract"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(service_dir))
    try:
        return importlib.import_module("app").app
    finally:
        sys.path.remove(str(service_dir))


def check(component: str) -> None:
    client = TestClient(load_app(component))
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["component"] == component, health

    res = client.post("/analyze", json={"projectId": "test", "context": SAMPLE_CONTEXT[component], "upstream": {}})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["component"] == component and body["insights"], body
    for insight in body["insights"]:
        assert REQUIRED <= set(insight), f"missing {REQUIRED - set(insight)}"
        assert set(insight) <= ALLOWED, f"unexpected {set(insight) - ALLOWED}"
        assert insight["component"] == component


def test_planning():
    check("planning")


def test_sprint():
    check("sprint")


def test_quality():
    check("quality")


def test_pull_request():
    check("pull-request")


if __name__ == "__main__":
    for c in SAMPLE_CONTEXT:
        check(c)
        print(f"{c}: ok")
