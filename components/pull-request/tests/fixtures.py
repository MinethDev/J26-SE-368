"""Small synthetic records shaped like the raw SWE-Review-Chat shard."""

import pandas as pd


def event(event_type, reviewer, timestamp, reviewer_type="User", **extra):
    record = {
        "type": event_type,
        "reviewer": reviewer,
        "reviewer_type": reviewer_type,
        "timestamp": timestamp,
        "body": extra.pop("body", ""),
        "title": None,
        "state": extra.pop("state", None),
        "review_id": extra.pop("review_id", None),
        "comment_id": extra.pop("comment_id", None),
        "path": extra.pop("path", None),
        "diff_hunk": extra.pop("diff_hunk", None),
        "thread_replies": None,
    }
    record.update(extra)
    return record


def pull_request(repo, number, author, created_at, title, events, author_type="User"):
    return {
        "repo_full_name": repo,
        "pr_number": number,
        "title": title,
        "review_conversations": events,
        "repo_url": f"https://github.com/{repo}",
        "pr_url": f"https://github.com/{repo}/pull/{number}",
        "created_at": created_at,
        "created_by": author,
        "created_by_type": author_type,
        "state": "merged",
        "closed_at": None,
        "merged_at": None,
        "merged_by": None,
        "merged_by_type": "Unknown",
        "additions": 10,
        "deletions": 2,
    }


def raw_frame(pull_requests):
    return pd.DataFrame(pull_requests)


def pairs_frame(rows):
    """Build review pairs: (repo, pr_number, reviewer, reviewed_at, pr_author, pr_title)."""

    frame = pd.DataFrame(
        rows,
        columns=[
            "repo_full_name",
            "pr_number",
            "reviewer",
            "reviewed_at",
            "pr_author",
            "pr_title",
        ],
    )
    frame["reviewed_at"] = pd.to_datetime(frame["reviewed_at"], utc=True)
    frame["pr_created_at"] = frame["reviewed_at"]
    return frame
