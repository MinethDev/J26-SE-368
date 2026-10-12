"""
Command-line entry point for the AI code review benchmark.

This script lives in the component's source root, so the packages import
directly. Run from any directory (requires a local Ollama server):

    python components/pull-request/run_code_review_benchmark.py dev --prompts v1 v2 v3
    python components/pull-request/run_code_review_benchmark.py heldout --prompts v1 v2 v3
    python components/pull-request/run_code_review_benchmark.py realdata --prompt v3
    python components/pull-request/run_code_review_benchmark.py check-freeze

The held-out split is frozen by a hash manifest and can be evaluated once.
"""

import argparse
import json

import pandas as pd

from code_review import benchmark_eval
from code_review.ai_reviewer import OllamaClient
from code_review.evaluate_reviewer import DATASET_PATH, RANDOM_SEED, SAMPLE_SIZE, select_sample


TABLE = ["detection_rate", "localized_detection_rate", "false_positive_rate", "precision", "line_accuracy",
         "category_accuracy", "pair_accuracy", "conservative_detection_rate",
         "conservative_localized_detection_rate", "conservative_pair_accuracy",
         "invalid_response_rate", "model_error_rate"]


def progress(index, total, record):
    result = record["result"]
    label = record.get("label", "")
    print(f"  [{index:>2}/{total}] {record.get('id', record.get('file_path', '')):<22} {label:<7} "
          f"{result['status']:<17} findings={len(result['findings'])}", flush=True)


def cell(metric):
    if metric.get("value") is None:
        return "n/a"

    return f"{metric['value']:.3f} ({metric['numerator']}/{metric['denominator']})"


def print_table(title, metrics_by_prompt):
    print(f"\n{title}")
    print(f"{'metric':<40}" + "".join(f"{version:>22}" for version in metrics_by_prompt))

    for name in TABLE:
        print(f"{name:<40}" + "".join(f"{cell(m[name]):>22}" for m in metrics_by_prompt.values()))


def print_metrics(results):
    print_table("PRIMARY ANALYSIS (all cases)", {v: p["metrics"] for v, p in results["results"].items()})

    for version, payload in results["results"].items():
        print(f"Status counts [{version}]:", json.dumps(payload["metrics"]["status_counts"]))

    common = results["analysis"]["common_valid_pairs"]

    if common.get("metrics"):
        print_table(f"COMMON VALID PAIRS ({len(common['pair_ids'])} pairs; "
                    f"excluded: {common['excluded_pair_ids']})", common["metrics"])
    else:
        print(f"\nCommon valid pairs: {common['note']}")

    sensitivity = results["analysis"].get("diagnostic_sensitivity")

    if sensitivity:
        print(f"\n{sensitivity['label']}")
        print_table(f"DIAGNOSTIC SENSITIVITY (excluding {sensitivity['excluded_pair_ids']})",
                    sensitivity["metrics"])


def command_benchmark(split, prompts):
    # Model metadata is fetched inside run_benchmark, after the held-out guards.
    results = benchmark_eval.run_benchmark(split, prompts, OllamaClient(), progress=progress)
    run = results["run"]
    print(f"\nModel: {run['model']} | options: {json.dumps(run['options'])} | "
          f"server: {run['model_metadata'].get('server_version')}")
    print_metrics(results)
    print(f"\nResults: {results['results_path']}")


def command_realdata(prompt):
    sample = select_sample(pd.read_parquet(DATASET_PATH), SAMPLE_SIZE, RANDOM_SEED)
    results = benchmark_eval.run_real_data(sample, prompt, OllamaClient(), progress=progress)

    print("\nREAL-DATA SAMPLE (descriptive only; human comments are not ground truth)")
    print(json.dumps(results["summary"], indent=2))
    print(f"\nResults: {results['results_path']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    commands = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("dev", "Evaluate prompts on the development split."),
                            ("heldout", "Evaluate prompts once on the frozen held-out split.")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--prompts", nargs="+", default=["v1", "v2", "v3"])

    realdata = commands.add_parser("realdata", help="Descriptive run on the 30-example validation sample.")
    realdata.add_argument("--prompt", default="v3")

    commands.add_parser("check-freeze", help="Verify the held-out freeze manifest.")

    args = parser.parse_args()

    if args.command == "dev":
        command_benchmark("development", args.prompts)
    elif args.command == "heldout":
        command_benchmark("held_out", args.prompts)
    elif args.command == "realdata":
        command_realdata(args.prompt)
    else:
        print(json.dumps(benchmark_eval.check_held_out_frozen(), indent=2))


if __name__ == "__main__":
    main()
