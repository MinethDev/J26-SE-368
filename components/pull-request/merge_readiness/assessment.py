"""
Explainable merge-readiness checklist.

Each item reports a status (pass / attention / unknown), a severity for
attention items, the evidence behind it, and how the rule is grounded
(heuristic threshold, approximation, or input not provided).
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from merge_readiness.config import ReadinessThresholds
from merge_readiness.context import PRContext, to_utc
from merge_readiness.signals import ReadinessSignals, compute_signals


PASS, ATTENTION, UNKNOWN = "pass", "attention", "unknown"
BLOCKING, ADVISORY = "blocking", "advisory"

LABEL_READY = "No blocking issues found: ready for human merge decision"
LABEL_ATTENTION = "Needs attention"
LABEL_INSUFFICIENT = "Insufficient information"

DISCLAIMER = (
    "Decision support only. This assessment does not approve, reject, or "
    "merge the pull request; a human makes the merge decision."
)

# Items that must be determinable for a "ready" label.
REQUIRED_ITEMS = (
    "human_approval",
    "change_requests",
    "review_coverage",
    "recent_activity",
    "change_size",
)

EXTERNAL_CHECKS = ("ci", "quality_gate", "merge_conflicts")

# Always-missing information in the current offline dataset.
KNOWN_DATA_GAPS = (
    "Review-thread resolution status is not available; unanswered threads are approximated.",
    "Commit/push history is not available; whether approvals predate the latest change cannot be checked.",
)


@dataclass
class ChecklistItem:
    key: str
    name: str
    status: str
    evidence: str
    basis: str
    severity: str = None


@dataclass
class Assessment:
    repo: str
    number: int
    as_of: str
    label: str
    items: list
    missing_information: list = field(default_factory=list)
    thresholds: dict = field(default_factory=dict)
    disclaimer: str = DISCLAIMER

    def to_dict(self):
        return asdict(self)

    def item(self, key) -> ChecklistItem:
        return next(item for item in self.items if item.key == key)


def _names(logins) -> str:
    return ", ".join(logins)


def approval_item(signals: ReadinessSignals, thresholds) -> ChecklistItem:
    count = len(signals.approvals)
    needed = thresholds.min_approvals
    basis = f"Heuristic threshold: at least {needed} current human approval(s)."

    if count >= needed:
        return ChecklistItem("human_approval", "Human approval", PASS,
                             f"Current approval(s) from: {_names(signals.approvals)}.", basis)

    return ChecklistItem("human_approval", "Human approval", ATTENTION,
                         f"{count} of {needed} required current human approval(s).", basis, BLOCKING)


def change_request_item(signals: ReadinessSignals) -> ChecklistItem:
    basis = "Latest review state per reviewer (dismissed reviews are withdrawn)."

    if signals.change_requests:
        return ChecklistItem("change_requests", "Outstanding change requests", ATTENTION,
                             f"Changes still requested by: {_names(signals.change_requests)}.", basis, BLOCKING)

    return ChecklistItem("change_requests", "Outstanding change requests", PASS,
                         "No reviewer's latest review requests changes.", basis)


def thread_item(signals: ReadinessSignals) -> ChecklistItem:
    basis = (
        "Approximation: a thread counts as unanswered when the PR author has not "
        "replied. Resolution status and reply times are not in the dataset."
    )

    if signals.unanswered_threads:
        return ChecklistItem("unanswered_threads", "Unanswered review threads", ATTENTION,
                             f"{signals.unanswered_threads} of {signals.review_threads} inline review thread(s) "
                             f"have no reply from the author.", basis, ADVISORY)

    return ChecklistItem("unanswered_threads", "Unanswered review threads", PASS,
                         f"All {signals.review_threads} inline review thread(s) have an author reply.", basis)


def coverage_item(signals: ReadinessSignals, thresholds) -> ChecklistItem:
    count = len(signals.reviewers)
    needed = thresholds.min_reviewers
    basis = f"Heuristic threshold: at least {needed} human reviewer(s) other than the author."

    if count >= needed:
        return ChecklistItem("review_coverage", "Review coverage", PASS,
                             f"{count} human reviewer(s): {_names(signals.reviewers)}.", basis)

    return ChecklistItem("review_coverage", "Review coverage", ATTENTION,
                         f"{count} of {needed} required human reviewer(s).", basis, ADVISORY)


def activity_item(signals: ReadinessSignals, thresholds) -> ChecklistItem:
    limit = thresholds.stale_after_days
    basis = f"Heuristic threshold: attention after {limit:g} days without human activity."

    if signals.days_since_activity is None:
        return ChecklistItem("recent_activity", "Recent activity", UNKNOWN,
                             "No dated human activity before the assessment time.", basis)

    days = signals.days_since_activity
    evidence = f"Last human activity {days:.1f} day(s) before the assessment."

    if days > limit:
        return ChecklistItem("recent_activity", "Recent activity", ATTENTION, evidence, basis, ADVISORY)

    return ChecklistItem("recent_activity", "Recent activity", PASS, evidence, basis)


def size_item(signals: ReadinessSignals, thresholds) -> ChecklistItem:
    limit = thresholds.large_change_lines
    basis = (
        f"Heuristic threshold: attention above {limit} changed lines. "
        "The dataset provides final additions/deletions only."
    )

    if signals.changed_lines is None:
        return ChecklistItem("change_size", "Change size", UNKNOWN,
                             "Additions/deletions are not available.", basis)

    evidence = f"{signals.changed_lines} changed line(s)."

    if signals.changed_lines > limit:
        return ChecklistItem("change_size", "Change size", ATTENTION, evidence, basis, ADVISORY)

    return ChecklistItem("change_size", "Change size", PASS, evidence, basis)


def external_checks_item(external_checks) -> ChecklistItem:
    basis = (
        "Input expected from the planned DevIntel data integration layer "
        "(CI, quality gate, merge conflicts); not part of the offline dataset."
    )
    provided = {
        name: str(external_checks[name]).lower()
        for name in EXTERNAL_CHECKS
        if external_checks and external_checks.get(name) is not None
    }

    failing = sorted(name for name, status in provided.items() if status == "fail")
    pending = sorted(name for name, status in provided.items() if status == "pending")
    missing = [name for name in EXTERNAL_CHECKS if name not in provided]

    if failing:
        return ChecklistItem("external_checks", "External checks", ATTENTION,
                             f"Failing: {_names(failing)}.", basis, BLOCKING)

    if pending:
        return ChecklistItem("external_checks", "External checks", ATTENTION,
                             f"Pending: {_names(pending)}.", basis, ADVISORY)

    if missing:
        return ChecklistItem("external_checks", "External checks", UNKNOWN,
                             f"Not provided: {_names(missing)}.", basis)

    return ChecklistItem("external_checks", "External checks", PASS,
                         "All external checks passed.", basis)


def overall_label(items) -> str:
    """Any attention item -> needs attention; unknown required item -> insufficient."""

    if any(item.status == ATTENTION for item in items):
        return LABEL_ATTENTION

    if any(item.status == UNKNOWN for item in items if item.key in REQUIRED_ITEMS):
        return LABEL_INSUFFICIENT

    return LABEL_READY


def assess(context: PRContext, as_of=None, thresholds: ReadinessThresholds = None) -> Assessment:
    """Assess a PR using only events strictly before as_of (default: now, UTC)."""

    thresholds = thresholds or ReadinessThresholds()
    as_of = to_utc(as_of if as_of is not None else datetime.now(timezone.utc))
    signals = compute_signals(context, as_of)

    items = [
        approval_item(signals, thresholds),
        change_request_item(signals),
        thread_item(signals),
        coverage_item(signals, thresholds),
        activity_item(signals, thresholds),
        size_item(signals, thresholds),
        external_checks_item(context.external_checks),
    ]

    missing = list(KNOWN_DATA_GAPS) + [
        f"{item.name}: {item.evidence}" for item in items if item.status == UNKNOWN
    ]

    return Assessment(
        repo=context.repo,
        number=context.number,
        as_of=as_of.isoformat(),
        label=overall_label(items),
        items=items,
        missing_information=missing,
        thresholds=asdict(thresholds),
    )
