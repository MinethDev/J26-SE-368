"""DevIntel contracts 2 and 3 as Pydantic models.

Copied identically into every component service. Do not change one copy on its
own: the source of truth is shared/schemas/*.json and docs/CONTRACTS.md, and
the platform validates every insight against shared/schemas/insight.schema.json.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ComponentName = Literal["planning", "sprint", "quality", "pull-request"]
TargetType = Literal["project", "requirement", "sprint", "issue", "repository", "file", "pullRequest", "developer"]
Severity = Literal["info", "low", "medium", "high", "critical"]
EvidenceSource = Literal["github", "jira", "sonarqube", "upload", "component"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Target(_Strict):
    type: TargetType
    id: str = Field(min_length=1)
    label: Optional[str] = None


class Prediction(_Strict):
    label: str
    value: Any
    unit: Optional[str] = None


class ExplanationItem(_Strict):
    feature: str
    value: Any = None
    impact: float


class Evidence(_Strict):
    source: EvidenceSource
    ref: str
    note: Optional[str] = None


class Insight(_Strict):
    component: ComponentName
    type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    target: Target
    prediction: Prediction
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    severity: Severity = "info"
    explanation: list[ExplanationItem] = []
    recommendations: list[str] = []
    evidence: list[Evidence] = []
    modelVersion: str = Field(min_length=1)
    isStub: bool = False


class AnalyzeRequest(BaseModel):
    projectId: str
    context: dict[str, Any] = {}
    upstream: dict[str, list[dict[str, Any]]] = {}


class AnalyzeResponse(BaseModel):
    component: ComponentName
    modelVersion: str
    insights: list[Insight]


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    component: ComponentName
    modelVersion: str


def dump_insights(insights: list[Insight]) -> list[dict[str, Any]]:
    """Serialise insights without null optional fields (keeps payloads schema-clean)."""
    return [i.model_dump(exclude_none=True) for i in insights]
