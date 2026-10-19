"""
DevIntel Software Quality Intelligence.

Live integration pipeline:

SonarQube quality snapshots
        +
GitHub pull-request churn
        |
        v
quality signals
        |
        v
evidence-based risk scoring
        |
        v
hotspot prioritisation
        |
        v
explanations + recommendations
        |
        v
DevIntel Insight[]
"""

from collections import defaultdict

from contract import (
    AnalyzeRequest,
    Evidence,
    ExplanationItem,
    Insight,
    Prediction,
    Target,
)


COMPONENT = "quality"
MODEL_VERSION = "quality-live-baseline-0.2"

TOP_N = 10


def _num(data: dict, key: str) -> float:
    """
    Safely convert a numeric value to float.
    """

    value = data.get(key)

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass

    return 0.0


def _normalise(value: float, scale: float) -> float:
    """
    Convert a raw metric into a bounded 0..1 signal.

    This is a prototype baseline normalisation, not
    a learned probability.
    """

    if value <= 0:
        return 0.0

    return min(value / scale, 1.0)


def _build_churn_map(
    pull_requests: list[dict],
) -> dict[str, dict[str, float]]:
    """
    Aggregate recent GitHub PR changes by file.

    Output:

    {
        "src/example.py": {
            "additions": ...,
            "deletions": ...,
            "churn": ...
        }
    }
    """

    churn = defaultdict(
        lambda: {
            "additions": 0.0,
            "deletions": 0.0,
            "churn": 0.0,
        }
    )

    for pull_request in pull_requests:

        files = pull_request.get(
            "files",
            []
        ) or []

        for file_info in files:

            path = (
                file_info.get("path")
                or file_info.get("filename")
            )

            if not path:
                continue

            additions = _num(
                file_info,
                "additions",
            )

            deletions = _num(
                file_info,
                "deletions",
            )

            churn[path]["additions"] += (
                additions
            )

            churn[path]["deletions"] += (
                deletions
            )

            churn[path]["churn"] += (
                additions + deletions
            )

    return dict(churn)


def _extract_signals(
    snapshot: dict,
    churn_map: dict,
) -> dict[str, float]:

    metrics = snapshot.get(
        "metrics"
    ) or {}

    issue_counts = snapshot.get(
        "issueCounts"
    ) or {}

    path = snapshot.get(
        "path"
    ) or ""

    file_churn = churn_map.get(
        path,
        {},
    )

    signals = {
        "ncloc": _num(
            metrics,
            "ncloc",
        ),

        "complexity": _num(
            metrics,
            "complexity",
        ),

        "bugs": _num(
            metrics,
            "bugs",
        ),

        "code_smells": _num(
            metrics,
            "code_smells",
        ),

        "vulnerabilities": _num(
            metrics,
            "vulnerabilities",
        ),

        "duplicated_lines_density": _num(
            metrics,
            "duplicated_lines_density",
        ),

        "coverage": _num(
            metrics,
            "coverage",
        ),

        "technical_debt": (
            _num(
                metrics,
                "sqale_index",
            )
            or _num(
                metrics,
                "technical_debt",
            )
        ),

        "blocker_issues": _num(
            issue_counts,
            "BLOCKER",
        ),

        "critical_issues": _num(
            issue_counts,
            "CRITICAL",
        ),

        "major_issues": _num(
            issue_counts,
            "MAJOR",
        ),

        "churn": _num(
            file_churn,
            "churn",
        ),
    }

    return signals


def _calculate_risk(
    signals: dict[str, float],
):
    """
    Evidence-based baseline risk score.

    IMPORTANT:
    This is deliberately a deterministic baseline,
    not the benchmark-trained Random Forest.

    The output is a relative prioritisation score.
    """

    factors = {
        "bugs": (
            _normalise(
                signals["bugs"],
                5,
            )
            * 0.25
        ),

        "vulnerabilities": (
            _normalise(
                signals["vulnerabilities"],
                3,
            )
            * 0.20
        ),

        "complexity": (
            _normalise(
                signals["complexity"],
                50,
            )
            * 0.15
        ),

        "code_smells": (
            _normalise(
                signals["code_smells"],
                20,
            )
            * 0.10
        ),

        "technical_debt": (
            _normalise(
                signals["technical_debt"],
                240,
            )
            * 0.10
        ),

        "duplication": (
            _normalise(
                signals[
                    "duplicated_lines_density"
                ],
                20,
            )
            * 0.05
        ),

        "churn": (
            _normalise(
                signals["churn"],
                300,
            )
            * 0.10
        ),

        "critical_issues": (
            _normalise(
                (
                    signals["blocker_issues"]
                    * 2
                    + signals[
                        "critical_issues"
                    ]
                ),
                5,
            )
            * 0.05
        ),
    }

    score = min(
        sum(factors.values()),
        1.0,
    )

    return score, factors


def _risk_level(
    score: float,
) -> str:

    if score >= 0.75:
        return "critical"

    if score >= 0.50:
        return "high"

    if score >= 0.25:
        return "medium"

    return "low"


def _recommendations(
    signals: dict[str, float],
    factors: dict[str, float],
) -> list[str]:

    recommendations = []

    ranked_factors = sorted(
        factors.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    for feature, impact in ranked_factors:

        if impact <= 0:
            continue

        if feature == "bugs":
            recommendations.append(
                "Investigate and resolve the "
                "file's reported reliability defects."
            )

        elif feature == "vulnerabilities":
            recommendations.append(
                "Prioritise the reported security "
                "vulnerabilities before release."
            )

        elif feature == "complexity":
            recommendations.append(
                "Review complex logic and consider "
                "extracting or simplifying methods."
            )

        elif feature == "code_smells":
            recommendations.append(
                "Review the reported code smells "
                "and address high-impact "
                "maintainability findings."
            )

        elif feature == "technical_debt":
            recommendations.append(
                "Review technical-debt items and "
                "plan remediation for the highest "
                "cost areas."
            )

        elif feature == "duplication":
            recommendations.append(
                "Inspect duplicated code and "
                "consider extracting shared logic."
            )

        elif feature == "churn":
            recommendations.append(
                "Review this frequently changed "
                "file carefully and strengthen "
                "regression testing around it."
            )

        elif feature == "critical_issues":
            recommendations.append(
                "Address blocker and critical "
                "quality findings before lower "
                "severity issues."
            )

        if len(recommendations) >= 3:
            break

    if (
        signals["coverage"] > 0
        and signals["coverage"] < 60
    ):
        recommendations.append(
            "Increase automated test coverage for "
            "this file or its containing module."
        )

    return recommendations[:4]


def _build_explanation(
    signals: dict[str, float],
    factors: dict[str, float],
) -> list[ExplanationItem]:

    ranked = sorted(
        factors.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    explanations = []

    for feature, impact in ranked:

        if impact <= 0:
            continue

        signal_key = feature

        if feature == "duplication":
            signal_key = (
                "duplicated_lines_density"
            )

        explanations.append(
            ExplanationItem(
                feature=feature,
                value=signals.get(
                    signal_key,
                    0.0,
                ),
                impact=float(impact),
            )
        )

        if len(explanations) >= 5:
            break

    return explanations


def _evidence(
    snapshot: dict,
    repository: dict | None,
    signals: dict[str, float],
) -> list[Evidence]:

    evidence = []

    reference = (
        snapshot.get("sourceId")
        or snapshot.get("path")
        or ""
    )

    evidence.append(
        Evidence(
            source="sonarqube",
            ref=str(reference),
            note=(
                "Static quality metrics used "
                "for hotspot analysis."
            ),
        )
    )

    if signals["churn"] > 0:

        repository_name = ""

        if repository:
            repository_name = (
                repository.get("fullName")
                or ""
            )

        evidence.append(
            Evidence(
                source="github",
                ref=(
                    repository_name
                    or snapshot.get(
                        "path",
                        "",
                    )
                ),
                note=(
                    "Recent pull-request changes "
                    "contributed to the churn signal."
                ),
            )
        )

    return evidence


def analyze(
    request: AnalyzeRequest,
) -> list[Insight]:

    repository = request.context.get(
        "repository"
    )

    snapshots = request.context.get(
        "qualitySnapshots",
        [],
    ) or []

    pull_requests = request.context.get(
        "pullRequests",
        [],
    ) or []

    if not snapshots:
        return []

    churn_map = _build_churn_map(
        pull_requests
    )

    analysed = []

    for snapshot in snapshots:

        path = snapshot.get("path")

        if not path:
            continue

        signals = _extract_signals(
            snapshot,
            churn_map,
        )

        score, factors = (
            _calculate_risk(
                signals
            )
        )

        analysed.append({
            "snapshot": snapshot,
            "signals": signals,
            "score": score,
            "factors": factors,
        })

    ranked = sorted(
        analysed,
        key=lambda item: item["score"],
        reverse=True,
    )[:TOP_N]

    insights = []

    for rank, item in enumerate(
        ranked,
        start=1,
    ):

        snapshot = item["snapshot"]
        signals = item["signals"]
        score = item["score"]
        factors = item["factors"]

        path = snapshot.get(
            "path"
        ) or str(rank)

        severity = _risk_level(
            score
        )

        insights.append(
            Insight(
                component=COMPONENT,

                type="quality-hotspot",

                title=(
                    f"Quality hotspot #{rank}: "
                    f"{path}"
                ),

                target=Target(
                    type="file",
                    id=path,
                    label=path,
                ),

                prediction=Prediction(
                    label=(
                        "Quality risk score"
                    ),
                    value=round(
                        score,
                        4,
                    ),
                    unit="0-1",
                ),

                confidence=None,

                severity=severity,

                explanation=(
                    _build_explanation(
                        signals,
                        factors,
                    )
                ),

                recommendations=(
                    _recommendations(
                        signals,
                        factors,
                    )
                ),

                evidence=_evidence(
                    snapshot,
                    repository,
                    signals,
                ),

                modelVersion=(
                    MODEL_VERSION
                ),

                isStub=False,
            )
        )

    return insights