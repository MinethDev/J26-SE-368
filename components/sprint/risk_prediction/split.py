"""Chronological train / validation / test split by sprint, within each project."""
import pandas as pd

from risk_prediction.config import MIN_SPRINTS_TO_SPLIT, TRAIN_SHARE, VALIDATION_SHARE


def assign_splits(dataset: pd.DataFrame) -> pd.Series:
    """Returns split name per sprint_id. All checkpoints of a sprint land in the same split."""
    sprints = dataset.drop_duplicates("sprint_id")[["sprint_id", "project_id", "start_date"]]
    split = {}
    for _, group in sprints.sort_values("start_date").groupby("project_id"):
        ids = list(group["sprint_id"])
        n = len(ids)
        if n < MIN_SPRINTS_TO_SPLIT:
            split.update({i: "train" for i in ids})
            continue
        n_train, n_val = int(round(n * TRAIN_SHARE)), max(int(round(n * VALIDATION_SHARE)), 1)
        for k, i in enumerate(ids):
            split[i] = "train" if k < n_train else "validation" if k < n_train + n_val else "test"
    return pd.Series(split, name="split")


def check_no_leakage(dataset: pd.DataFrame) -> None:
    """Within each project, every validation/test sprint starts after every training sprint started."""
    for pid, g in dataset.groupby("project_id"):
        last_train = g.loc[g["split"] == "train", "start_date"].max()
        later = g.loc[g["split"] != "train", "start_date"]
        if len(later) and later.min() < last_train:
            raise AssertionError(f"project {pid}: a held-out sprint starts before a training sprint")
