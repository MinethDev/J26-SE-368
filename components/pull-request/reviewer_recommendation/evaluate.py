"""
Held-out evaluation for reviewer recommendation.

validate: tune weights and half-life on the validation split only, compare
          with baselines on the same candidate pools, and save the selected
          configuration.
test:     evaluate the saved configuration on the test split. Run once,
          after development is finished.
"""

import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from reviewer_recommendation.baselines import (
    popularity_ranking,
    random_ranking,
    recent_popularity_ranking,
)
from reviewer_recommendation.config import (
    FROZEN_CONFIG_PATH,
    RANDOM_SEED,
    RESULTS_DIR,
    SELECTED_CONFIG_PATH,
)
from reviewer_recommendation.dataset import ReviewerDataset, build_reviewer_dataset
from reviewer_recommendation.metrics import score_ranking, summarize
from reviewer_recommendation.recommender import (
    RecommenderConfig,
    ReviewHistory,
    candidate_signals,
    fit_title_vectorizer,
    normalized_signals,
    rank_order,
    weighted_scores,
)
from reviewer_recommendation.split import SPLITS, assign_chronological_splits


HALF_LIFE_GRID = (30.0, 90.0, 180.0, 365.0)
WEIGHT_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
KS = (1, 3, 5)
PRIMARY_METRIC = "mrr"
METRIC_COLUMNS = ["mrr"] + [
    f"{name}@{k}" for k in KS for name in ("hit", "recall")
]


@dataclass
class EvaluationContext:
    dataset: ReviewerDataset
    split_prs: pd.DataFrame
    history: ReviewHistory


def prepare_context(raw_df: pd.DataFrame) -> EvaluationContext:
    dataset = build_reviewer_dataset(raw_df)
    split_prs = assign_chronological_splits(dataset.evaluation_prs)

    # Title vocabulary comes from training PRs only.
    train_titles = split_prs.loc[split_prs["split"] == "train", "title"]
    history = ReviewHistory(dataset.pairs, fit_title_vectorizer(train_titles))

    return EvaluationContext(dataset=dataset, split_prs=split_prs, history=history)


def collect_queries(context: EvaluationContext, split, half_lives):
    """Compute as-of candidate signals once per query PR."""

    queries = context.split_prs[context.split_prs["split"] == split]

    return [
        (
            row,
            candidate_signals(
                context.history,
                row.repo_full_name,
                row.created_by,
                row.title,
                row.created_at,
                half_lives=half_lives,
            ),
        )
        for row in queries.itertuples(index=False)
    ]


def model_ranking(signals: pd.DataFrame, config: RecommenderConfig) -> list:
    """Same scoring and tie-breaking as ReviewerRecommender.rank."""

    if signals.empty:
        return []

    scores = weighted_scores(
        normalized_signals(signals, config.half_life_days), config
    )

    return list(signals.index[rank_order(scores)])


def baseline_rankers():
    return {
        "random": lambda signals, index: random_ranking(
            signals, np.random.default_rng([RANDOM_SEED, index])
        ),
        "popularity": lambda signals, index: popularity_ranking(signals),
        "recent_popularity": lambda signals, index: recent_popularity_ranking(signals),
    }


def evaluate_rankers(collected, rankers) -> dict:
    """Per-query metrics for each ranker, summarized overall and per repo."""

    records = {name: [] for name in rankers}

    for index, (row, signals) in enumerate(collected):
        for name, ranker in rankers.items():
            ranked = ranker(signals, index)
            records[name].append({
                "repo_full_name": row.repo_full_name,
                "pr_number": row.pr_number,
                **score_ranking(ranked, row.true_reviewers, KS),
            })

    return {
        name: summarize(pd.DataFrame(rows), METRIC_COLUMNS)
        for name, rows in records.items()
    }


def coverage_summary(collected) -> dict:
    """How often a true reviewer is in the candidate pool (the ceiling for any ranker)."""

    covered = [bool(set(signals.index) & set(row.true_reviewers)) for row, signals in collected]
    pool_sizes = [len(signals) for _, signals in collected]

    return {
        "queries": len(collected),
        "true_reviewer_in_pool": round(float(np.mean(covered)), 4) if covered else 0.0,
        "empty_pool": int(sum(size == 0 for size in pool_sizes)),
        "median_pool_size": float(np.median(pool_sizes)) if pool_sizes else 0.0,
    }


def weight_grid():
    for weights in itertools.product(WEIGHT_GRID, repeat=3):
        if any(weights):
            yield weights


def tune(collected, half_lives=HALF_LIFE_GRID) -> pd.DataFrame:
    """Overall validation MRR and Hit@k for every grid configuration."""

    prepared = []

    for row, signals in collected:
        prepared.append((
            signals.index.isin(row.true_reviewers),
            {half_life: normalized_signals(signals, half_life) for half_life in half_lives},
        ))

    rows = []

    for half_life in half_lives:
        for weights in weight_grid():
            config = RecommenderConfig(*weights, half_life_days=half_life)
            reciprocal_ranks = []
            hits = {k: [] for k in KS}

            for truth_mask, normalized in prepared:
                if len(truth_mask) == 0:
                    first = None
                else:
                    order = rank_order(weighted_scores(normalized[half_life], config))
                    positions = np.flatnonzero(truth_mask[order])
                    first = positions[0] if positions.size else None

                reciprocal_ranks.append(0.0 if first is None else 1.0 / (first + 1))

                for k in KS:
                    hits[k].append(float(first is not None and first < k))

            rows.append({
                **asdict(config),
                "mrr": float(np.mean(reciprocal_ranks)),
                **{f"hit@{k}": float(np.mean(values)) for k, values in hits.items()},
            })

    # Stable sort keeps grid order for ties, so selection is deterministic.
    return pd.DataFrame(rows).sort_values(
        PRIMARY_METRIC, ascending=False, kind="mergesort"
    ).reset_index(drop=True)


def file_fingerprint(path: Path) -> dict:
    digest = hashlib.sha256()

    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)

    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def code_fingerprint() -> str:
    """Hash of the source files that determine evaluation results."""

    package_dir = Path(__file__).resolve().parent
    preprocessing_dir = package_dir.parent / "preprocessing"
    sources = sorted(package_dir.glob("*.py")) + [
        preprocessing_dir / "cleaner.py",
        preprocessing_dir / "extractor.py",
    ]

    digest = hashlib.sha256()

    for source in sources:
        digest.update(source.name.encode("utf-8"))
        # Normalize line endings so the hash does not depend on Git checkout settings.
        digest.update(source.read_bytes().replace(b"\r\n", b"\n"))

    return digest.hexdigest()


def dataset_summary(context: EvaluationContext) -> dict:
    split_counts = context.split_prs["split"].value_counts()

    return {
        **context.dataset.stats,
        "split_prs": {name: int(split_counts.get(name, 0)) for name in SPLITS},
        "repositories": int(context.split_prs["repo_full_name"].nunique()),
    }


def _write_json(payload, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)


def _run_metadata(split, raw_path):
    return {
        "split": split,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "random_seed": RANDOM_SEED,
        "primary_metric": PRIMARY_METRIC,
        "raw_data": file_fingerprint(Path(raw_path)),
        "code_sha256": code_fingerprint(),
    }


def run_validation(raw_df, raw_path, results_dir=RESULTS_DIR) -> dict:
    context = prepare_context(raw_df)
    collected = collect_queries(context, "validation", HALF_LIFE_GRID)

    grid = tune(collected)
    best = grid.iloc[0]
    selected = RecommenderConfig(
        activity_weight=float(best["activity_weight"]),
        author_weight=float(best["author_weight"]),
        similarity_weight=float(best["similarity_weight"]),
        half_life_days=float(best["half_life_days"]),
    )

    ablations = {
        "activity_only": RecommenderConfig(1, 0, 0, selected.half_life_days),
        "author_affinity_only": RecommenderConfig(0, 1, 0, selected.half_life_days),
        "title_similarity_only": RecommenderConfig(0, 0, 1, selected.half_life_days),
    }

    rankers = baseline_rankers()
    rankers["recommender"] = lambda signals, index: model_ranking(signals, selected)

    for name, config in ablations.items():
        rankers[name] = lambda signals, index, config=config: model_ranking(signals, config)

    summaries = evaluate_rankers(collected, rankers)

    # The fast tuning path and the reference metric path must agree.
    if abs(summaries["recommender"]["overall"]["mrr"] - round(float(best["mrr"]), 4)) > 1e-4:
        raise RuntimeError("Tuning and evaluation MRR disagree; check ranking logic.")

    results = {
        "run": {
            **_run_metadata("validation", raw_path),
            "half_life_grid": list(HALF_LIFE_GRID),
            "weight_grid": list(WEIGHT_GRID),
            "grid_size": int(len(grid)),
        },
        "dataset": dataset_summary(context),
        "candidate_coverage": coverage_summary(collected),
        "selected_config": asdict(selected),
        "results": summaries,
        "top_configs": grid.head(10).round(4).to_dict("records"),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = Path(results_dir) / f"validation_{stamp}.json"
    _write_json(results, results_path)

    _write_json(
        {
            "config": asdict(selected),
            "selected_on": "validation",
            "validation_mrr": round(float(best["mrr"]), 4),
            "results_file": str(results_path),
        },
        Path(results_dir) / SELECTED_CONFIG_PATH.name,
    )

    results["results_path"] = str(results_path)
    return results


def load_selected_config(path=SELECTED_CONFIG_PATH) -> RecommenderConfig:
    with open(path, encoding="utf-8") as handle:
        return RecommenderConfig(**json.load(handle)["config"])


def freeze_config(config_path=SELECTED_CONFIG_PATH, frozen_path=FROZEN_CONFIG_PATH) -> dict:
    """Record the validation-selected settings and code state before testing."""

    if Path(frozen_path).exists():
        raise FileExistsError(f"Settings are already frozen: {frozen_path}")

    with open(config_path, encoding="utf-8") as handle:
        selected = json.load(handle)

    record = {
        "config": selected["config"],
        "selected_on": selected["selected_on"],
        "validation_mrr": selected["validation_mrr"],
        "validation_results_file": selected["results_file"],
        "selected_config_sha256": file_fingerprint(Path(config_path))["sha256"],
        "code_sha256": code_fingerprint(),
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    _write_json(record, Path(frozen_path))
    return record


def check_frozen_config(frozen_path=FROZEN_CONFIG_PATH, results_dir=RESULTS_DIR) -> dict:
    """Refuse to test if settings or code changed after freezing, or a test already ran."""

    if not Path(frozen_path).exists():
        raise FileNotFoundError("Freeze the validation-selected settings before testing.")

    with open(frozen_path, encoding="utf-8") as handle:
        frozen = json.load(handle)

    if code_fingerprint() != frozen["code_sha256"]:
        raise RuntimeError("Code changed after the settings were frozen.")

    for previous in Path(results_dir).glob("test_*.json"):
        with open(previous, encoding="utf-8") as handle:
            if json.load(handle)["run"].get("frozen_config_sha256") == file_fingerprint(Path(frozen_path))["sha256"]:
                raise FileExistsError(f"The test split was already evaluated: {previous}")

    return frozen


def run_test(raw_df, raw_path, frozen_path=FROZEN_CONFIG_PATH, results_dir=RESULTS_DIR) -> dict:
    frozen = check_frozen_config(frozen_path, results_dir)
    config = RecommenderConfig(**frozen["config"])
    context = prepare_context(raw_df)
    collected = collect_queries(context, "test", (config.half_life_days,))

    rankers = baseline_rankers()
    rankers["recommender"] = lambda signals, index: model_ranking(signals, config)

    results = {
        "run": {
            **_run_metadata("test", raw_path),
            "frozen_config_file": str(frozen_path),
            "frozen_config_sha256": file_fingerprint(Path(frozen_path))["sha256"],
            "frozen_at_utc": frozen["frozen_at_utc"],
        },
        "dataset": dataset_summary(context),
        "candidate_coverage": coverage_summary(collected),
        "selected_config": asdict(config),
        "results": evaluate_rankers(collected, rankers),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = Path(results_dir) / f"test_{stamp}.json"
    _write_json(results, results_path)

    results["results_path"] = str(results_path)
    return results
