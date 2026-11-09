"""Team-coordination helpers for the shared software factory (stdlib only)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

IN_PROGRESS_LABEL = "in-progress"


def job_id(issue: int, title_or_slug: str) -> str:
    """Job id from an issue number and the first four words of its slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", title_or_slug.lower()).strip("-")
    words = [w for w in slug.split("-")[:4] if w]
    return "-".join([str(issue)] + words)


@dataclass(frozen=True)
class Claim:
    state: str  # "free" | "mine" | "other"
    holder: Optional[str]
    url: str


def _assignees(issue: dict) -> list:
    return [a.get("login") for a in issue.get("assignees") or []]


def claim_state(issue: dict, me: str) -> Claim:
    """Who holds the issue. `issue` is `gh issue view --json number,url,assignees,labels`."""
    url = issue.get("url", "")
    assignees = _assignees(issue)
    labels = [l.get("name") for l in issue.get("labels") or []]
    if not assignees:
        if IN_PROGRESS_LABEL in labels:
            return Claim("other", None, url)
        return Claim("free", None, url)
    if assignees == [me]:
        return Claim("mine", me, url)
    holder = next((a for a in assignees if a != me), assignees[0])
    return Claim("other", holder, url)


def decide_claim_winner(issue_after_write: dict, me: str) -> bool:
    """True only if `me` is the first assignee after writing the claim."""
    assignees = _assignees(issue_after_write)
    return bool(assignees) and assignees[0] == me
