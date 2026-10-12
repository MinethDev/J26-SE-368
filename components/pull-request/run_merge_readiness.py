"""
Command-line entry point for Merge-Readiness Decision Support.

This script lives in the component's source root, so the packages import
directly. Run from any directory:

    python components/pull-request/run_merge_readiness.py validate
    python components/pull-request/run_merge_readiness.py freeze
    python components/pull-request/run_merge_readiness.py test
    python components/pull-request/run_merge_readiness.py assess \
        --repo Altinn/altinn-studio --number 12345 [--as-of 2024-09-01T00:00:00Z]

The raw dataset path is taken from --raw-path, then the DEVINTEL_PR_RAW_DATA
environment variable, then the documented default.
"""

import argparse
import json

from merge_readiness import evaluate
from merge_readiness.assessment import assess
from merge_readiness.config import FROZEN_CONFIG_PATH
from merge_readiness.context import contexts_from_raw, decision_outcome
from preprocessing.loader import load_parquet
from reviewer_recommendation.config import get_raw_data_path


METRICS = ["roc_auc", "pr_auc_closed", "balanced_accuracy"]


def print_baseline_table(split_results):
    print(f"\n{'predictor':<48}{'subset':<8}{'n':>6}{'closed':>8}" + "".join(f"{m:>19}" for m in METRICS))

    for predictor, subsets in split_results.items():
        for subset, values in subsets.items():
            cells = "".join(
                f"{'n/a' if values[m] is None else format(values[m], '.3f'):>19}" for m in METRICS
            )
            print(f"{predictor:<48}{subset:<8}{values['n']:>6}{values['closed_share']:>8.3f}{cells}")


def print_descriptive(summary):
    print(f"\n{'group':<38}{'n':>6}  label shares")

    for group, values in summary.items():
        shares = ", ".join(f"{label}: {v['share']:.2f}" for label, v in values["labels"].items())
        print(f"{group:<38}{values['n']:>6}  {shares}")


def command_validate(args):
    raw_path = get_raw_data_path(args.raw_path)
    results = evaluate.run_validation(load_parquet(str(raw_path)), raw_path)
    baseline = results["auxiliary_baseline"]

    print("\nMERGE READINESS - VALIDATION")
    print(json.dumps(results["dataset"], indent=2))
    print_descriptive(results["checklist_descriptive"])
    print("\nAuxiliary merged-vs-closed baseline (not a readiness measure)")
    print("Primary variant:", baseline["primary_variant"])
    print("Selected C:", json.dumps(baseline["selected_c"]))

    for variant, weights in baseline["coefficients"].items():
        print(f"Coefficients [{variant}] (standardized, + = closed):", json.dumps(weights))
    print_baseline_table(baseline["validation"])
    print(f"\nResults: {results['results_path']}")


def command_freeze(args):
    record = evaluate.freeze_config()
    print(json.dumps(record, indent=2))
    print(f"Saved to: {FROZEN_CONFIG_PATH}")


def command_test(args):
    raw_path = get_raw_data_path(args.raw_path)
    results = evaluate.run_test(load_parquet(str(raw_path)), raw_path)

    print("\nMERGE READINESS - AUXILIARY BASELINE TEST (held-out, run once)")
    print_baseline_table(results["auxiliary_baseline"]["test"])
    print(f"\nResults: {results['results_path']}")


def command_assess(args):
    raw_path = get_raw_data_path(args.raw_path)
    contexts, _ = contexts_from_raw(load_parquet(str(raw_path)))
    context = next(
        (c for c in contexts if c.repo == args.repo and c.number == args.number), None
    )

    if context is None:
        raise SystemExit(f"PR not found: {args.repo}#{args.number}")

    as_of = args.as_of

    if as_of is None:
        outcome = decision_outcome(context)
        # Default for historical PRs: just before the final merge/close event.
        as_of = outcome.decision_time if outcome else None

    print(json.dumps(assess(context, as_of=as_of).to_dict(), indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--raw-path", help="Path to the raw Parquet shard.")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("validate", help="Descriptive statistics and auxiliary baseline on validation.")
    commands.add_parser("freeze", help="Freeze the validation-selected auxiliary settings.")
    commands.add_parser("test", help="Evaluate the frozen auxiliary settings on the test split (once).")

    assess_parser = commands.add_parser("assess", help="Readiness checklist for one dataset PR.")
    assess_parser.add_argument("--repo", required=True)
    assess_parser.add_argument("--number", type=int, required=True)
    assess_parser.add_argument("--as-of", help="ISO timestamp (default: just before the PR's final decision).")

    args = parser.parse_args()

    {
        "validate": command_validate,
        "freeze": command_freeze,
        "test": command_test,
        "assess": command_assess,
    }[args.command](args)


if __name__ == "__main__":
    main()
