
from pathlib import Path
import pandas as pd

# Dataset folder
DATASET_FOLDER = Path(
    r"C:\Users\Evindu\OneDrive\Desktop\Devintel Dataset"
)

# Expected dataset files and row counts
DATASETS = {
    "final_sprint_issues.csv": {
        "expected_rows": 7997,
        "expected_columns": 21,
    },
    "final_sprint_metadata.csv": {
        "expected_rows": 884,
        "expected_columns": 9,
    },
    "final_sprint_change_logs.csv": {
        "expected_rows": 179782,
        "expected_columns": 7,
    },
}

all_passed = True

for filename, expected in DATASETS.items():
    file_path = DATASET_FOLDER / filename

    print(f"\n{'=' * 60}")
    print(f"Checking: {filename}")
    print("=" * 60)

    if not file_path.exists():
        print("Status: ERROR - File not found")
        print("Expected path:", file_path)
        all_passed = False
        continue

    try:
        df = pd.read_csv(
            file_path,
            encoding="utf-8-sig",
            low_memory=False,
        )

        actual_rows = len(df)
        actual_columns = len(df.columns)

        print("Status: OK")
        print("Rows:", actual_rows)
        print("Columns:", actual_columns)
        print("Column names:", df.columns.tolist())

        rows_match = actual_rows == expected["expected_rows"]
        columns_match = actual_columns == expected["expected_columns"]

        print(
            "Row count:",
            "PASS" if rows_match else
            f"FAIL (expected {expected['expected_rows']})"
        )
        print(
            "Column count:",
            "PASS" if columns_match else
            f"FAIL (expected {expected['expected_columns']})"
        )

        if not rows_match or not columns_match:
            all_passed = False

        # Display missing values for data-quality inspection
        missing_values = df.isnull().sum()
        missing_columns = missing_values[missing_values > 0]

        if not missing_columns.empty:
            print("\nColumns containing missing values:")
            print(missing_columns.to_string())
        else:
            print("Missing values: None")

    except Exception as error:
        print("Status: ERROR")
        print(repr(error))
        all_passed = False

print(f"\n{'=' * 60}")

if all_passed:
    print("RESULT: ALL DATASETS PASSED VALIDATION")
else:
    print("RESULT: SOME DATASETS NEED ATTENTION")

print("=" * 60)
