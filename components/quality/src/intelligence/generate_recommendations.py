from pathlib import Path
import argparse
import json

import pandas as pd


FEATURE_RECOMMENDATIONS = {
    "code_lines": {
        "category": "file_size",
        "action": "Review file size and responsibility boundaries.",
        "rationale": (
            "Code lines contributed positively to the model's "
            "defect-risk prediction."
        ),
    },

    "total_lines": {
        "category": "file_size",
        "action": (
            "Review whether the file contains multiple "
            "responsibilities that can be separated."
        ),
        "rationale": (
            "Total file size contributed positively to "
            "the predicted risk."
        ),
    },

    "source_chars": {
        "category": "file_size",
        "action": (
            "Inspect the file for opportunities to reduce "
            "unnecessary size or split responsibilities."
        ),
        "rationale": (
            "Source length contributed positively to the "
            "model prediction."
        ),
    },

    "method_count": {
        "category": "structure",
        "action": (
            "Review the number of methods and consider "
            "refactoring unrelated responsibilities."
        ),
        "rationale": (
            "Method count contributed positively to the "
            "predicted defect risk."
        ),
    },

    "import_count": {
        "category": "coupling_proxy",
        "action": (
            "Review dependencies and determine whether "
            "the file has excessive external responsibilities."
        ),
        "rationale": (
            "Import count contributed positively to the "
            "model prediction."
        ),
    },

    "return_count": {
        "category": "control_structure",
        "action": (
            "Review method structure and control flow for "
            "unnecessary complexity or fragmented logic."
        ),
        "rationale": (
            "Return-statement frequency contributed positively "
            "to the predicted risk."
        ),
    },

    "throw_count": {
        "category": "exception_handling",
        "action": (
            "Review exception paths and error-handling logic "
            "for consistency and maintainability."
        ),
        "rationale": (
            "Exception-throwing structure contributed "
            "positively to predicted risk."
        ),
    },

    "approx_cyclomatic_complexity": {
        "category": "complexity",
        "action": (
            "Review complex control-flow regions and consider "
            "simplifying or extracting logic."
        ),
        "rationale": (
            "Approximate cyclomatic complexity contributed "
            "positively to predicted defect risk."
        ),
    },

    "decision_points": {
        "category": "complexity",
        "action": (
            "Inspect branching and decision-heavy regions "
            "for simplification and focused testing."
        ),
        "rationale": (
            "Decision-point count contributed positively "
            "to the model prediction."
        ),
    },

    "if_count": {
        "category": "complexity",
        "action": (
            "Review conditional-heavy logic and consider "
            "simplifying complex branches."
        ),
        "rationale": (
            "Conditional structure contributed positively "
            "to predicted risk."
        ),
    },

    "for_count": {
        "category": "control_structure",
        "action": (
            "Review loop-heavy processing for complexity, "
            "edge cases and test coverage."
        ),
        "rationale": (
            "Loop structure contributed positively to "
            "the risk prediction."
        ),
    },

    "while_count": {
        "category": "control_structure",
        "action": (
            "Review loop termination conditions and "
            "complex loop logic."
        ),
        "rationale": (
            "Loop structure contributed positively to "
            "the risk prediction."
        ),
    },

    "catch_count": {
        "category": "exception_handling",
        "action": (
            "Review exception-handling paths and verify "
            "that failures are handled consistently."
        ),
        "rationale": (
            "Exception-handling structure contributed "
            "positively to predicted risk."
        ),
    },

    "new_count": {
        "category": "dependency_creation",
        "action": (
            "Review object creation and dependency management "
            "for excessive responsibilities or tight coupling."
        ),
        "rationale": (
            "Object-creation frequency contributed positively "
            "to the model prediction."
        ),
    },

    "blank_lines": {
        "category": "source_structure",
        "action": (
            "Review overall file organization together with "
            "the stronger structural indicators."
        ),
        "rationale": (
            "Source-layout characteristics influenced the "
            "model prediction; this signal should not be "
            "interpreted causally in isolation."
        ),
    },
}

ZERO_REQUIRES_NO_ACTION = {
    "throw_count",
    "catch_count",
    "if_count",
    "for_count",
    "while_count",
    "switch_count",
    "case_count",
    "new_count",
    "import_count",
    "method_count",
}


def priority_from_risk(probability):
    if probability >= 0.75:
        return "critical"

    if probability >= 0.50:
        return "high"

    if probability >= 0.25:
        return "medium"

    return "low"


def generate_file_recommendations(row):

    feature_value = row.get(value_column)

    if (
        feature in ZERO_REQUIRES_NO_ACTION
        and (
            pd.isna(feature_value)
            or float(feature_value) <= 0
        )
    ):

    recommendations = []

    seen_categories = set()

    for rank in range(1, 6):
        feature_column = (
            f"risk_driver_{rank}_feature"
        )

        shap_column = (
            f"risk_driver_{rank}_shap"
        )

        value_column = (
            f"risk_driver_{rank}_value"
        )

        feature = row.get(feature_column)

        if pd.isna(feature):
            continue

        feature = str(feature)

        shap_value = row.get(shap_column)

        # Only use risk-increasing explanations.
        if pd.isna(shap_value) or shap_value <= 0:
            continue

        rule = FEATURE_RECOMMENDATIONS.get(
            feature
        )

        if rule is None:
            continue

        category = rule["category"]

        # Avoid returning several near-identical
        # recommendations for correlated features.
        if category in seen_categories:
            continue

        seen_categories.add(category)

        recommendations.append({
            "rank": len(recommendations) + 1,
            "category": category,
            "evidence_feature": feature,
            "evidence_value": row.get(
                value_column
            ),
            "shap_contribution": shap_value,
            "action": rule["action"],
            "rationale": rule["rationale"],
        })

    return recommendations


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate evidence-linked baseline "
            "recommendations from risk predictions "
            "and SHAP explanations."
        )
    )

    parser.add_argument(
        "explanations",
        type=Path,
        help=(
            "CSV produced by explain_model.py "
            "containing local SHAP explanations."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "evaluation/defect_prediction/"
            "intelligence/"
            "quality_intelligence.csv"
        ),
    )

    args = parser.parse_args()

    df = pd.read_csv(
        args.explanations
    )

    required = {
        "project",
        "version",
        "file",
        "actual_bug",
        "predicted_bug",
        "risk_probability",
        "risk_band",
    }

    missing = required - set(df.columns)

    if missing:
        raise SystemExit(
            f"Missing columns: {sorted(missing)}"
        )

    records = []

    for _, row in df.iterrows():
        recommendations = (
            generate_file_recommendations(row)
        )

        probability = float(
            row["risk_probability"]
        )

        record = {
            "project": row["project"],
            "version": row["version"],
            "file": row["file"],
            "actual_bug": int(
                row["actual_bug"]
            ),
            "predicted_bug": int(
                row["predicted_bug"]
            ),
            "risk_probability": probability,
            "risk_band": row["risk_band"],
            "priority": priority_from_risk(
                probability
            ),
            "recommendation_count":
                len(recommendations),
            "recommendations":
                json.dumps(
                    recommendations,
                    ensure_ascii=False,
                ),
        }

        records.append(record)

    result = pd.DataFrame(
        records
    )

    result = result.sort_values(
        by="risk_probability",
        ascending=False,
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        args.output,
        index=False,
    )

    print("\n=== QUALITY INTELLIGENCE ===")
    print(f"Files processed: {len(result)}")

    print("\nPriority distribution:")
    print(
        result["priority"]
        .value_counts()
    )

    print("\nTop risk files:\n")

    print(
        result[
            [
                "project",
                "version",
                "file",
                "risk_probability",
                "priority",
                "recommendation_count",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )

    print(
        f"\nOutput written to: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()