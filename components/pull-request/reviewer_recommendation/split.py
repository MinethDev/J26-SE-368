"""Chronological train/validation/test split, applied within each repository."""

import numpy as np
import pandas as pd


SPLITS = ("train", "validation", "test")


def assign_chronological_splits(
    prs: pd.DataFrame,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
) -> pd.DataFrame:
    """
    Assign each PR to a split by creation order within its repository.

    Splitting per repository keeps every repository represented in each
    split; a single global cut would leave most repositories out of test.
    """

    if not 0 < train_ratio < 1 or not 0 <= validation_ratio < 1:
        raise ValueError("Split ratios must be between 0 and 1.")

    if train_ratio + validation_ratio >= 1:
        raise ValueError("Train and validation ratios must leave room for test.")

    ordered = prs.sort_values(
        ["repo_full_name", "created_at", "pr_number"], kind="mergesort"
    ).copy()

    position = ordered.groupby("repo_full_name").cumcount().to_numpy()
    size = (
        ordered.groupby("repo_full_name")["pr_number"]
        .transform("size")
        .to_numpy()
    )

    train_end = np.floor(size * train_ratio).astype(int)
    validation_end = np.floor(
        size * (train_ratio + validation_ratio)
    ).astype(int)

    ordered["split"] = np.where(
        position < train_end,
        "train",
        np.where(position < validation_end, "validation", "test"),
    )

    return ordered.reset_index(drop=True)
