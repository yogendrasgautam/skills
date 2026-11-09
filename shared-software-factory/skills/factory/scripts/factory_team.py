"""Team-coordination helpers for the shared software factory (stdlib only)."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

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


# --- Board rebuild from GitHub state -------------------------------------------------

STALE_AFTER_DAYS = 3
_MARKER_RE = re.compile(r"<!--\s*factory:(\S+?(?: [^\s>]+?)?)\s*-->")


def markers_from_comments(bodies: list) -> set:
    """Collect `<!-- factory:... -->` markers, e.g. {"spec", "review round-1"}."""
    found = set()
    for body in bodies:
        found.update(_MARKER_RE.findall(body or ""))
    return found


def _label_names(issue: dict) -> list:
    return [lbl.get("name") for lbl in issue.get("labels") or []]


def derive_stage(issue: dict, pr: Optional[dict], markers: set) -> str:
    """Pipeline stage from labels, the linked PR and comment markers (first match wins)."""
    labels = _label_names(issue)
    pr_state = (pr or {}).get("state")
    if pr_state == "MERGED":
        return "merged"
    if "needs-human-review" in labels:
        return "needs-human"
    if pr_state == "OPEN":
        if "factory-approved" in labels:
            return "pr-open"
        if "decision" in markers:
            return "approve"
        if any(m.startswith("review") for m in markers):
            return "review"
        return "build"
    if "spec" in markers:
        return "build"
    if IN_PROGRESS_LABEL in labels:
        return "spec"
    return "blocked"


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _mentions(pr: dict, number: int) -> bool:
    return re.search(r"#%d(?!\d)" % number, pr.get("body") or "") is not None


def _pick_pr(number: int, prs: list):
    """(chosen PR or None, note). Open PRs win; a merged PR is used only if none is open."""
    linked = [p for p in prs if _mentions(p, number)]
    for state in ("OPEN", "MERGED"):
        group = sorted(
            (p for p in linked if p.get("state") == state),
            key=lambda p: p.get("updatedAt", ""),
            reverse=True,
        )
        if group:
            others = ", ".join("[#%d](%s)" % (p["number"], p.get("url", "")) for p in group[1:])
            note = "other PRs: " + others if others else ""
            return group[0], note
    return None, ""


def build_board(repo: str, issues: list, prs: list, comments: dict, me: str, now: str) -> dict:
    """Rebuild board.json from issues, PRs and issue comments (nothing local is trusted)."""
    now_dt = _parse_ts(now)
    jobs = []
    for issue in issues:
        labels = _label_names(issue)
        if "factory" not in labels or "epic" in labels:
            continue
        number = issue["number"]
        pr, note = _pick_pr(number, prs)
        markers = markers_from_comments(comments.get(number, []))
        stage = derive_stage(issue, pr, markers)
        claim = claim_state(issue, me)
        owner = (_assignees(issue) or [None])[0]
        updated = issue.get("updatedAt", "")
        stale = (
            claim.state != "free"
            and stage not in ("merged", "needs-human")
            and bool(updated)
            and now_dt - _parse_ts(updated) > timedelta(days=STALE_AFTER_DAYS)
        )
        rounds = [
            int(m.rsplit("-", 1)[1])
            for m in markers
            if m.startswith("review round-") and m.rsplit("-", 1)[1].isdigit()
        ]
        jid = job_id(number, issue.get("title", ""))
        jobs.append({
            "id": jid,
            "title": issue.get("title", ""),
            "plan": None,
            "ticket": None,
            "issue": number,
            "issueUrl": issue.get("url", ""),
            "epic": None,
            "pr": pr["number"] if pr else None,
            "prUrl": pr["url"] if pr else "",
            "owner": owner,
            "blockedBy": [],
            "branch": "factory/" + jid,
            "base": "main",
            "stage": stage,
            "round": max(rounds) if rounds else 0,
            "reviews": {},
            "rounds": [],
            "decision": None,
            "stale": stale,
            "note": note,
            "updated": updated,
        })
    return {"repo": repo, "jobs": jobs}


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|")


def render_status(board: dict, repo: str) -> str:
    """Markdown status table for the board."""
    lines = [
        "| Job | Stage | Owner | Issue | PR | Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for job in board.get("jobs", []):
        issue_url = job.get("issueUrl") or "https://github.com/%s/issues/%d" % (repo, job["issue"])
        issue_cell = "[#%d](%s)" % (job["issue"], issue_url)
        pr_cell = "[#%d](%s)" % (job["pr"], job["prUrl"]) if job.get("prUrl") else "—"
        stage = job["stage"] + (" (stale)" if job.get("stale") else "")
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            _cell(job["id"]), stage, job.get("owner") or "—",
            issue_cell, pr_cell, _cell(job.get("note", ""))))
    return "\n".join(lines) + "\n"


# --- gh-backed CLI -------------------------------------------------------------------

ISSUE_FIELDS = "number,title,url,state,labels,assignees,updatedAt"
PR_FIELDS = "number,url,state,body,updatedAt,headRefName"

# Tests (and Task 4) may override the runner; None means the real `gh`.
RUN: Optional[Callable] = None


def default_run(args: list) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def fetch_state(repo: str, run: Callable):
    """(issues, prs, {issue number: [comment bodies]}) from GitHub via `run(argv) -> stdout`."""
    issues = json.loads(run([
        "gh", "issue", "list", "--repo", repo, "--label", "factory", "--state", "all",
        "--limit", "500", "--json", ISSUE_FIELDS]))
    prs = json.loads(run([
        "gh", "pr", "list", "--repo", repo, "--state", "all",
        "--limit", "500", "--json", PR_FIELDS]))
    comments = {}
    for issue in issues:
        n = issue["number"]
        data = json.loads(run(["gh", "issue", "view", str(n), "--repo", repo, "--json", "comments"]))
        comments[n] = [c.get("body", "") for c in data.get("comments") or []]
    return issues, prs, comments


def _board_for(args, run: Callable) -> dict:
    me = args.me or run(["gh", "api", "user", "--jq", ".login"]).strip()
    issues, prs, comments = fetch_state(args.repo, run)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return build_board(args.repo, issues, prs, comments, me, now)


def _write_board(board: dict, out: str) -> None:
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "board.json"), "w", encoding="utf-8") as f:
        json.dump(board, f, indent=2)
        f.write("\n")


def _cmd_status(args, run):
    sys.stdout.write(render_status(_board_for(args, run), args.repo))


def _cmd_board(args, run):
    _write_board(_board_for(args, run), args.out)


def _cmd_dashboard(args, run):
    _write_board(_board_for(args, run), args.out)
    template = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "dashboard.html")
    shutil.copyfile(template, os.path.join(args.out, "dashboard.html"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory_team.py")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler, helptext in (
        ("status", _cmd_status, "print the status table"),
        ("board", _cmd_board, "write <out>/board.json"),
        ("dashboard", _cmd_dashboard, "write board.json and dashboard.html to <out>"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--repo", required=True, help="OWNER/NAME")
        p.add_argument("--me", help="GitHub login (default: gh api user)")
        if name != "status":
            p.add_argument("--out", default="factory", help="output directory (default: factory)")
        p.set_defaults(handler=handler)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    run = RUN or default_run
    try:
        args.handler(args, run)
    except FileNotFoundError:
        sys.stderr.write("error: the gh CLI was not found; install it and run `gh auth login`\n")
        return 1
    except subprocess.CalledProcessError as e:
        detail = ((e.stderr or "").strip().splitlines() or ["gh failed (run `gh auth login`?)"])[0]
        sys.stderr.write("error: gh failed: %s\n" % detail)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
