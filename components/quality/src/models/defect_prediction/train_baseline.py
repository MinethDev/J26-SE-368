from pathlib import Path
import argparse

import pandas as pd

from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
)


FEATURES = [
    "total_lines",
    "blank_lines",
    "code_lines",
    "source_chars",
    "class_count",
    "interface_count",
    "enum_count",
    "import_count",
    "method_count",
    "if_count",
    "for_count",
    "while_count",
    "switch_count",
    "case_count",
    "catch_count",
    "return_count",
    "throw_count",
    "new_count",
    "decision_points",
    "approx_cyclomatic_complexity",
]


TRAIN_PROJECTS = {
    "ant",
    "camel",
    "jedit",
    "log4j",
    "lucene",
    "poi",
    "synapse",
    "velocity",
}


TEST_PROJECTS = {
    "xalan",
    "xerces",
}


EXCLUDED_RELEASES = {
    ("jedit", "4.3"),
    ("log4j", "1.2"),
    ("xalan", "2.7"),
}


def remove_excluded_releases(df):
    keep = pd.Series(True, index=df.index)

    for project, version in EXCLUDED_RELEASES:
        keep &= ~(
            (df["project"] == project)
            & (df["version"].astype(str) == version)
        )

    return df[keep].copy()


def evaluate_model(name, model, x_test, y_test):
    predictions = model.predict(x_test)

    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(x_test)[:, 1]
    else:
        probabilities = None

    result = {
        "model": name,
        "accuracy": accuracy_score(
            y_test,
            predictions,
        ),
        "precision": precision_score(
            y_test,
            predictions,
            zero_division=0,
        ),
        "recall": recall_score(
            y_test,
            predictions,
            zero_division=0,
        ),
        "f1": f1_score(
            y_test,
            predictions,
            zero_division=0,
        ),
    }

    if probabilities is not None:
        result["roc_auc"] = roc_auc_score(
            y_test,
            probabilities,
        )

        result["pr_auc"] = average_precision_score(
            y_test,
            probabilities,
        )

    matrix = confusion_matrix(
        y_test,
        predictions,
    )

    return result, matrix


def print_distribution(name, df):
    print(f"\n=== {name} ===")
    print(f"Rows: {len(df)}")
    print(f"Projects: {sorted(df['project'].unique())}")

    print("\nTarget counts:")
    print(df["bug"].value_counts().sort_index())

    print("\nTarget percentages:")
    print(
        df["bug"]
        .value_counts(normalize=True)
        .sort_index()
        .mul(100)
        .round(2)
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Train baseline defect-prediction models "
            "using project-level holdout."
        )
    )

    parser.add_argument(
        "dataset",
        type=Path,
        help="Feature-engineered CSV dataset.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "evaluation/defect_prediction/"
            "baseline_results.csv"
        ),
    )

    args = parser.parse_args()

    df = pd.read_csv(args.dataset)

    required_columns = set(
        FEATURES
        + [
            "project",
            "version",
            "bug",
        ]
    )

    missing = required_columns - set(df.columns)

    if missing:
        raise SystemExit(
            f"Dataset missing columns: {sorted(missing)}"
        )

    print("Original observations:", len(df))

    df = remove_excluded_releases(df)

    print(
        "Observations after excluding flagged releases:",
        len(df),
    )

    train_df = df[
        df["project"].isin(TRAIN_PROJECTS)
    ].copy()

    test_df = df[
        df["project"].isin(TEST_PROJECTS)
    ].copy()

    if train_df.empty:
        raise SystemExit("Training dataset is empty.")

    if test_df.empty:
        raise SystemExit("Test dataset is empty.")

    overlap = set(
        train_df["project"].unique()
    ) & set(
        test_df["project"].unique()
    )

    if overlap:
        raise SystemExit(
            f"Project leakage detected: {sorted(overlap)}"
        )

    print_distribution(
        "TRAINING DATA",
        train_df,
    )

    print_distribution(
        "TEST DATA",
        test_df,
    )

    x_train = train_df[FEATURES]
    y_train = train_df["bug"]

    x_test = test_df[FEATURES]
    y_test = test_df["bug"]

    models = {
        "Dummy Majority": DummyClassifier(
            strategy="most_frequent"
        ),

        "Dummy Stratified": DummyClassifier(
            strategy="stratified",
            random_state=42,
        ),

        "Logistic Regression": Pipeline(
            steps=[
                (
                    "scaler",
                    StandardScaler(),
                ),
                (
                    "model",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                        random_state=42,
                    ),
                ),
            ]
        ),
    }

    results = []

    for name, model in models.items():
        print("\n" + "=" * 70)
        print(name)
        print("=" * 70)

        model.fit(
            x_train,
            y_train,
        )

        result, matrix = evaluate_model(
            name,
            model,
            x_test,
            y_test,
        )

        results.append(result)

        print("\nMetrics:")

        for key, value in result.items():
            if key == "model":
                continue

            print(
                f"{key:12s}: {value:.4f}"
            )

        print("\nConfusion matrix:")
        print(matrix)

    results_df = pd.DataFrame(results)

    print("\n=== MODEL COMPARISON ===\n")

    print(
        results_df.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    results_df.to_csv(
        args.output,
        index=False,
    )

    print(
        f"\nResults written to: {args.output}"
    )


if __name__ == "__main__":
    main()