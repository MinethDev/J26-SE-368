"""
Command-line entry point for Reviewer Recommendation.

This script lives in the component's source root, so its own directory is on
the import path and the packages import directly. Run from any directory:

    python components/pull-request/run_reviewer_recommendation.py validate
    python components/pull-request/run_reviewer_recommendation.py freeze
    python components/pull-request/run_reviewer_recommendation.py test
    python components/pull-request/run_reviewer_recommendation.py recommend \
        --repo Altinn/altinn-studio --author someone --title "Fix login form"

The raw dataset path is taken from --raw-path, then the DEVINTEL_PR_RAW_DATA
environment variable, then the documented default.
"""

import argparse
import json
from datetime import datetime, timezone

from preprocessing.loader import load_parquet
from reviewer_recommendation import evaluate
from reviewer_recommendation.config import (
    FROZEN_CONFIG_PATH,
    SELECTED_CONFIG_PATH,
    get_raw_data_path,
)
from reviewer_recommendation.recommender import RecommenderConfig, ReviewerRecommender


TABLE_METRICS = ["mrr", "hit@1", "hit@3", "hit@5", "recall@3"]


def print_table(results):
    print(f"\n{'ranker':<24}" + "".join(f"{m:>10}" for m in TABLE_METRICS) + f"{'macro mrr':>12}")

    for name, summary in results["results"].items():
        overall = summary["overall"]
        print(
            f"{name:<24}"
            + "".join(f"{overall[m]:>10.3f}" for m in TABLE_METRICS)
            + f"{summary['macro']['mrr']:>12.3f}"
        )


def command_validate(args):
    raw_path = get_raw_data_path(args.raw_path)
    results = evaluate.run_validation(load_parquet(str(raw_path)), raw_path)

    print("\nREVIEWER RECOMMENDATION - VALIDATION")
    print(json.dumps(results["dataset"], indent=2))
    print("Candidate coverage:", json.dumps(results["candidate_coverage"]))
    print("Selected config:", json.dumps(results["selected_config"]))
    print_table(results)
    print(f"\nResults: {results['results_path']}")
    print(f"Selected config saved to: {SELECTED_CONFIG_PATH}")


def command_freeze(args):
    record = evaluate.freeze_config()

    print("\nSettings frozen for test evaluation:")
    print(json.dumps(record, indent=2))
    print(f"Saved to: {FROZEN_CONFIG_PATH}")


def command_test(args):
    raw_path = get_raw_data_path(args.raw_path)
    results = evaluate.run_test(load_parquet(str(raw_path)), raw_path)

    print("\nREVIEWER RECOMMENDATION - TEST (held-out, run once)")
    print("Candidate coverage:", json.dumps(results["candidate_coverage"]))
    print("Config:", json.dumps(results["selected_config"]))
    print_table(results)
    print(f"\nResults: {results['results_path']}")


def command_recommend(args):
    raw_path = get_raw_data_path(args.raw_path)
    context = evaluate.prepare_context(load_parquet(str(raw_path)))

    config = (
        evaluate.load_selected_config()
        if SELECTED_CONFIG_PATH.exists()
        else RecommenderConfig()
    )

    created_at = args.created_at or datetime.now(timezone.utc).isoformat()
    recommendations = ReviewerRecommender(context.history, config).recommend(
        args.repo, args.author, args.title, created_at, k=args.k
    )

    print(json.dumps(
        {
            "repo": args.repo,
            "author": args.author,
            "title": args.title,
            "created_at": created_at,
            "config": config.__dict__,
            "recommendations": [r.to_dict() for r in recommendations],
            "note": "Decision support only; a human selects the reviewers.",
        },
        indent=2,
        ensure_ascii=False,
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--raw-path", help="Path to the raw Parquet shard.")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("validate", help="Tune on validation and compare with baselines.")
    commands.add_parser("freeze", help="Freeze the validation-selected settings before testing.")
    commands.add_parser("test", help="Evaluate the frozen settings on the test split (once).")

    recommend = commands.add_parser("recommend", help="Recommend reviewers for one PR.")
    recommend.add_argument("--repo", required=True)
    recommend.add_argument("--author", required=True)
    recommend.add_argument("--title", required=True)
    recommend.add_argument("--created-at", help="ISO timestamp (default: now, UTC).")
    recommend.add_argument("-k", type=int, default=5)

    args = parser.parse_args()

    {
        "validate": command_validate,
        "freeze": command_freeze,
        "test": command_test,
        "recommend": command_recommend,
    }[args.command](args)


if __name__ == "__main__":
    main()
