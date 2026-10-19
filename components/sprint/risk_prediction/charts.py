"""Charts for the report, saved as PNG files in data/risk/charts/."""
import matplotlib

matplotlib.use("Agg")  # write files, no window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import confusion_matrix, roc_curve  # noqa: E402

from sprint_health.config import CHECKPOINTS  # noqa: E402

# Fixed colour per model, so a model keeps its colour on every chart.
COLORS = {
    "majority (always 'missed')": "#8a8985",
    "health score (Step 4)": "#eb6834",
    "logistic regression": "#2a78d6",
    "xgboost": "#1baf7a",
}
INK, MUTED, GRID = "#1f1f1e", "#6b6a66", "#e4e3df"


def _style(ax, title: str):
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=12)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def roc_curves(rows: pd.DataFrame, scores: dict, results: dict, path):
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    for name, s in scores.items():
        fpr, tpr, _ = roc_curve(rows["missed"], s)
        ax.plot(fpr, tpr, color=COLORS[name], linewidth=2, label=f"{name}  (AUC {results[name]['auc']:.3f})")
    ax.plot([0, 1], [0, 1], color=GRID, linewidth=1, linestyle="--")
    ax.set_xlabel("False alarm rate (on-track sprints flagged)", color=MUTED)
    ax.set_ylabel("Hit rate (missed sprints flagged)", color=MUTED)
    _style(ax, "ROC curves, test split")
    ax.legend(frameon=False, fontsize=9, loc="lower right", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def auc_by_checkpoint(results: dict, path):
    names = [n for n in results if n in COLORS and not n.startswith("majority")]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    width = 0.8 / len(names)
    x = np.arange(len(CHECKPOINTS))
    for k, name in enumerate(names):
        vals = [results[name][f"auc@{cp:.0%}"] for cp in CHECKPOINTS]
        bars = ax.bar(x + k * width - 0.4 + width / 2, vals, width - 0.02, color=COLORS[name], label=name)
        ax.bar_label(bars, fmt="%.2f", fontsize=8, color=MUTED, padding=2)
    ax.axhline(0.5, color=MUTED, linewidth=1, linestyle="--")
    ax.text(len(CHECKPOINTS) - 0.45, 0.51, "chance", color=MUTED, fontsize=8, ha="right")
    ax.set_xticks(x, [f"{cp:.0%} through the sprint" for cp in CHECKPOINTS])
    ax.set_ylim(0.4, 1.0)
    ax.set_ylabel("AUC", color=MUTED)
    _style(ax, "How early each model warns, test split")
    ax.legend(frameon=False, fontsize=9, ncols=len(names), loc="upper left", bbox_to_anchor=(0, -0.1), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def confusion(rows: pd.DataFrame, predicted, name: str, path):
    cm = confusion_matrix(rows["missed"], predicted, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.imshow(cm, cmap="Blues")
    labels = ["on track", "missed"]
    for i in range(2):
        for j in range(2):
            ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=14,
                    color="white" if cm[i, j] > cm.max() / 2 else INK)
    ax.set_xticks([0, 1], [f"predicted {lbl}" for lbl in labels])
    ax.set_yticks([0, 1], [f"actually {lbl}" for lbl in labels])
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(f"Confusion matrix, {name}, test split", loc="left", fontsize=12, color=INK, pad=12)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def feature_importance(importance: pd.Series, name: str, path):
    imp = importance[importance > 0].sort_values()
    fig, ax = plt.subplots(figsize=(7, 0.35 * len(imp) + 1.2))
    ax.barh(imp.index, imp.values, color=COLORS.get(name, "#2a78d6"), height=0.6)
    ax.set_xlabel("Mean |contribution| to the prediction (log-odds)", color=MUTED)
    _style(ax, f"What drives the {name} predictions")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
