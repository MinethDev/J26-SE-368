"""
Merge-readiness evaluation runs.

validate: descriptive statistics of the checklist on all decided PRs, and the
          auxiliary merged-vs-closed baseline tuned on the validation split.
freeze:   record the selected auxiliary settings and the code state.
test:     evaluate the frozen auxiliary settings once on the test split.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from merge_readiness import auxiliary
from merge_readiness.config import (
    FROZEN_CONFIG_PATH,
    RANDOM_SEED,
    RESULTS_DIR,
    SELECTED_CONFIG_PATH,
    ReadinessThresholds,
)
from merge_readiness.context import contexts_from_raw
from merge_readiness.descriptive import assess_at_decision, describe
from reviewer_recommendation.split import SPLITS


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)

    return digest.hexdigest()


def code_fingerprint() -> str:
    """Hash of the source files that determine merge-readiness results."""

    component_dir = Path(__file__).resolve().parent.parent
    sources = sorted((component_dir / "merge_readiness").glob("*.py")) + [
        component_dir / "preprocessing" / "cleaner.py",
        component_dir / "preprocessing" / "extractor.py",
        component_dir / "reviewer_recommendation" / "dataset.py",
        component_dir / "reviewer_recommendation" / "identity.py",
        component_dir / "reviewer_recommendation" / "split.py",
    ]

    digest = hashlib.sha256()

    for source in sources:
        digest.update(source.name.encode("utf-8"))
        digest.update(source.read_bytes().replace(b"\r\n", b"\n"))

    return digest.hexdigest()


def _write_json(payload, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)


def _run_metadata(split, raw_path) -> dict:
    raw_path = Path(raw_path)

    return {
        "split": split,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "random_seed": RANDOM_SEED,
        "raw_data": {"path": str(raw_path), "bytes": raw_path.stat().st_size, "sha256": _sha256_file(raw_path)},
        "code_sha256": code_fingerprint(),
    }


def build_frame(raw_df, thresholds=None):
    contexts, stats = contexts_from_raw(raw_df)
    frame = assess_at_decision(contexts, thresholds)
    stats["decided_prs"] = int(len(frame))
    stats["undecided_prs_excluded"] = int(stats["unique_prs"] - len(frame))

    return frame, stats


def _split_counts(data) -> dict:
    return {
        name: {
            "n": int((data["split"] == name).sum()),
            "closed": int(((data["split"] == name) & (data["target"] == 1)).sum()),
            "bot_authored": int(((data["split"] == name) & (data["author_group"] == "bot")).sum()),
        }
        for name in SPLITS
    }


def run_validation(raw_df, raw_path, results_dir=RESULTS_DIR) -> dict:
    thresholds = ReadinessThresholds()
    frame, stats = build_frame(raw_df, thresholds)
    data = auxiliary.prepare_features(frame)

    train = data[data["split"] == "train"]
    validation = data[data["split"] == "validation"]

    selected_c, c_selection, models = {}, {}, {}

    for variant, features in auxiliary.MODEL_VARIANTS.items():
        selected_c[variant], c_selection[variant] = auxiliary.select_c(train, validation, features)
        models[variant] = auxiliary.fit_logistic(train, selected_c[variant], features)

    results = {
        "run": {**_run_metadata("validation", raw_path), "c_grid": list(auxiliary.C_GRID)},
        "dataset": {**stats, "splits": _split_counts(data)},
        "thresholds": thresholds.__dict__,
        "checklist_descriptive": describe(frame),
        "auxiliary_baseline": {
            "caveats": auxiliary.CAVEATS,
            "primary_variant": auxiliary.PRIMARY_VARIANT,
            "variants": auxiliary.MODEL_VARIANTS,
            "c_selection": c_selection,
            "selected_c": selected_c,
            "coefficients": {v: auxiliary.coefficients(m) for v, m in models.items()},
            "validation": auxiliary.evaluate_split(validation, train, models),
        },
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = Path(results_dir) / f"validation_{stamp}.json"
    _write_json(results, results_path)
    _write_json(
        {
            "selected_c": selected_c,
            "primary_variant": auxiliary.PRIMARY_VARIANT,
            "selected_on": "validation",
            "results_file": str(results_path),
        },
        Path(results_dir) / SELECTED_CONFIG_PATH.name,
    )

    results["results_path"] = str(results_path)
    return results


def freeze_config(selected_path=SELECTED_CONFIG_PATH, frozen_path=FROZEN_CONFIG_PATH) -> dict:
    if Path(frozen_path).exists():
        raise FileExistsError(f"Settings are already frozen: {frozen_path}")

    with open(selected_path, encoding="utf-8") as handle:
        selected = json.load(handle)

    record = {
        **selected,
        "thresholds": ReadinessThresholds().__dict__,
        "code_sha256": code_fingerprint(),
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    _write_json(record, Path(frozen_path))
    return record


def check_frozen_config(frozen_path=FROZEN_CONFIG_PATH, results_dir=RESULTS_DIR) -> dict:
    if not Path(frozen_path).exists():
        raise FileNotFoundError("Freeze the validation-selected settings before testing.")

    with open(frozen_path, encoding="utf-8") as handle:
        frozen = json.load(handle)

    if code_fingerprint() != frozen["code_sha256"]:
        raise RuntimeError("Code changed after the settings were frozen.")

    frozen_sha = _sha256_file(Path(frozen_path))

    for previous in Path(results_dir).glob("test_*.json"):
        with open(previous, encoding="utf-8") as handle:
            if json.load(handle)["run"].get("frozen_config_sha256") == frozen_sha:
                raise FileExistsError(f"The test split was already evaluated: {previous}")

    return frozen


def run_test(raw_df, raw_path, frozen_path=FROZEN_CONFIG_PATH, results_dir=RESULTS_DIR) -> dict:
    frozen = check_frozen_config(frozen_path, results_dir)
    thresholds = ReadinessThresholds(**frozen["thresholds"])

    frame, stats = build_frame(raw_df, thresholds)
    data = auxiliary.prepare_features(frame)
    train = data[data["split"] == "train"]
    test = data[data["split"] == "test"]

    models = {
        variant: auxiliary.fit_logistic(train, c_value, auxiliary.MODEL_VARIANTS[variant])
        for variant, c_value in frozen["selected_c"].items()
    }

    results = {
        "run": {
            **_run_metadata("test", raw_path),
            "frozen_config_file": str(frozen_path),
            "frozen_config_sha256": _sha256_file(Path(frozen_path)),
        },
        "dataset": {**stats, "splits": _split_counts(data)},
        "auxiliary_baseline": {
            "caveats": auxiliary.CAVEATS,
            "primary_variant": frozen["primary_variant"],
            "selected_c": frozen["selected_c"],
            "coefficients": {v: auxiliary.coefficients(m) for v, m in models.items()},
            "test": auxiliary.evaluate_split(test, train, models),
        },
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = Path(results_dir) / f"test_{stamp}.json"
    _write_json(results, results_path)

    results["results_path"] = str(results_path)
    return results
