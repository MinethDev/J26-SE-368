import pandas as pd


def load_parquet(file_path: str) -> pd.DataFrame:
    """
    Load a SWE-Review-Chat Parquet shard into a pandas DataFrame.
    """

    df = pd.read_parquet(file_path)

    print(f"Loaded dataset: {file_path}")
    print(f"Rows: {len(df)}")
    print(f"Columns: {len(df.columns)}")

    return df


if __name__ == "__main__":
    file_path = r"D:\Downloads Folder\train-00001.parquet"

    df = load_parquet(file_path)

    print("\nColumns:")
    print(df.columns.tolist())