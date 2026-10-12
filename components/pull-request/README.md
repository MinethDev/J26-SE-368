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
- `reviewer_recommendation/` - reviewer recommendation (planned)
- `summarization/` - pull request summarization (planned)
- `merge_readiness/` - merge-readiness decision support (planned)
- `preprocessing/` - data preparation and preprocessing
- `evaluation/` - component evaluation (planned)

## Data

### Raw dataset

- Input: a single SWE-Review-Chat Parquet shard, `train-00001.parquet` (4,948 pull requests from 10 repositories).
- Source URL / dataset identifier: **unverified, not yet documented**.
- The raw file is stored outside the repository and is not committed.
- Current location: `D:\Downloads Folder\train-00001.parquet`. This path is hardcoded as `INPUT_FILE` in `code_review/dataset_builder.py` and as `file_path` in the `__main__` blocks of the `preprocessing/` modules. Edit it there if the file is stored elsewhere.

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
