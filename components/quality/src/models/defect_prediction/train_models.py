from pathlib import Path
import argparse
import json

import joblib
import pandas as pd

from sklearn.ensemble import (
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import LeaveOneGroupOut


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


RANDOM_FOREST_CONFIGS = [
    {
        "n_estimators": 300,
        "max_depth": None,
        "min_samples_leaf": 1,
        "max_features": "sqrt",
        "class_weight": "balanced",
    },
    {
        "n_estimators": 300,
        "max_depth": 10,
        "min_samples_leaf": 2,
        "max_features": "sqrt",
        "class_weight": "balanced",
    },
    {
        "n_estimators": 500,
        "max_depth": 15,
        "min_samples_leaf": 4,
        "max_features": 0.7,
        "class_weight": "balanced",
    },
]


GRADIENT_BOOSTING_CONFIGS = [
    {
        "n_estimators": 100,
        "learning_rate": 0.05,
        "max_depth": 2,
        "min_samples_leaf": 5,
        "subsample": 1.0,
    },
    {
        "n_estimators": 200,
        "learning_rate": 0.05,
        "max_depth": 2,
        "min_samples_leaf": 10,
        "subsample": 0.8,
    },
    {
        "n_estimators": 200,
        "learning_rate": 0.03,
        "max_depth": 3,
        "min_samples_leaf": 10,
        "subsample": 0.8,
    },
]


def remove_excluded_releases(df):
    keep = pd.Series(True, index=df.index)

    for project, version in EXCLUDED_RELEASES:
        keep &= ~(
            (df["project"] == project)
            & (df["version"].astype(str) == version)
        )

    return df[keep].copy()


def build_model(model_type, config):
    if model_type == "Random Forest":
        return RandomForestClassifier(
            **config,
            random_state=42,
            n_jobs=-1,
        )

    if model_type == "Gradient Boosting":
        return GradientBoostingClassifier(
            **config,
            random_state=42,
        )

    raise ValueError(f"Unsupported model type: {model_type}")


def calculate_metrics(y_true, predictions, probabilities):
    return {
        "accuracy": accuracy_score(
            y_true,
            predictions,
        ),
        "precision": precision_score(
            y_true,
            predictions,
            zero_division=0,
        ),
        "recall": recall_score(
            y_true,
            predictions,
            zero_division=0,
        ),
        "f1": f1_score(
            y_true,
            predictions,
            zero_division=0,
        ),
        "roc_auc": roc_auc_score(
            y_true,
            probabilities,
        ),
        "pr_auc": average_precision_score(
            y_true,
            probabilities,
        ),
    }


def evaluate_configuration(
    model_type,
    config,
    x,
    y,
    groups,
):
    logo = LeaveOneGroupOut()

    fold_results = []

    for fold_number, (train_index, validation_index) in enumerate(
        logo.split(x, y, groups),
        start=1,
    ):
        x_fold_train = x.iloc[train_index]
        y_fold_train = y.iloc[train_index]

        x_fold_validation = x.iloc[validation_index]
        y_fold_validation = y.iloc[validation_index]

        held_out_project = groups.iloc[
            validation_index
        ].iloc[0]

        # AUC-based metrics require both classes in validation data.
        if y_fold_validation.nunique() < 2:
            print(
                f"Skipping fold {fold_number}: "
                f"{held_out_project} has a single validation class."
            )
            continue

        model = build_model(
            model_type,
            config,
        )

        model.fit(
            x_fold_train,
            y_fold_train,
        )

        predictions = model.predict(
            x_fold_validation
        )

        probabilities = model.predict_proba(
            x_fold_validation
        )[:, 1]

        metrics = calculate_metrics(
            y_fold_validation,
            predictions,
            probabilities,
        )

        metrics.update({
            "held_out_project": held_out_project,
            "fold": fold_number,
        })

        fold_results.append(metrics)

    if not fold_results:
        raise RuntimeError(
            f"No valid folds completed for {model_type}"
        )

    fold_df = pd.DataFrame(fold_results)

    summary = {
        "model": model_type,
        "config": json.dumps(
            config,
            sort_keys=True,
        ),
        "folds": len(fold_df),
        "mean_accuracy": fold_df["accuracy"].mean(),
        "std_accuracy": fold_df["accuracy"].std(),
        "mean_precision": fold_df["precision"].mean(),
        "std_precision": fold_df["precision"].std(),
        "mean_recall": fold_df["recall"].mean(),
        "std_recall": fold_df["recall"].std(),
        "mean_f1": fold_df["f1"].mean(),
        "std_f1": fold_df["f1"].std(),
        "mean_roc_auc": fold_df["roc_auc"].mean(),
        "std_roc_auc": fold_df["roc_auc"].std(),
        "mean_pr_auc": fold_df["pr_auc"].mean(),
        "std_pr_auc": fold_df["pr_auc"].std(),
    }

    return summary, fold_df


def find_best_configuration(
    model_type,
    configurations,
    x_train,
    y_train,
    groups,
):
    summaries = []
    all_folds = []

    for config_index, config in enumerate(
        configurations,
        start=1,
    ):
        print("\n" + "=" * 72)
        print(
            f"{model_type} configuration "
            f"{config_index}/{len(configurations)}"
        )
        print(config)
        print("=" * 72)

        summary, fold_df = evaluate_configuration(
            model_type=model_type,
            config=config,
            x=x_train,
            y=y_train,
            groups=groups,
        )

        summary["config_index"] = config_index
        summaries.append(summary)

        fold_df["model"] = model_type
        fold_df["config_index"] = config_index
        fold_df["config"] = json.dumps(
            config,
            sort_keys=True,
        )

        all_folds.append(fold_df)

        print(
            f"Mean PR-AUC:  "
            f"{summary['mean_pr_auc']:.4f}"
        )
        print(
            f"Mean ROC-AUC: "
            f"{summary['mean_roc_auc']:.4f}"
        )
        print(
            f"Mean F1:      "
            f"{summary['mean_f1']:.4f}"
        )

    summary_df = pd.DataFrame(summaries)

    # Primary selection metric: mean validation PR-AUC.
    # F1 and ROC-AUC are tie-breakers.
    summary_df = summary_df.sort_values(
        by=[
            "mean_pr_auc",
            "mean_f1",
            "mean_roc_auc",
        ],
        ascending=False,
    ).reset_index(drop=True)

    best_row = summary_df.iloc[0]

    best_config = json.loads(
        best_row["config"]
    )

    folds_df = pd.concat(
        all_folds,
        ignore_index=True,
    )

    return best_config, summary_df, folds_df


def evaluate_on_test(
    model_type,
    config,
    x_train,
    y_train,
    x_test,
    y_test,
):
    model = build_model(
        model_type,
        config,
    )

    model.fit(
        x_train,
        y_train,
    )

    predictions = model.predict(
        x_test
    )

    probabilities = model.predict_proba(
        x_test
    )[:, 1]

    metrics = calculate_metrics(
        y_test,
        predictions,
        probabilities,
    )

    metrics.update({
        "model": model_type,
        "config": json.dumps(
            config,
            sort_keys=True,
        ),
    })

    matrix = confusion_matrix(
        y_test,
        predictions,
    )

    return model, metrics, matrix


def print_test_result(metrics, matrix):
    print("\nMetrics:")

    for metric in [
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "pr_auc",
    ]:
        print(
            f"{metric:12s}: "
            f"{metrics[metric]:.4f}"
        )

    print("\nConfusion matrix:")
    print(matrix)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Select Random Forest and Gradient Boosting "
            "models using project-grouped cross-validation."
        )
    )

    parser.add_argument(
        "dataset",
        type=Path,
        help="Feature-engineered dataset.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "evaluation/defect_prediction/"
            "model_comparison"
        ),
    )

    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(
            "models/defect_prediction"
        ),
    )

    args = parser.parse_args()

    df = pd.read_csv(
        args.dataset
    )

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
            f"Missing columns: {sorted(missing)}"
        )

    df = remove_excluded_releases(df)

    train_df = df[
        df["project"].isin(TRAIN_PROJECTS)
    ].copy()

    test_df = df[
        df["project"].isin(TEST_PROJECTS)
    ].copy()

    train_projects = set(
        train_df["project"].unique()
    )

    test_projects = set(
        test_df["project"].unique()
    )

    overlap = train_projects & test_projects

    if overlap:
        raise SystemExit(
            f"Project leakage detected: {sorted(overlap)}"
        )

    if train_df.empty or test_df.empty:
        raise SystemExit(
            "Training or test dataset is empty."
        )

    print("\n=== EXPERIMENT DATA ===")
    print(f"Training rows: {len(train_df)}")
    print(f"Test rows:     {len(test_df)}")
    print(
        f"Training projects: "
        f"{sorted(train_projects)}"
    )
    print(
        f"Locked test projects: "
        f"{sorted(test_projects)}"
    )

    x_train = train_df[FEATURES]
    y_train = train_df["bug"]
    groups = train_df["project"]

    x_test = test_df[FEATURES]
    y_test = test_df["bug"]

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.model_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    model_searches = [
        (
            "Random Forest",
            RANDOM_FOREST_CONFIGS,
            "random_forest",
        ),
        (
            "Gradient Boosting",
            GRADIENT_BOOSTING_CONFIGS,
            "gradient_boosting",
        ),
    ]

    final_results = []

    for model_type, configs, filename_prefix in model_searches:
        print("\n" + "#" * 72)
        print(f"MODEL SELECTION: {model_type}")
        print("#" * 72)

        (
            best_config,
            cv_summary,
            fold_results,
        ) = find_best_configuration(
            model_type=model_type,
            configurations=configs,
            x_train=x_train,
            y_train=y_train,
            groups=groups,
        )

        cv_summary.to_csv(
            args.output_dir
            / f"{filename_prefix}_cv_summary.csv",
            index=False,
        )

        fold_results.to_csv(
            args.output_dir
            / f"{filename_prefix}_cv_folds.csv",
            index=False,
        )

        print("\nSelected configuration:")
        print(best_config)

        print("\n" + "-" * 72)
        print(f"LOCKED TEST EVALUATION: {model_type}")
        print("-" * 72)

        model, metrics, matrix = evaluate_on_test(
            model_type=model_type,
            config=best_config,
            x_train=x_train,
            y_train=y_train,
            x_test=x_test,
            y_test=y_test,
        )

        print_test_result(
            metrics,
            matrix,
        )

        final_results.append(metrics)

        joblib.dump(
            model,
            args.model_dir
            / f"{filename_prefix}.joblib",
        )

    final_results_df = pd.DataFrame(
        final_results
    )

    baseline_path = Path(
        "evaluation/defect_prediction/"
        "baseline_results.csv"
    )

    if baseline_path.exists():
        baseline_df = pd.read_csv(
            baseline_path
        )

        # Keep Logistic Regression for the final comparison.
        logistic = baseline_df[
            baseline_df["model"]
            == "Logistic Regression"
        ].copy()

        if not logistic.empty:
            logistic["config"] = (
                "StandardScaler + class_weight=balanced"
            )

            comparison_df = pd.concat(
                [
                    logistic,
                    final_results_df,
                ],
                ignore_index=True,
            )
        else:
            comparison_df = final_results_df
    else:
        comparison_df = final_results_df

    ordered_columns = [
        "model",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "pr_auc",
        "config",
    ]

    comparison_df = comparison_df[
        [
            column
            for column in ordered_columns
            if column in comparison_df.columns
        ]
    ]

    comparison_df = comparison_df.sort_values(
        by=[
            "pr_auc",
            "f1",
            "roc_auc",
        ],
        ascending=False,
    ).reset_index(drop=True)

    output_path = (
        args.output_dir
        / "final_test_comparison.csv"
    )

    comparison_df.to_csv(
        output_path,
        index=False,
    )

    print("\n" + "=" * 72)
    print("FINAL LOCKED-TEST COMPARISON")
    print("=" * 72)

    print(
        comparison_df.to_string(
            index=False,
            float_format=lambda value: f"{value:.4f}",
        )
    )

    print(f"\nResults written to: {args.output_dir}")
    print(f"Models written to:  {args.model_dir}")


if __name__ == "__main__":
    main()