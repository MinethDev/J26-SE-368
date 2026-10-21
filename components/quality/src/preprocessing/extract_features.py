from pathlib import Path
import argparse
import re

import pandas as pd


FILE_PATTERN = re.compile(
    r"^(?P<project>.+)-(?P<version>\d+(?:\.\d+)*)_ground-truth-files_dataset\.csv$"
)


def parse_release(path: Path):
    match = FILE_PATTERN.match(path.name)

    if not match:
        return path.stem, "unknown"

    return match.group("project"), match.group("version")


def normalize_bug(value):
    if isinstance(value, bool):
        return value

    value = str(value).strip().lower()

    if value in {"true", "1"}:
        return True

    if value in {"false", "0"}:
        return False

    return None


def strip_comments_and_strings(source: str) -> str:
    """
    Produces a simplified version of Java source for lightweight
    structural counting.

    This is intentionally not a full Java parser.
    """

    # Remove block comments.
    cleaned = re.sub(
        r"/\*.*?\*/",
        " ",
        source,
        flags=re.DOTALL,
    )

    # Remove line comments.
    cleaned = re.sub(
        r"//.*?$",
        " ",
        cleaned,
        flags=re.MULTILINE,
    )

    # Remove string literals.
    cleaned = re.sub(
        r'"(?:\\.|[^"\\])*"',
        '""',
        cleaned,
    )

    # Remove character literals.
    cleaned = re.sub(
        r"'(?:\\.|[^'\\])'",
        "''",
        cleaned,
    )

    return cleaned


def count_pattern(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text))


def extract_source_features(source):
    if not isinstance(source, str):
        source = ""

    raw_lines = source.splitlines()

    total_lines = len(raw_lines)

    blank_lines = sum(
        1 for line in raw_lines if not line.strip()
    )

    source_chars = len(source)

    cleaned = strip_comments_and_strings(source)

    cleaned_lines = cleaned.splitlines()

    code_lines = sum(
        1 for line in cleaned_lines if line.strip()
    )

    # Lightweight Java structural features.
    class_count = count_pattern(
        r"\bclass\s+[A-Za-z_$][A-Za-z0-9_$]*",
        cleaned,
    )

    interface_count = count_pattern(
        r"\binterface\s+[A-Za-z_$][A-Za-z0-9_$]*",
        cleaned,
    )

    enum_count = count_pattern(
        r"\benum\s+[A-Za-z_$][A-Za-z0-9_$]*",
        cleaned,
    )

    import_count = count_pattern(
        r"(?m)^\s*import\s+",
        cleaned,
    )

    if_count = count_pattern(
        r"\bif\s*\(",
        cleaned,
    )

    for_count = count_pattern(
        r"\bfor\s*\(",
        cleaned,
    )

    while_count = count_pattern(
        r"\bwhile\s*\(",
        cleaned,
    )

    switch_count = count_pattern(
        r"\bswitch\s*\(",
        cleaned,
    )

    case_count = count_pattern(
        r"\bcase\b",
        cleaned,
    )

    catch_count = count_pattern(
        r"\bcatch\s*\(",
        cleaned,
    )

    return_count = count_pattern(
        r"\breturn\b",
        cleaned,
    )

    throw_count = count_pattern(
        r"\bthrow\b",
        cleaned,
    )

    new_count = count_pattern(
        r"\bnew\s+[A-Za-z_$]",
        cleaned,
    )

    # Method approximation.
    #
    # Avoid obvious control structures while identifying patterns
    # resembling Java method declarations.
    method_pattern = re.compile(
        r"""
        (?:
            public|protected|private|static|
            final|native|synchronized|abstract|
            transient|strictfp|\s
        )+
        [A-Za-z_$][A-Za-z0-9_$<>\[\],.?]*\s+
        [A-Za-z_$][A-Za-z0-9_$]*\s*
        \([^;{}]*\)
        \s*
        (?:throws\s+[^{]+)?
        \{
        """,
        re.VERBOSE,
    )

    method_count = len(method_pattern.findall(cleaned))

    # Approximate decision complexity.
    decision_points = (
        if_count
        + for_count
        + while_count
        + case_count
        + catch_count
        + count_pattern(r"&&", cleaned)
        + count_pattern(r"\|\|", cleaned)
        + count_pattern(r"\?", cleaned)
    )

    approx_cyclomatic_complexity = 1 + decision_points

    return {
        "total_lines": total_lines,
        "blank_lines": blank_lines,
        "code_lines": code_lines,
        "source_chars": source_chars,
        "class_count": class_count,
        "interface_count": interface_count,
        "enum_count": enum_count,
        "import_count": import_count,
        "method_count": method_count,
        "if_count": if_count,
        "for_count": for_count,
        "while_count": while_count,
        "switch_count": switch_count,
        "case_count": case_count,
        "catch_count": catch_count,
        "return_count": return_count,
        "throw_count": throw_count,
        "new_count": new_count,
        "decision_points": decision_points,
        "approx_cyclomatic_complexity":
            approx_cyclomatic_complexity,
    }


def process_release(path: Path):
    df = pd.read_csv(path)

    project, version = parse_release(path)

    if df.empty:
        print(f"Skipping empty release: {path.name}")
        return pd.DataFrame()

    required = {"File", "Bug", "SRC"}

    missing = required - set(df.columns)

    if missing:
        print(
            f"Skipping {path.name}: "
            f"missing columns {sorted(missing)}"
        )
        return pd.DataFrame()

    records = []

    for _, row in df.iterrows():
        bug = normalize_bug(row["Bug"])

        if bug is None:
            continue

        source = row["SRC"]

        features = extract_source_features(source)

        record = {
            "project": project,
            "version": version,
            "file": row["File"],
            "bug": int(bug),
            **features,
        }

        records.append(record)

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract lightweight Java source-code features "
            "from the defect benchmark."
        )
    )

    parser.add_argument(
        "dataset_dir",
        type=Path,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/processed/jureczko_features.csv"
        ),
    )

    args = parser.parse_args()

    csv_files = sorted(
        args.dataset_dir.rglob(
            "*_ground-truth-files_dataset.csv"
        )
    )

    if not csv_files:
        raise SystemExit(
            f"No matching CSV files found under {args.dataset_dir}"
        )

    frames = []

    for path in csv_files:
        print(f"Processing {path.name}...")

        frame = process_release(path)

        if not frame.empty:
            frames.append(frame)

    if not frames:
        raise SystemExit("No usable observations found.")

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        args.output,
        index=False,
    )

    print("\n=== FEATURE DATASET ===")
    print(f"Rows:     {len(result)}")
    print(f"Columns:  {len(result.columns)}")
    print(f"Projects: {result['project'].nunique()}")
    print(
        f"Releases: "
        f"{result[['project', 'version']].drop_duplicates().shape[0]}"
    )

    print("\n=== TARGET ===")
    print(result["bug"].value_counts())
    print("\nTarget %:")
    print(
        result["bug"]
        .value_counts(normalize=True)
        .mul(100)
        .round(2)
    )

    print("\n=== FEATURES ===")

    feature_columns = [
        column
        for column in result.columns
        if column not in {
            "project",
            "version",
            "file",
            "bug",
        }
    ]

    print(feature_columns)

    print(
        f"\nOutput written to: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()