from pathlib import Path
import argparse

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap


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
    keep = pd.Series(
        True,
        index=df.index,
    )

    for project, version in EXCLUDED_RELEASES:
        keep &= ~(
            (df["project"] == project)
            & (df["version"].astype(str) == version)
        )

    return df[keep].copy()


def get_positive_class_values(shap_values):
    """
    Normalize the output from different SHAP versions.

    Possible formats include:
    - list with one array per class
    - array: rows x features
    - array: rows x features x classes
    """

    if isinstance(shap_values, list):
        if len(shap_values) == 2:
            return np.asarray(shap_values[1])

        return np.asarray(shap_values[0])

    values = np.asarray(shap_values)

    if values.ndim == 3:
        # Rows x features x classes
        return values[:, :, 1]

    return values


def assign_risk_band(probability):
    """
    Descriptive prototype risk bands.

    These are not calibrated clinical-style thresholds.
    They are intended for prototype display.
    """

    if probability >= 0.75:
        return "very_high"

    if probability >= 0.50:
        return "high"

    if probability >= 0.25:
        return "moderate"

    return "low"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate SHAP explanations for the "
            "Random Forest defect-risk model."
        )
    )

    parser.add_argument(
        "dataset",
        type=Path,
        help="Feature-engineered dataset.",
    )

    parser.add_argument(
        "model",
        type=Path,
        help="Saved Random Forest model.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "evaluation/defect_prediction/"
            "explainability"
        ),
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=1000,
        help=(
            "Maximum number of test observations "
            "used for global SHAP analysis."
        ),
    )

    parser.add_argument(
        "--top-files",
        type=int,
        default=25,
        help=(
            "Number of highest-risk files to export "
            "with local explanations."
        ),
    )

    args = parser.parse_args()

    df = pd.read_csv(
        args.dataset
    )

    required = set(
        FEATURES
        + [
            "project",
            "version",
            "file",
            "bug",
        ]
    )

    missing = required - set(df.columns)

    if missing:
        raise SystemExit(
            f"Missing columns: {sorted(missing)}"
        )

    df = remove_excluded_releases(df)

    test_df = df[
        df["project"].isin(TEST_PROJECTS)
    ].copy()

    if test_df.empty:
        raise SystemExit(
            "No test observations found."
        )

    model = joblib.load(
        args.model
    )

    x_test = test_df[FEATURES]

    probabilities = model.predict_proba(
        x_test
    )[:, 1]

    predictions = model.predict(
        x_test
    )

    test_df["risk_probability"] = probabilities
    test_df["prediction"] = predictions
    test_df["risk_band"] = test_df[
        "risk_probability"
    ].apply(assign_risk_band)

    sample_size = min(
        args.sample_size,
        len(test_df),
    )

    # Fixed random_state for reproducibility.
    explanation_sample = test_df.sample(
        n=sample_size,
        random_state=42,
    )

    x_sample = explanation_sample[FEATURES]

    print("\n=== SHAP ANALYSIS ===")
    print(f"Test observations: {len(test_df)}")
    print(f"SHAP sample:       {len(x_sample)}")

    explainer = shap.TreeExplainer(
        model
    )

    raw_shap_values = explainer.shap_values(
        x_sample
    )

    positive_shap_values = get_positive_class_values(
        raw_shap_values
    )

    if positive_shap_values.shape != x_sample.shape:
        raise RuntimeError(
            "Unexpected SHAP dimensions: "
            f"{positive_shap_values.shape}; "
            f"expected {x_sample.shape}"
        )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Global feature importance based on mean absolute SHAP.
    mean_absolute_shap = np.abs(
        positive_shap_values
    ).mean(axis=0)

    importance_df = pd.DataFrame({
        "feature": FEATURES,
        "mean_abs_shap": mean_absolute_shap,
    }).sort_values(
        by="mean_abs_shap",
        ascending=False,
    )

    importance_path = (
        args.output_dir
        / "global_shap_importance.csv"
    )

    importance_df.to_csv(
        importance_path,
        index=False,
    )

    print("\n=== GLOBAL SHAP IMPORTANCE ===\n")
    print(
        importance_df.to_string(
            index=False,
            float_format=lambda value: f"{value:.6f}",
        )
    )

    # SHAP summary plot.
    shap.summary_plot(
        positive_shap_values,
        x_sample,
        feature_names=FEATURES,
        show=False,
    )

    plt.tight_layout()

    summary_plot_path = (
        args.output_dir
        / "shap_summary.png"
    )

    plt.savefig(
        summary_plot_path,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close()

    # SHAP bar plot.
    shap.summary_plot(
        positive_shap_values,
        x_sample,
        feature_names=FEATURES,
        plot_type="bar",
        show=False,
    )

    plt.tight_layout()

    bar_plot_path = (
        args.output_dir
        / "shap_importance_bar.png"
    )

    plt.savefig(
        bar_plot_path,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close()

    # Generate local explanations for highest-risk files.
    top_files = test_df.sort_values(
        by="risk_probability",
        ascending=False,
    ).head(
        args.top_files
    ).copy()

    top_x = top_files[FEATURES]

    top_raw_shap = explainer.shap_values(
        top_x
    )

    top_positive_shap = get_positive_class_values(
        top_raw_shap
    )

    local_records = []

    for row_position, (_, row) in enumerate(
        top_files.iterrows()
    ):
        contributions = pd.Series(
            top_positive_shap[row_position],
            index=FEATURES,
        )

        risk_drivers = contributions.sort_values(
            ascending=False
        ).head(5)

        risk_reducers = contributions.sort_values(
            ascending=True
        ).head(5)

        record = {
            "project": row["project"],
            "version": row["version"],
            "file": row["file"],
            "actual_bug": int(row["bug"]),
            "predicted_bug": int(row["prediction"]),
            "risk_probability": row[
                "risk_probability"
            ],
            "risk_band": row["risk_band"],
        }

        for rank, (feature, value) in enumerate(
            risk_drivers.items(),
            start=1,
        ):
            record[
                f"risk_driver_{rank}_feature"
            ] = feature

            record[
                f"risk_driver_{rank}_shap"
            ] = value

            record[
                f"risk_driver_{rank}_value"
            ] = row[feature]

        for rank, (feature, value) in enumerate(
            risk_reducers.items(),
            start=1,
        ):
            record[
                f"risk_reducer_{rank}_feature"
            ] = feature

            record[
                f"risk_reducer_{rank}_shap"
            ] = value

            record[
                f"risk_reducer_{rank}_value"
            ] = row[feature]

        local_records.append(
            record
        )

    local_df = pd.DataFrame(
        local_records
    )

    local_path = (
        args.output_dir
        / "top_risk_file_explanations.csv"
    )

    local_df.to_csv(
        local_path,
        index=False,
    )

    # Export predictions for later API/dashboard work.
    prediction_columns = [
        "project",
        "version",
        "file",
        "bug",
        "prediction",
        "risk_probability",
        "risk_band",
    ]

    predictions_path = (
        args.output_dir
        / "test_risk_predictions.csv"
    )

    test_df[prediction_columns].sort_values(
        by="risk_probability",
        ascending=False,
    ).to_csv(
        predictions_path,
        index=False,
    )

    print("\n=== OUTPUTS ===")
    print(f"Global importance: {importance_path}")
    print(f"SHAP summary:      {summary_plot_path}")
    print(f"SHAP bar chart:    {bar_plot_path}")
    print(f"Local explanations:{local_path}")
    print(f"Risk predictions:  {predictions_path}")


if __name__ == "__main__":
    main()