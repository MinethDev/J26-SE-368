# AI-Assisted Pull Request Intelligence

This component provides AI-assisted intelligence for pull request analysis within the DevIntel platform.

## Mechanisms

1. AI-Assisted Code Review
2. Reviewer Recommendation
3. Pull Request Summarization
4. Merge-Readiness Decision Support

## Scope

The component provides contextualized, explainable decision support to assist software engineering teams during pull request review and decision-making.

The system does not autonomously approve, reject, or merge pull requests.

## Structure

- `code_review/` - AI-assisted code review
- `reviewer_recommendation/` - reviewer recommendation
- `summarization/` - pull request summarization (planned)
- `merge_readiness/` - merge-readiness decision support
- `preprocessing/` - data preparation and preprocessing
- `evaluation/` - component evaluation (planned)
- `tests/` - unit tests (synthetic data; the raw dataset is not needed)
- `run_reviewer_recommendation.py` - command-line entry point for reviewer recommendation
- `run_merge_readiness.py` - command-line entry point for merge-readiness decision support

## Development setup

`components/pull-request/` is the component's source root: mechanism folders are importable packages (`preprocessing`, `reviewer_recommendation`, `merge_readiness`). Entry-point scripts live in this folder, so they import the packages without modifying `sys.path`.

```bash
# From the repository root: create a local virtual environment (ignored by Git)
python -m venv .venv
.venv/Scripts/python -m pip install -r components/pull-request/requirements.txt   # Linux/macOS: .venv/bin/python

# Run the unit tests
.venv/Scripts/python -m unittest discover -s components/pull-request/tests -t components/pull-request
```

`pytest.ini` at the repository root configures the same source root and test folder for pytest (pytest itself is not yet a listed dependency).

## Data

### Raw dataset

- Input: a single SWE-Review-Chat Parquet shard, `train-00001.parquet` (4,948 pull requests from 10 repositories).
- Source URL / dataset identifier: **unverified, not yet documented**.
- The raw file is stored outside the repository and is not committed.
- Current location: `D:\Downloads Folder\train-00001.parquet`. This path is hardcoded as `INPUT_FILE` in `code_review/dataset_builder.py` and as `file_path` in the `__main__` blocks of the `preprocessing/` modules. Edit it there if the file is stored elsewhere.
- Reviewer recommendation resolves the path from `--raw-path`, then the `DEVINTEL_PR_RAW_DATA` environment variable, then the default above.

### Generated files

All Parquet files (`*.parquet`) and code-review evaluation results (`code_review/data/evaluation_results*.csv`) are excluded from Git. They can be regenerated with the scripts below.

Requirements: Python with `pandas` and `pyarrow` (Parquet I/O), `scikit-learn` (retrieval baseline), and a local [Ollama](https://ollama.com) server with the `qwen2.5-coder:3b` model (AI reviewer evaluation).

Run from the repository root, in order:

```bash
# 1. Build the code-review dataset from the raw shard
#    -> components/pull-request/code_review/data/code_review_dataset.parquet
python components/pull-request/code_review/dataset_builder.py

# 2. Chronological train/validation/test split (70/15/15), grouped by PR, with a leakage check
#    -> components/pull-request/code_review/data/splits/train.parquet
#    -> components/pull-request/code_review/data/splits/validation.parquet
#    -> components/pull-request/code_review/data/splits/test.parquet
python components/pull-request/code_review/split_dataset.py

# 3. (Optional) TF-IDF retrieval baseline demonstration (prints results, writes no files)
python components/pull-request/code_review/retrieval_baseline.py

# 4. AI reviewer evaluation on 30 validation examples (requires Ollama on localhost:11434)
#    -> components/pull-request/code_review/data/evaluation_results_<YYYYMMDD_HHMMSS>.csv
python components/pull-request/code_review/evaluate_reviewer.py
```

`code_review/inspect_validation.py` prints a summary of the validation split. It uses a relative path and must be run from the repository root.

The preprocessing modules (`preprocessing/validator.py` and others) can be run directly to print data-quality reports for the raw shard. They write no files.

## Reviewer Recommendation

Recommends human reviewers for a pull request and explains each recommendation. It is decision support: a human always selects the reviewers.

### Task definition

- **Input:** repository, PR author, PR title, PR creation time. Only information available when the PR is opened is used.
- **Output:** top-k ranked reviewers, each with a score, three signal values, and plain-language reasons.
- **Ground truth:** human accounts, other than the author, that submitted a `review` or an inline `review_comment` on the PR. General PR comments and thread replies are not counted.
- **Excluded accounts:** bots (account type `Bot`, logins ending in `[bot]`, and `KNOWN_BOT_LOGINS` in `reviewer_recommendation/identity.py`: `matticbot`, `azclibot`), missing logins, and the PR author (case-insensitive).
- **Candidates:** humans who reviewed in the same repository strictly before the PR was created, excluding the author.

### Method

Each candidate receives three signals, scaled to [0, 1] within the candidate set:

| Signal | Definition |
|---|---|
| Activity | Recency-weighted number of PRs reviewed in the repository (weight halves every `half_life_days`) |
| Author affinity | Recency-weighted number of this author's PRs the candidate reviewed |
| Title similarity | Highest TF-IDF cosine similarity between the PR title and titles the candidate reviewed |

The score is a weighted sum of the signals. Weights ({0, 0.25, 0.5, 0.75, 1}) and half-life ({30, 90, 180, 365} days) were selected by grid search on the validation split only (primary metric: MRR).

Baselines rank the same candidate pool: **random**, **popularity** (most PRs reviewed in the repository), and **recent popularity** (most PRs reviewed in the last 90 days).

### Leakage controls

- All candidates and signals use review activity strictly before the PR's creation time.
- File paths are not used: in this dataset they come only from review comments, so they would reveal the reviewers.
- Final PR size (additions/deletions) is not used.
- Chronological 70/15/15 split by PR within each repository.
- The title vocabulary is fitted on training-split PRs only.
- Settings were frozen (with a fingerprint of the code) before the single test-split run. The `test` command refuses to run if the code changed after freezing, or if the test split was already evaluated with the frozen settings.

### Running

```bash
python components/pull-request/run_reviewer_recommendation.py validate   # tune on validation, compare with baselines
python components/pull-request/run_reviewer_recommendation.py freeze     # freeze the selected settings
python components/pull-request/run_reviewer_recommendation.py test       # evaluate once on the test split
python components/pull-request/run_reviewer_recommendation.py recommend --repo OWNER/REPO --author LOGIN --title "PR title" --created-at 2024-09-01T00:00:00Z
```

Outputs are written to `reviewer_recommendation/data/results/` (ignored by Git): validation and test results (aggregate and per-repository metrics, run metadata, and dataset fingerprint), the selected settings, and the frozen settings.

### Evaluation population

| | PRs |
|---|---|
| Raw PR rows | 4,948 |
| Unique PRs (3 duplicate rows removed) | 4,945 |
| PRs with at least one eligible reviewer (evaluated) | 3,798 |
| PRs excluded: no review events | 915 |
| PRs excluded: only bot, missing-login, or author reviews | 232 |
| Split: train / validation / test | 2,655 / 568 / 575 |

A true reviewer was in the candidate pool for 98.2% of validation PRs (558/568) and 98.3% of test PRs; the remainder are first-time reviewers that no ranker using past activity can recommend.

### Results

Selected settings (validation): activity weight 0.25, author weight 1.0, title-similarity weight 0.25, half-life 90 days.

**Validation (568 PRs, used for model selection):**

| Ranker | MRR | Hit@1 | Hit@3 | Hit@5 | Recall@3 | Macro MRR |
|---|---|---|---|---|---|---|
| Random | 0.166 | 0.053 | 0.166 | 0.239 | 0.121 | 0.217 |
| Popularity | 0.505 | 0.361 | 0.556 | 0.685 | 0.433 | 0.582 |
| Recent popularity | 0.528 | 0.368 | 0.607 | 0.748 | 0.476 | 0.599 |
| Recommender | 0.605 | 0.445 | 0.706 | 0.831 | 0.566 | 0.657 |
| Activity only | 0.531 | 0.366 | 0.613 | 0.762 | 0.483 | 0.600 |
| Author affinity only | 0.591 | 0.426 | 0.703 | 0.812 | 0.568 | 0.643 |
| Title similarity only | 0.484 | 0.294 | 0.576 | 0.743 | 0.446 | 0.580 |

**Test (575 PRs, held out, evaluated once with the frozen settings):**

| Ranker | MRR | Hit@1 | Hit@3 | Hit@5 | Recall@3 | Macro MRR |
|---|---|---|---|---|---|---|
| Random | 0.160 | 0.061 | 0.123 | 0.226 | 0.093 | 0.204 |
| Popularity | 0.401 | 0.210 | 0.459 | 0.649 | 0.386 | 0.559 |
| Recent popularity | 0.428 | 0.235 | 0.520 | 0.670 | 0.427 | 0.564 |
| Recommender | 0.614 | 0.445 | 0.734 | 0.844 | 0.653 | 0.687 |

Macro MRR averages per-repository MRR so that `Altinn/altinn-studio` (67% of test PRs) does not dominate.

**Test, per repository (MRR / Hit@3):**

| Repository | PRs | Popularity | Recommender |
|---|---|---|---|
| Altinn/altinn-studio | 384 | 0.315 / 0.339 | 0.572 / 0.708 |
| AppFlowy-IO/AppFlowy | 10 | 0.693 / 0.800 | 0.708 / 0.800 |
| ArcadeData/arcadedb | 16 | 0.781 / 1.000 | 0.865 / 1.000 |
| Automattic/wordpress-activitypub | 32 | 0.888 / 0.906 | 0.892 / 0.938 |
| Automattic/wp-calypso | 28 | 0.123 / 0.179 | 0.231 / 0.286 |
| Azure/azure-cli | 47 | 0.535 / 0.723 | 0.780 / 0.915 |
| Azure/azure-cli-extensions | 19 | 0.595 / 0.737 | 0.655 / 0.684 |
| Azure/azure-container-networking | 14 | 0.698 / 0.929 | 0.905 / 1.000 |
| Azure/azure-functions-host | 14 | 0.483 / 0.429 | 0.607 / 0.714 |
| Azure/azure-powershell | 11 | 0.475 / 0.818 | 0.660 / 0.727 |

No statistical significance test has been run yet, so these results show observed differences only. Per-repository samples outside `Altinn/altinn-studio` are small (10-47 PRs).

### Limitations

- The changed-file list at PR creation is not available in this dataset, so file-ownership signals are not used.
- Ground truth is who actually reviewed, not who would have been the best reviewer.
- Reviewer workload and availability are not modelled.
- One dataset shard; one repository provides about two-thirds of evaluated PRs.
- New reviewers with no earlier activity in the repository cannot be recommended (about 1.7% of PRs).

## Merge-Readiness Decision Support

Produces an explainable readiness checklist for a pull request at a given time. It never approves, rejects, or merges a pull request: every output states that a human makes the merge decision. Deployment-risk prediction is out of scope.

### Checklist

Each item reports a status (`pass`, `attention`, `unknown`), a severity for attention items (`blocking` or `advisory`), the evidence, and the basis of the rule. Only events strictly before the assessment time are used.

| Item | Rule | Basis |
|---|---|---|
| Human approval | At least 1 current approval from a human other than the author (latest review state per reviewer; dismissed reviews withdrawn) | Heuristic threshold; blocking |
| Outstanding change requests | No reviewer whose latest review requests changes | Review state; blocking |
| Unanswered review threads | Inline threads by human reviewers with no reply from the author | **Approximation**: resolution status and reply times are not in the dataset; advisory |
| Review coverage | At least 1 human reviewer other than the author | Heuristic threshold; advisory |
| Recent activity | Attention after 14 days without human activity | Heuristic threshold; advisory |
| Change size | Attention above 500 changed lines | Heuristic threshold; final additions/deletions only; advisory |
| External checks | CI, quality gate, merge conflicts | **Not in the offline dataset**: reported as "not provided" unless supplied (planned input from the DevIntel data integration layer); failing = blocking |

The thresholds (`merge_readiness/config.py`, `ReadinessThresholds`) are configurable, **unvalidated initial heuristics**. They are not taken from the proposal or calibrated on data. The seven items are the agreed initial implementation; they are not all explicitly mandated by the proposal.

Overall label:
- **Needs attention**: any item needs attention (listed with evidence).
- **Insufficient information**: a required item (approval, change requests, coverage, activity, size) cannot be determined.
- **No blocking issues found: ready for human merge decision**: otherwise. External checks that were not provided are listed under missing information.

Every assessment also lists known data gaps: thread resolution is approximated, and commit/push history is unavailable, so approvals cannot be checked against the latest change.

### Running

```bash
python components/pull-request/run_merge_readiness.py validate   # descriptive statistics + auxiliary baseline (validation)
python components/pull-request/run_merge_readiness.py freeze     # freeze the auxiliary baseline settings
python components/pull-request/run_merge_readiness.py test       # evaluate the frozen auxiliary baseline once on test
python components/pull-request/run_merge_readiness.py assess --repo OWNER/REPO --number 123 [--as-of 2024-09-01T00:00:00Z]
```

`assess` defaults to the moment just before the PR's final merge/close event. Outputs are written to `merge_readiness/data/results/` (ignored by Git).

### Descriptive statistics (all decided PRs)

Each of the 4,939 decided PRs (6 undecided PRs excluded) was assessed immediately before its final merge/close event. These numbers describe checklist behaviour on historical data; **they are not a validation of readiness**, for which no ground truth exists.

| Group | PRs | Needs attention | No blocking issues found |
|---|---|---|---|
| Merged, human-authored | 3,724 | 49% | 51% |
| Merged, bot-authored | 329 | 22% | 78% |
| Closed, human-authored | 730 | 98% | 2% |
| Closed, bot-authored | 156 | 100% | 0% |

Attention rates per item (merged-human / closed-human): human approval 17% / 88%, change requests 1% / 7%, unanswered threads 23% / 20%, review coverage 14% / 64%, recent activity 1% / 60%, change size 21% / 22%. External checks were unknown for all PRs.

### Auxiliary baseline: merged vs. closed (not a readiness measure)

The checklist and this baseline are evaluated separately. The checklist is checked by unit tests and described by the statistics above; this baseline only measures outcome prediction. **Its metrics are not readiness accuracy.**

Predicts whether a PR was closed without merging, from checklist signals taken immediately before the final merge/close event. Merged vs. closed is only a proxy: PRs can be merged without being ready, or closed for unrelated reasons (superseded, duplicate, abandoned).

- Split: chronological 70/15/15 per repository (3,452 / 742 / 745 PRs). Regularization strength selected on validation (ROC-AUC).
- Predictors: majority class; the checklist label used as a rule; logistic regression (standardized, class-balanced).
- **Primary model excludes recent activity.** Immediately before the decision, the median time since human activity was 0.01 days for merged PRs and 56 days for closed PRs: inactivity mainly reflects how PRs end (abandoned PRs are closed), so a model using it is reported only as a labelled diagnostic.
- Leakage check: deleting every event at or after the decision time leaves all 4,939 PRs' features unchanged. Thread replies (untimed) and change size (final) are not timestamped and are listed as caveats.
- Caveats: thread replies are untimed and change size is final.
- Bot-authored PRs are included in training and reported separately.
- Settings were frozen (with a code fingerprint) before the single test run; repeat test runs are refused.

**Validation (742 PRs; closed share 14.1%):**

| Predictor | Subset | PRs | ROC-AUC | PR-AUC (closed) | Balanced accuracy |
|---|---|---|---|---|---|
| Majority class | all | 742 | 0.500 | 0.141 | 0.500 |
| Checklist label rule | all | 742 | 0.757 | 0.257 | 0.757 |
| Checklist label rule | human | 688 | 0.745 | 0.245 | 0.745 |
| Checklist label rule | bot | 54 | 0.911 | 0.529 | 0.911 |
| Logistic regression (primary, no activity) | all | 742 | 0.913 | 0.576 | 0.874 |
| Logistic regression (primary, no activity) | human | 688 | 0.906 | 0.525 | 0.868 |
| Logistic regression (primary, no activity) | bot | 54 | 0.938 | 0.918 | 0.944 |
| Logistic regression (diagnostic, all signals) | all | 742 | 0.969 | 0.880 | 0.917 |

**Test (745 PRs, held out, evaluated once with frozen settings; closed share 13.4%):**

| Predictor | Subset | PRs | ROC-AUC | PR-AUC (closed) | Balanced accuracy |
|---|---|---|---|---|---|
| Majority class | all | 745 | 0.500 | 0.134 | 0.500 |
| Checklist label rule | all | 745 | 0.793 | 0.277 | 0.793 |
| Checklist label rule | human | 681 | 0.782 | 0.259 | 0.782 |
| Checklist label rule | bot | 64 | 0.904 | 0.545 | 0.904 |
| Logistic regression (primary, no activity) | all | 745 | 0.878 | 0.569 | 0.874 |
| Logistic regression (primary, no activity) | human | 681 | 0.863 | 0.480 | 0.862 |
| Logistic regression (primary, no activity) | bot | 64 | 0.995 | 0.979 | 0.981 |
| Logistic regression (diagnostic, all signals) | all | 745 | 0.916 | 0.751 | 0.822 |

Bot subsets are small (54 validation, 64 test PRs). No statistical significance test has been run. These are outcome-prediction results for a proxy task, not readiness accuracy.

### Limitations

- No ground truth for readiness; the checklist has not been manually validated (a manual assessment of 30 PRs is a stretch goal and has not been done).
- Thresholds are unvalidated heuristics.
- CI status, quality gates, merge conflicts, branch protection rules, and commit history are not in the dataset.
- Thread resolution is approximated from author replies, which have no timestamps.
- Approval features carry most of the auxiliary model's weight, but approvals partly reflect repository merge policies (e.g. branch protection requiring an approval before merge). Their predictive weight therefore does not show that approvals indicate readiness.

## AI-Assisted Code Review

Reviews a pull request diff with a local Ollama model (`qwen2.5-coder:3b`) and returns line-referenced findings. It is decision support: it never approves, rejects, or merges a pull request.

### Pipeline

`code_review/ai_reviewer.py` separates three steps:

1. **Prompt construction** (`build_messages`): versioned prompts. v2 and v3 show the diff with new-file line numbers so findings can cite a line.
2. **Model invocation** (`OllamaClient`): queries the model's reported context length first and sets `num_ctx` to `min(8192, context length)`; if the length is unavailable, `num_ctx` is not set. `temperature` is 0.
3. **Response parsing** (`parse_response`): strict schema validation. Any malformed field makes the whole response `invalid_response`; it is never turned into findings or an empty result.

`run_review()` returns an explicit status (`findings`, `no_findings`, `invalid_response`, `model_error`) with the raw response, prompt version and hash, model, options, and model metadata. `review_code(pr_title, file_path, code_diff, debug=False)` keeps its original interface: it returns `{"findings": [...]}` and raises `RuntimeError` on model errors or invalid responses.

| Prompt | Description | Finding fields |
|---|---|---|
| v1 | Original prompt, kept verbatim for comparison | finding, explanation, suggestion, confidence |
| v2 | Line-numbered diff, defect checklist, no fixture-specific rule | + line, category, severity |
| v3 (default) | v2 plus rules against reporting problems the shown code already handles | same as v2 |

Categories: correctness, null_safety, error_handling, input_validation, resource_management, security. Severities: high, medium, low.

### Planted-defect benchmark

`code_review/benchmark/` contains 24 pairs (48 cases): each pair is a diff with one planted defect (known category and new-file line) and a clean twin. Languages: Python, TypeScript/TSX, PHP, C#. Defect types: off-by-one, null/undefined dereference, divide-by-zero, inverted condition, assignment in condition, missing await, unchecked index, swapped arguments, resource leak, swallowed exception, SQL/command injection, path traversal.

- **Development** (12 pairs): used for prompt development.
- **Held-out** (12 pairs): frozen before prompt v2 was written (`held_out.freeze.json`, SHA-256 of the file with LF line endings). It is never used for iteration and may be evaluated only once (see "Held-out run marker").

### Metrics

Valid-response metrics exclude cases with an invalid response or model error from the denominator. Conservative metrics count those cases as failures. Both are reported, with numerator and denominator, and invalid-response and model-error rates are reported separately.

| Metric | Numerator | Denominator |
|---|---|---|
| Detection rate | Defect cases with >= 1 finding | Defect cases with a valid response |
| Localized detection rate | Defect cases with a finding within +/-1 of the expected line | Defect cases with a valid response |
| False-positive rate | Clean cases with >= 1 finding | Clean cases with a valid response |
| Precision | Defect cases with >= 1 finding | Cases with a valid response and >= 1 finding |
| Line accuracy | Detected defect cases with a finding within +/-1 of the expected line | Detected defect cases |
| Category accuracy | Detected defect cases with a finding in an acceptable category | Detected defect cases |
| Pair accuracy | Pairs where the defect case is flagged and the clean twin is not | Pairs with both responses valid |
| Conservative detection rate | Defect cases with a valid response and >= 1 finding | All defect cases |
| Conservative localized detection rate | Defect cases with a valid response and a finding within +/-1 of the expected line | All defect cases |
| Conservative pair accuracy | Pairs with both responses valid, the defect case flagged, and the clean twin not flagged | All pairs |
| Invalid response rate / model error rate | Cases with that status | All cases |

Line accuracy, localized detection and category accuracy are not available for v1, whose response schema has no line or category field.

**Common valid pairs.** Each run that includes v1, v2 and v3 also reports all metrics restricted to the pairs where all three prompts produced valid responses for both cases, so every prompt is scored on the same pairs. Excluded pairs are listed.

**Diagnostic sensitivity analysis (held-out only).** Held-out results are reported twice:
- **Primary analysis:** all frozen held-out cases. This is the result of the benchmark.
- **Diagnostic sensitivity analysis:** the same metrics excluding pairs `held-04`, `held-05` and `held-10`, whose clean twins resemble v3's examples of already-handled code. These pairs were chosen after inspecting the cases, so this analysis is potentially biased. It only indicates how much the overlap may affect the results, and never replaces the primary analysis.

### Held-out run marker

Before the first held-out case is sent to the model, the runner atomically creates `code_review/benchmark/held_out.run_marker.json` (exclusive creation; a second start fails). It records the held-out SHA-256, prompt versions and hashes, start time, and run status (`started`, then `completed` with the results path, or `failed` with the error). The marker lives outside the Git-ignored results directory so that results cleanup cannot remove it.

Run order: verify the freeze manifest → stop if the marker or a held-out result already exists → fetch model metadata (no cases sent; stop if unavailable) → create the marker → send cases. If the marker exists, the runner stops before contacting the model.

During a held-out run, the first model-call failure (status `model_error`, e.g. Ollama unreachable or timed out) stops the run: no further cases are sent, no results file is written, and the marker is set to `failed` with the error and the number of cases already sent. Invalid model responses (`invalid_response`) are a separate status and do not stop the run. Development runs record model errors and continue.

The runner never resets or deletes the marker, and there is no reset command. If a run was interrupted (status `started` or `failed`), held-out cases may already have been sent to the model, so the held-out set may no longer be unseen. Manual recovery:
1. Do not delete the marker. Read its status and error, look for partial results, and determine what happened to the process.
2. Record what happened, including whether any held-out case reached the model.
3. If any held-out case was sent, treat the held-out set as exposed: report this, and prefer a new, independently frozen held-out set over re-running.
4. Only after this investigation, and with the decision documented, move the marker aside manually (keep it as evidence) before any new run.

### Running

```bash
python components/pull-request/run_code_review_benchmark.py dev --prompts v1 v2 v3
python components/pull-request/run_code_review_benchmark.py heldout --prompts v1 v2 v3   # once only
python components/pull-request/run_code_review_benchmark.py realdata --prompt v3          # descriptive only
python components/pull-request/run_code_review_benchmark.py check-freeze
```

Results are written to `code_review/data/results/` (ignored by Git) and are never overwritten. The earlier 30-example CSV files are kept unchanged.

### Development results (12 pairs)

| Metric | v1 | v2 | v3 |
|---|---|---|---|
| Detection rate | 0.167 (2/12) | 0.583 (7/12) | 0.636 (7/11) |
| Localized detection rate | n/a (no line field) | 0.500 (6/12) | 0.545 (6/11) |
| False-positive rate | 0.083 (1/12) | 0.333 (4/12) | 0.250 (3/12) |
| Precision | 0.667 (2/3) | 0.636 (7/11) | 0.700 (7/10) |
| Line accuracy | n/a | 0.857 (6/7) | 0.857 (6/7) |
| Category accuracy | n/a | 0.714 (5/7) | 0.714 (5/7) |
| Pair accuracy | 0.083 (1/12) | 0.333 (4/12) | 0.455 (5/11) |
| Conservative detection rate | 0.167 (2/12) | 0.583 (7/12) | 0.583 (7/12) |
| Conservative localized detection rate | n/a | 0.500 (6/12) | 0.500 (6/12) |
| Conservative pair accuracy | 0.083 (1/12) | 0.333 (4/12) | 0.417 (5/12) |
| Invalid responses / model errors | 0/24 / 0/24 | 0/24 / 0/24 | 1/24 / 0/24 |

Common valid pairs (11 pairs; `dev-04` excluded because v3's response for its defect case was invalid):

| Metric | v1 | v2 | v3 |
|---|---|---|---|
| Detection rate | 0.182 (2/11) | 0.636 (7/11) | 0.636 (7/11) |
| False-positive rate | 0.091 (1/11) | 0.364 (4/11) | 0.273 (3/11) |
| Precision | 0.667 (2/3) | 0.636 (7/11) | 0.700 (7/10) |
| Pair accuracy | 0.091 (1/11) | 0.364 (4/11) | 0.455 (5/11) |

- All three v1 findings were the same "division-by-zero" claim, including on an SQL-injection case and a clean twin: the original prompt's division-by-zero rule biased the model.
- v3 was selected by a rule fixed before its run: highest development pair accuracy, then lower false-positive rate. Under the conservative and common-pairs comparisons, v3 detects the same number of defects as v2; its advantage is one fewer false positive and one more correct pair out of 12.
- v3's invalid response (`dev-04`, truncated JSON) cited a line within tolerance of the defect but with an incorrect explanation, so excluding it, counting it as a miss, or counting it as a hit would each be debatable.
- The development results were produced before the conservative and common-pairs metrics existed; they were recomputed from the stored records without new model calls.
- The held-out split has not been evaluated yet.

### Limitations

These limitations bound what the benchmark can show; results should not be read as general bug-detection accuracy.

- **Specified defect families, not open-ended review.** The v2/v3 prompts name 13 of the 14 planted defect types (all except React state mutation). The results measure detection of these named defect families, not unrestricted bug discovery.
- **Overlap between v3 and held-out clean cases.** v3's examples of already-handled code (guard clauses, parameterised queries, using/with blocks, logged and re-raised exceptions) resemble the fixes in held-out clean cases `held-04`, `held-05` and `held-10`. This may lower v3's held-out false-positive rate; the diagnostic sensitivity analysis indicates how much.
- **Familiar defect families.** 10 of the 12 held-out defect types also appear in the development set, mostly as the same defect in another language. The held-out set tests generalization to new code within mostly familiar defect families, not generalization to unseen defect types.
- **Confounded v1 → v2 comparison.** v2 changes prompt wording, adds line-number annotations, and changes the response schema at the same time, so its improvement over v1 cannot be attributed to any single change.
- **Same author, no peer validation.** The cases and the prompts were authored by the same developer (assistant-generated); no peer-authored or peer-validated cases were available.
- **Small benchmark, no significance testing.** 12 pairs per split; differences of one or two cases are not meaningful, and no statistical significance test is run.
- **Line location is not correctness.** A finding on the correct line does not prove that its explanation or suggested fix is correct; some findings cite the right line with a wrong explanation.
- **Synthetic cases.** Planted defects are short, self-contained diffs with one defect each; real review hunks are partial and mostly UI/config code.
- **No real-data ground truth.** Real-data runs are descriptive only: human review comments are not ground-truth bug labels.
