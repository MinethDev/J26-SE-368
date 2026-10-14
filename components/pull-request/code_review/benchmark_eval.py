"""
Planted-defect benchmark and descriptive real-data runs for the AI reviewer.

Benchmark cases come in pairs: a diff with one planted defect (known line and
category) and a clean twin. The held-out split is frozen by a hash manifest
before prompt tuning and may be evaluated only once.

Real-data runs are descriptive only: human review comments are not verified
bug labels, so no accuracy is computed from them.
"""

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from code_review.ai_reviewer import (
    STATUS_FINDINGS,
    STATUS_INVALID,
    STATUS_MODEL_ERROR,
    STATUS_NO_FINDINGS,
    ModelError,
    get_prompt,
    prompt_sha256,
    run_review,
)


PACKAGE_DIR = Path(__file__).resolve().parent
BENCHMARK_DIR = PACKAGE_DIR / "benchmark"
RESULTS_DIR = PACKAGE_DIR / "data" / "results"
HELD_OUT_FILE = BENCHMARK_DIR / "held_out.json"
HELD_OUT_MANIFEST = BENCHMARK_DIR / "held_out.freeze.json"
# Persistent run marker, kept outside the Git-ignored results directory.
HELD_OUT_RUN_MARKER = BENCHMARK_DIR / "held_out.run_marker.json"
SPLITS = ("development", "held_out")

# Prompt versions that the common-valid-pairs comparison requires.
COMPARISON_PROMPTS = ("v1", "v2", "v3")

# Held-out pairs whose clean twins resemble v3's examples of already-handled
# code. Excluded only in the diagnostic sensitivity analysis.
SENSITIVITY_EXCLUDED_PAIRS = ("held-04", "held-05", "held-10")
SENSITIVITY_LABEL = (
    "DIAGNOSTIC sensitivity analysis, not the primary result: excludes held-out pairs whose "
    "clean twins resemble v3's examples of already-handled code. Chosen after inspecting the "
    "cases, so it is potentially biased and must not replace the primary analysis."
)

# A finding "hits" the defect line if it is within this many lines.
LINE_TOLERANCE = 1

METRIC_DEFINITIONS = {
    "detection_rate": "Defect cases with >= 1 finding / defect cases with a valid response.",
    "localized_detection_rate": f"Defect cases with a finding within +/-{LINE_TOLERANCE} of the expected "
                                "line / defect cases with a valid response. The finding's stated reason "
                                "is not checked.",
    "false_positive_rate": "Clean cases with >= 1 finding / clean cases with a valid response.",
    "precision": "Defect cases with >= 1 finding / all cases with a valid response and >= 1 finding.",
    "line_accuracy": f"Detected defect cases where some finding's line is within +/-{LINE_TOLERANCE} "
                     "of the expected line / detected defect cases. Findings without a line count as misses.",
    "category_accuracy": "Detected defect cases where some finding's category is in the case's "
                         "acceptable categories / detected defect cases.",
    "pair_accuracy": "Pairs where the defect case has >= 1 finding and the clean twin has none / "
                     "pairs where both responses are valid.",
    "invalid_response_rate": "Cases with an invalid model response / all cases.",
    "model_error_rate": "Cases where the model call failed / all cases.",
    # Conservative variants: invalid responses and model errors count as failures.
    "conservative_detection_rate": "Defect cases with a valid response and >= 1 finding / all defect "
                                   "cases. Invalid responses and model errors count as misses.",
    "conservative_localized_detection_rate": f"Defect cases with a valid response and a finding within "
                                             f"+/-{LINE_TOLERANCE} of the expected line / all defect cases. "
                                             "Invalid responses and model errors count as misses.",
    "conservative_pair_accuracy": "Pairs where both responses are valid, the defect case has >= 1 "
                                  "finding, and the clean twin has none / all pairs. Invalid responses "
                                  "and model errors count as pair failures.",
}


# ---------------------------------------------------------------------------
# Benchmark files and freezing
# ---------------------------------------------------------------------------

def normalized_sha256(path: Path) -> str:
    """SHA-256 of a text file with line endings normalized to LF."""

    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_cases(split, benchmark_dir=BENCHMARK_DIR) -> list:
    if split not in SPLITS:
        raise ValueError(f"Unknown split: {split}")

    with open(Path(benchmark_dir) / f"{split}.json", encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def check_held_out_frozen(held_out_file=HELD_OUT_FILE, manifest_file=HELD_OUT_MANIFEST) -> dict:
    """Refuse to use held-out cases that are missing a manifest or were changed."""

    if not Path(manifest_file).exists():
        raise FileNotFoundError("The held-out split has no freeze manifest.")

    with open(manifest_file, encoding="utf-8") as handle:
        manifest = json.load(handle)

    if normalized_sha256(held_out_file) != manifest["sha256_lf_normalized"]:
        raise RuntimeError("held_out.json changed after it was frozen.")

    return manifest


def check_held_out_not_evaluated(manifest, results_dir=RESULTS_DIR):
    """The held-out split may be evaluated only once."""

    for previous in Path(results_dir).glob("benchmark_held_out_*.json"):
        with open(previous, encoding="utf-8") as handle:
            if json.load(handle)["run"].get("held_out_sha256") == manifest["sha256_lf_normalized"]:
                raise FileExistsError(f"The held-out split was already evaluated: {previous}")


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

def review_case(case, prompt_version, client) -> dict:
    result = run_review(
        case["pr_title"], case["file_path"], case["diff"],
        prompt_version=prompt_version, client=client,
    )

    return {
        "id": case["id"],
        "pair_id": case["pair_id"],
        "label": case["label"],
        "language": case["language"],
        "expected": case["expected"],
        "result": result.to_dict(),
    }


class RunAbortedOnModelError(ModelError):
    """A model call failed during a run that must not continue with degraded results."""

    def __init__(self, case_id, prompt_version, cases_sent, error):
        self.case_id = case_id
        self.prompt_version = prompt_version
        self.cases_sent = cases_sent
        super().__init__(
            f"Model call failed for case {case_id} (prompt {prompt_version}) after {cases_sent} "
            f"case(s) were sent in this run; the run was stopped. Model error: {error}"
        )


def run_cases(cases, prompt_version, client, progress=None, stop_on_model_error=False, sent_counter=None) -> list:
    """
    Review each case. With stop_on_model_error, the first model-call failure
    (status model_error) stops the run; invalid responses never stop it.
    """

    records = []

    for index, case in enumerate(cases, start=1):
        record = review_case(case, prompt_version, client)
        records.append(record)

        if sent_counter is not None:
            sent_counter["cases_sent"] += 1

        if progress:
            progress(index, len(cases), record)

        if stop_on_model_error and record["result"]["status"] == STATUS_MODEL_ERROR:
            raise RunAbortedOnModelError(
                case["id"], prompt_version,
                sent_counter["cases_sent"] if sent_counter is not None else index,
                record["result"]["error"],
            )

    return records


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _ratio(numerator, denominator, definition) -> dict:
    return {
        "value": round(numerator / denominator, 4) if denominator else None,
        "numerator": int(numerator),
        "denominator": int(denominator),
        "definition": definition,
    }


def case_outcome(record) -> dict:
    """Per-case flags used by the metrics."""

    result = record["result"]
    valid = result["status"] in (STATUS_FINDINGS, STATUS_NO_FINDINGS)
    findings = result["findings"] if valid else []
    expected = record["expected"] or {}

    line_hit = any(
        isinstance(f.get("line"), int)
        and expected.get("line") is not None
        and abs(f["line"] - expected["line"]) <= LINE_TOLERANCE
        for f in findings
    )
    category_hit = any(
        f.get("category") in expected.get("acceptable_categories", []) for f in findings
    )

    return {
        "valid": valid,
        "flagged": bool(findings),
        "has_line_field": any("line" in f for f in findings),
        "has_category_field": any("category" in f for f in findings),
        "line_hit": line_hit,
        "category_hit": category_hit,
    }


def compute_metrics(records) -> dict:
    outcomes = [(record, case_outcome(record)) for record in records]
    statuses = Counter(record["result"]["status"] for record in records)

    defects = [o for r, o in outcomes if r["label"] == "defect" and o["valid"]]
    cleans = [o for r, o in outcomes if r["label"] == "clean" and o["valid"]]
    detected = [o for o in defects if o["flagged"]]
    flagged_any = [o for r, o in outcomes if o["valid"] and o["flagged"]]

    # Line and category accuracy need those fields (prompt v1 has neither).
    line_available = any(o["has_line_field"] for o in detected)
    category_available = any(o["has_category_field"] for o in detected)

    pairs = {}

    for record, outcome in outcomes:
        pairs.setdefault(record["pair_id"], {})[record["label"]] = outcome

    complete_pairs = [
        p for p in pairs.values()
        if "defect" in p and "clean" in p and p["defect"]["valid"] and p["clean"]["valid"]
    ]
    correct_pairs = [p for p in complete_pairs if p["defect"]["flagged"] and not p["clean"]["flagged"]]

    definitions = METRIC_DEFINITIONS
    metrics = {
        "cases": len(records),
        "status_counts": {
            status: int(statuses.get(status, 0))
            for status in (STATUS_FINDINGS, STATUS_NO_FINDINGS, STATUS_INVALID, STATUS_MODEL_ERROR)
        },
        "detection_rate": _ratio(len(detected), len(defects), definitions["detection_rate"]),
        "localized_detection_rate": (
            _ratio(sum(o["line_hit"] for o in defects), len(defects), definitions["localized_detection_rate"])
            if line_available or not detected else
            {"value": None, "note": "Not available: the prompt's schema has no line field."}
        ),
        "false_positive_rate": _ratio(sum(o["flagged"] for o in cleans), len(cleans),
                                      definitions["false_positive_rate"]),
        "precision": _ratio(len(detected), len(flagged_any), definitions["precision"]),
        "line_accuracy": (
            _ratio(sum(o["line_hit"] for o in detected), len(detected), definitions["line_accuracy"])
            if line_available or not detected else
            {"value": None, "note": "Not available: the prompt's schema has no line field."}
        ),
        "category_accuracy": (
            _ratio(sum(o["category_hit"] for o in detected), len(detected), definitions["category_accuracy"])
            if category_available or not detected else
            {"value": None, "note": "Not available: the prompt's schema has no category field."}
        ),
        "pair_accuracy": _ratio(len(correct_pairs), len(complete_pairs), definitions["pair_accuracy"]),
        "invalid_response_rate": _ratio(statuses.get(STATUS_INVALID, 0), len(records),
                                        definitions["invalid_response_rate"]),
        "model_error_rate": _ratio(statuses.get(STATUS_MODEL_ERROR, 0), len(records),
                                   definitions["model_error_rate"]),
    }

    # Conservative variants: same numerators, but every case or pair is in the
    # denominator, so invalid responses and model errors count as failures.
    all_defects = [o for r, o in outcomes if r["label"] == "defect"]
    metrics["conservative_detection_rate"] = _ratio(
        len(detected), len(all_defects), definitions["conservative_detection_rate"])
    metrics["conservative_localized_detection_rate"] = (
        _ratio(sum(o["valid"] and o["line_hit"] for o in all_defects), len(all_defects),
               definitions["conservative_localized_detection_rate"])
        if line_available or not detected else
        {"value": None, "note": "Not available: the prompt's schema has no line field."}
    )
    metrics["conservative_pair_accuracy"] = _ratio(
        len(correct_pairs), len(pairs), definitions["conservative_pair_accuracy"])

    by_language = {}

    for record, outcome in outcomes:
        stats = by_language.setdefault(record["language"], {"defect_detected": 0, "defect_valid": 0,
                                                            "clean_flagged": 0, "clean_valid": 0})
        if outcome["valid"]:
            stats[f"{record['label']}_valid"] += 1
            if outcome["flagged"]:
                stats["defect_detected" if record["label"] == "defect" else "clean_flagged"] += 1

    metrics["by_language"] = by_language
    return metrics


def valid_pair_ids(records) -> set:
    """Pairs whose defect case and clean twin both have a valid response."""

    valid = {}

    for record in records:
        valid.setdefault(record["pair_id"], {})[record["label"]] = case_outcome(record)["valid"]

    return {pair for pair, labels in valid.items() if labels.get("defect") and labels.get("clean")}


def filter_pairs(records, keep=None, exclude=()) -> list:
    """Records whose pair is in `keep` (if given) and not in `exclude`."""

    return [
        record for record in records
        if (keep is None or record["pair_id"] in keep) and record["pair_id"] not in set(exclude)
    ]


def common_valid_pairs_comparison(records_by_prompt, required_prompts=COMPARISON_PROMPTS) -> dict:
    """
    Compare prompts on the pairs where every required prompt produced valid
    responses for both cases, so all prompts are scored on the same pairs.
    """

    missing = [version for version in required_prompts if version not in records_by_prompt]

    if missing:
        return {"value": None, "note": f"Not available: prompts {missing} were not evaluated in this run."}

    all_pairs = set.union(*(
        {record["pair_id"] for record in records_by_prompt[version]} for version in required_prompts
    ))
    common = set.intersection(*(valid_pair_ids(records_by_prompt[version]) for version in required_prompts))

    return {
        "definition": f"Metrics restricted to pairs where all of {list(required_prompts)} produced "
                      "valid responses for both the defect case and the clean twin.",
        "prompts": list(required_prompts),
        "pair_ids": sorted(common),
        "excluded_pair_ids": sorted(all_pairs - common),
        "metrics": {
            version: compute_metrics(filter_pairs(records_by_prompt[version], keep=common))
            for version in required_prompts
        },
    }


def sensitivity_analysis(records_by_prompt, excluded_pairs=SENSITIVITY_EXCLUDED_PAIRS) -> dict:
    """Diagnostic re-analysis without the listed pairs. Never replaces the primary metrics."""

    return {
        "label": SENSITIVITY_LABEL,
        "excluded_pair_ids": sorted(excluded_pairs),
        "metrics": {
            version: compute_metrics(filter_pairs(records, exclude=excluded_pairs))
            for version, records in records_by_prompt.items()
        },
        "common_valid_pairs": common_valid_pairs_comparison(
            {version: filter_pairs(records, exclude=excluded_pairs)
             for version, records in records_by_prompt.items()}
        ),
    }


def analyze_records(records_by_prompt, split) -> dict:
    """Primary metrics per prompt, the common-pairs comparison, and (held-out only) the sensitivity analysis."""

    analysis = {
        "primary": {version: compute_metrics(records) for version, records in records_by_prompt.items()},
        "common_valid_pairs": common_valid_pairs_comparison(records_by_prompt),
    }

    if split == "held_out":
        analysis["diagnostic_sensitivity"] = sensitivity_analysis(records_by_prompt)

    return analysis


# ---------------------------------------------------------------------------
# Held-out run marker
# ---------------------------------------------------------------------------

class HeldOutRunAlreadyStarted(RuntimeError):
    """A held-out run was already started; recovery is a deliberate manual process."""


RECOVERY_INSTRUCTIONS = (
    "A held-out run was already started (see the marker file). The runner never resets this marker. "
    "If that run did not complete, held-out cases may already have been sent to the model, so the "
    "held-out set may no longer be unseen. Investigate before doing anything else: check the marker's "
    "status and error, any partial results, and what happened to the process. Recovery is manual and "
    "must be documented; see the 'Held-out run marker' section of components/pull-request/README.md."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_no_run_marker(marker_path=HELD_OUT_RUN_MARKER):
    if Path(marker_path).exists():
        raise HeldOutRunAlreadyStarted(f"{RECOVERY_INSTRUCTIONS} Marker: {marker_path}")


def create_run_marker(held_out_sha256, prompt_versions, marker_path=HELD_OUT_RUN_MARKER) -> dict:
    """
    Atomically create the run marker. Exclusive creation ("x" mode, O_EXCL)
    fails if the file already exists, so two starts cannot both succeed.
    """

    marker = {
        "held_out_sha256": held_out_sha256,
        "prompt_versions": list(prompt_versions),
        "prompt_sha256": {version: prompt_sha256(version) for version in prompt_versions},
        "started_at_utc": _utc_now(),
        "status": "started",
    }

    try:
        with open(marker_path, "x", encoding="utf-8") as handle:
            json.dump(marker, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise HeldOutRunAlreadyStarted(f"{RECOVERY_INSTRUCTIONS} Marker: {marker_path}") from error

    return marker


def update_run_marker(marker_path, **fields) -> dict:
    """Record the run status. The marker is updated in place, never removed."""

    with open(marker_path, encoding="utf-8") as handle:
        marker = json.load(handle)

    marker.update(fields)
    temporary = Path(f"{marker_path}.tmp")

    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(marker, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temporary, marker_path)
    return marker


# ---------------------------------------------------------------------------
# Result files
# ---------------------------------------------------------------------------

def _write_json(payload, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _run_metadata(client, prompt_versions) -> dict:
    options, metadata = client.resolve_options()

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": getattr(client, "model", None),
        "options": options,
        "model_metadata": metadata,
        "prompts": {version: {"sha256": prompt_sha256(version)} for version in prompt_versions},
    }


def run_benchmark(split, prompt_versions, client, results_dir=RESULTS_DIR, progress=None,
                  benchmark_dir=BENCHMARK_DIR, marker_path=None) -> dict:
    """
    Evaluate one or more prompt versions on a benchmark split and save the results.

    Held-out order: verify the freeze, refuse if a run marker or held-out
    result exists, fetch model metadata (no cases are sent), atomically
    create the run marker, and only then send cases to the model.
    """

    benchmark_dir = Path(benchmark_dir)
    prompt_versions = list(prompt_versions)

    for version in prompt_versions:
        get_prompt(version)

    if split == "held_out":
        marker_path = Path(marker_path) if marker_path else benchmark_dir / HELD_OUT_RUN_MARKER.name
        manifest = check_held_out_frozen(benchmark_dir / HELD_OUT_FILE.name,
                                         benchmark_dir / HELD_OUT_MANIFEST.name)
        check_no_run_marker(marker_path)
        check_held_out_not_evaluated(manifest, results_dir)

    run = {"split": split, **_run_metadata(client, prompt_versions)}

    if split == "held_out":
        if "error" in run["model_metadata"]:
            raise ModelError("Model metadata unavailable, so the held-out run was not started: "
                             f"{run['model_metadata']['error']}")

        create_run_marker(manifest["sha256_lf_normalized"], prompt_versions, marker_path)
        run["held_out_sha256"] = manifest["sha256_lf_normalized"]
        run["held_out_frozen_at_utc"] = manifest["frozen_at_utc"]
        run["run_marker"] = str(marker_path)

    # Held-out runs stop on the first model-call failure instead of completing
    # with degraded results; development runs record the error and continue.
    held_out = split == "held_out"
    sent = {"cases_sent": 0}

    try:
        cases = load_cases(split, benchmark_dir)
        run["benchmark_sha256"] = normalized_sha256(benchmark_dir / f"{split}.json")

        by_prompt = {}

        for version in prompt_versions:
            records = run_cases(cases, version, client, progress,
                                stop_on_model_error=held_out, sent_counter=sent)
            by_prompt[version] = {"metrics": compute_metrics(records), "records": records}

        analysis = analyze_records({v: payload["records"] for v, payload in by_prompt.items()}, split)
        results = {
            "run": run,
            "metric_definitions": METRIC_DEFINITIONS,
            "results": by_prompt,
            "analysis": {key: value for key, value in analysis.items() if key != "primary"},
        }
        path = Path(results_dir) / f"benchmark_{split}_{_stamp()}.json"
        _write_json(results, path)
    except BaseException as error:
        if held_out:
            update_run_marker(marker_path, status="failed", ended_at_utc=_utc_now(), error=repr(error),
                              cases_sent=sent["cases_sent"])
        raise

    if held_out:
        update_run_marker(marker_path, status="completed", ended_at_utc=_utc_now(), results_path=str(path),
                          cases_sent=sent["cases_sent"])

    results["results_path"] = str(path)
    return results


def describe_real_data(records) -> dict:
    """Descriptive statistics only: there are no ground-truth labels."""

    statuses = Counter(r["result"]["status"] for r in records)
    findings = [f for r in records for f in r["result"]["findings"]]

    return {
        "cases": len(records),
        "status_counts": dict(statuses),
        "cases_with_findings": int(statuses.get(STATUS_FINDINGS, 0)),
        "total_findings": len(findings),
        "categories": dict(Counter(f.get("category", "n/a") for f in findings)),
        "severities": dict(Counter(f.get("severity", "n/a") for f in findings)),
        "note": "Descriptive only. Human review comments are not verified bug labels; no accuracy is computed.",
    }


def run_real_data(sample, prompt_version, client, results_dir=RESULTS_DIR, progress=None) -> dict:
    """Review a real-data sample (a DataFrame with pr_title, path, diff_hunk, body)."""

    records = []

    for index, row in enumerate(sample.itertuples(index=False), start=1):
        result = run_review(row.pr_title, row.path, row.diff_hunk,
                            prompt_version=prompt_version, client=client)
        record = {
            "repo_full_name": row.repo_full_name,
            "pr_number": int(row.pr_number),
            "file_path": row.path,
            "human_review_comment_not_ground_truth": row.body,
            "result": result.to_dict(),
        }
        records.append(record)

        if progress:
            progress(index, len(sample), record)

    results = {
        "run": {"split": "real_data_validation_sample", **_run_metadata(client, [prompt_version])},
        "summary": describe_real_data(records),
        "records": records,
    }
    path = Path(results_dir) / f"realdata_{prompt_version}_{_stamp()}.json"
    _write_json(results, path)

    results["results_path"] = str(path)
    return results
