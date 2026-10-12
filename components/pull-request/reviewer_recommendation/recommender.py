"""
Explainable reviewer recommender.

For a pull request opened at time t, candidates and all signals are computed
only from review activity strictly before t, and only from information known
when the PR is opened (repository, author, title, creation time).

Signals (each scaled to [0, 1] within the candidate set):
- activity:         recency-weighted number of PRs reviewed in the repository
- author_affinity:  recency-weighted number of this author's PRs reviewed
- title_similarity: highest TF-IDF cosine similarity between this PR's title
                    and titles of PRs the candidate reviewed
"""

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from reviewer_recommendation.identity import is_bot, same_login


SIGNALS = ("activity", "author_affinity", "title_similarity")
RECENT_WINDOW_DAYS = 90
NANOSECONDS_PER_DAY = 86_400 * 10**9

SIGNAL_COLUMNS = [
    "repo_review_count",
    "recent_review_count",
    "last_review_days",
    "author_review_count",
    "best_match_similarity",
    "best_match_title",
]


@dataclass(frozen=True)
class RecommenderConfig:
    activity_weight: float = 1.0
    author_weight: float = 1.0
    similarity_weight: float = 1.0
    half_life_days: float = 90.0


@dataclass
class Recommendation:
    reviewer: str
    score: float
    signals: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def fit_title_vectorizer(titles) -> TfidfVectorizer:
    """Fit the title vocabulary (use training-split titles only)."""

    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    vectorizer.fit(pd.Series(titles).fillna("").astype(str))

    return vectorizer


def to_utc_timestamp(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")

    return timestamp.tz_convert("UTC")


def _to_nanoseconds(values) -> np.ndarray:
    return pd.DatetimeIndex(values).tz_convert("UTC").as_unit("ns").asi8


def activity_column(half_life_days) -> str:
    return f"activity@{float(half_life_days):g}"


def author_column(half_life_days) -> str:
    return f"author_affinity@{float(half_life_days):g}"


class ReviewHistory:
    """As-of index over (PR, reviewer) pairs, one time-sorted block per repo."""

    def __init__(self, pairs: pd.DataFrame, vectorizer: TfidfVectorizer):
        self.vectorizer = vectorizer
        self._blocks = {}

        # Defensive: bots must never become candidates.
        human = ~pairs["reviewer"].map(is_bot).astype(bool)
        pairs = pairs[human]

        for repo, block in pairs.groupby("repo_full_name", sort=False):
            block = block.sort_values(
                ["reviewed_at", "pr_number", "reviewer"], kind="mergesort"
            ).reset_index(drop=True)

            self._blocks[repo] = (
                block,
                _to_nanoseconds(block["reviewed_at"]),
                vectorizer.transform(block["pr_title"].fillna("").astype(str)),
            )

    def before(self, repo, timestamp):
        """Return pairs (and their title vectors) reviewed strictly before timestamp."""

        if repo not in self._blocks:
            return None

        block, times, titles = self._blocks[repo]
        end = int(np.searchsorted(times, to_utc_timestamp(timestamp).value, side="left"))

        return block.iloc[:end], times[:end], titles[:end]


def candidate_signals(
    history: ReviewHistory,
    repo,
    author,
    title,
    created_at,
    half_lives=(90.0,),
) -> pd.DataFrame:
    """
    Raw signal values for every eligible candidate, indexed by reviewer.

    Rows are returned in the deterministic tie-break order used for ranking:
    more PRs reviewed in the repository first, then login alphabetically.
    """

    columns = SIGNAL_COLUMNS + [
        name
        for half_life in half_lives
        for name in (activity_column(half_life), author_column(half_life))
    ]
    empty = pd.DataFrame(columns=columns, index=pd.Index([], name="reviewer"))

    found = history.before(repo, created_at)

    if found is None:
        return empty

    block, times, titles = found

    eligible = ~np.array(
        [same_login(reviewer, author) for reviewer in block["reviewer"]],
        dtype=bool,
    )

    if not eligible.any():
        return empty

    block = block[eligible]
    times = times[eligible]
    titles = titles[eligible]

    query_time = to_utc_timestamp(created_at).value
    age_days = (query_time - times) / NANOSECONDS_PER_DAY

    query_vector = history.vectorizer.transform([str(title or "")])
    similarity = np.asarray((titles @ query_vector.T).todense()).ravel()

    is_author_pr = np.array(
        [same_login(pr_author, author) for pr_author in block["pr_author"]],
        dtype=bool,
    )

    frame = pd.DataFrame({
        "reviewer": block["reviewer"].to_numpy(),
        "age_days": age_days,
        "recent": age_days <= RECENT_WINDOW_DAYS,
        "is_author_pr": is_author_pr,
        "similarity": similarity,
        "pr_title": block["pr_title"].to_numpy(),
    })

    grouped = frame.groupby("reviewer", sort=True)

    signals = pd.DataFrame({
        "repo_review_count": grouped.size(),
        "recent_review_count": grouped["recent"].sum(),
        "last_review_days": grouped["age_days"].min(),
        "author_review_count": grouped["is_author_pr"].sum(),
    })

    best = frame.loc[grouped["similarity"].idxmax()].set_index("reviewer")
    signals["best_match_similarity"] = best["similarity"]
    signals["best_match_title"] = best["pr_title"]

    for half_life in half_lives:
        weight = np.power(0.5, frame["age_days"] / float(half_life))
        signals[activity_column(half_life)] = weight.groupby(frame["reviewer"]).sum()
        signals[author_column(half_life)] = (
            (weight * frame["is_author_pr"]).groupby(frame["reviewer"]).sum()
        )

    signals.index.name = "reviewer"
    signals = signals.reset_index().sort_values(
        ["repo_review_count", "reviewer"],
        ascending=[False, True],
        kind="mergesort",
    ).set_index("reviewer")

    return signals[columns]


def scale_to_unit(values) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    maximum = values.max() if len(values) else 0.0

    if maximum <= 0:
        return np.zeros_like(values)

    return values / maximum


def normalized_signals(signals: pd.DataFrame, half_life_days) -> dict:
    return {
        "activity": scale_to_unit(signals[activity_column(half_life_days)]),
        "author_affinity": scale_to_unit(signals[author_column(half_life_days)]),
        "title_similarity": scale_to_unit(signals["best_match_similarity"]),
    }


def weighted_scores(normalized: dict, config: RecommenderConfig) -> np.ndarray:
    return (
        config.activity_weight * normalized["activity"]
        + config.author_weight * normalized["author_affinity"]
        + config.similarity_weight * normalized["title_similarity"]
    )


def rank_order(scores) -> np.ndarray:
    """Highest score first; ties keep the candidate tie-break order."""

    return np.argsort(-np.asarray(scores, dtype=float), kind="stable")


def explain(row, repo, author) -> list:
    """Human-readable evidence for one candidate."""

    reasons = [
        f"Reviewed {int(row['repo_review_count'])} earlier PR(s) in {repo}; "
        f"most recent {row['last_review_days']:.0f} day(s) before this PR "
        f"({int(row['recent_review_count'])} in the last {RECENT_WINDOW_DAYS} days)"
    ]

    if row["author_review_count"] > 0:
        reasons.append(
            f"Reviewed {int(row['author_review_count'])} earlier PR(s) by {author} "
            f"(recency-weighted affinity {row['author_affinity']:.2f})"
        )

    if row["best_match_similarity"] > 0:
        reasons.append(
            f"Reviewed a PR with a similar title: \"{row['best_match_title']}\" "
            f"(similarity {row['best_match_similarity']:.2f})"
        )

    return reasons


class ReviewerRecommender:
    """Rank human reviewers for a PR, with per-candidate explanations."""

    def __init__(self, history: ReviewHistory, config: RecommenderConfig = None):
        self.history = history
        self.config = config or RecommenderConfig()

    def rank(self, repo, author, title, created_at) -> pd.DataFrame:
        signals = candidate_signals(
            self.history,
            repo,
            author,
            title,
            created_at,
            half_lives=(self.config.half_life_days,),
        )

        if signals.empty:
            return signals.assign(score=pd.Series(dtype=float))

        normalized = normalized_signals(signals, self.config.half_life_days)
        scores = weighted_scores(normalized, self.config)

        ranked = signals.copy()

        for name, values in normalized.items():
            ranked[name] = values

        ranked["score"] = scores

        return ranked.iloc[rank_order(scores)]

    def recommend(self, repo, author, title, created_at, k=5) -> list:
        ranked = self.rank(repo, author, title, created_at).head(k)

        return [
            Recommendation(
                reviewer=reviewer,
                score=round(float(row["score"]), 4),
                signals={name: round(float(row[name]), 4) for name in SIGNALS},
                reasons=explain(row, repo, author),
            )
            for reviewer, row in ranked.iterrows()
        ]
