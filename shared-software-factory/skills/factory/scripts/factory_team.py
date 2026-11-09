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
    """Job id from an issue number and the first four words of its slug ("job" if empty)."""
    slug = re.sub(r"[^a-z0-9]+", "-", title_or_slug.lower()).strip("-")
    words = [w for w in slug.split("-")[:4] if w] or ["job"]
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


def decide_claim_winner_by_events(issue_after_write: dict, events: list, me: str) -> bool:
    """True if `me` has the earliest `assigned` event among the current assignees.

    `events` is a list of {"login", "at"}. No usable event, or a tie for the
    earliest time, falls back to `decide_claim_winner` (first assignee).
    """
    current = set(_assignees(issue_after_write))
    stamps = [
        (e.get("at"), e.get("login")) for e in events or []
        if isinstance(e, dict) and e.get("login") in current and e.get("at")
    ]
    if stamps:
        first = min(at for at, _ in stamps)
        winners = {login for at, login in stamps if at == first}
        if len(winners) == 1:
            return winners.pop() == me
    return decide_claim_winner(issue_after_write, me)


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
    if issue.get("state") == "CLOSED":
        return "closed"
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


_FACTORY_BRANCH_RE = re.compile(r"factory/\d+-")


def _branch_prefix(number: int) -> str:
    return "factory/%d-" % number


def _pick_pr(number: int, prs: list):
    """(chosen PR or None, note). Open PRs win; a merged PR is used only if none is open.

    PRs from forks are ignored. A PR whose head branch is `factory/<number>-...` is
    linked; a `#<number>` mention in the body counts only when no branch matches, and
    never for a PR on another job's `factory/<n>-` branch (e.g. "stacked on #41").
    """
    own = [p for p in prs if not p.get("isCrossRepository")]
    linked = [p for p in own if (p.get("headRefName") or "").startswith(_branch_prefix(number))]
    if not linked:
        linked = [p for p in own
                  if _mentions(p, number) and not _FACTORY_BRANCH_RE.match(p.get("headRefName") or "")]
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
            and stage not in ("merged", "closed", "needs-human")
            and bool(updated)
            and now_dt - _parse_ts(updated) > timedelta(days=STALE_AFTER_DAYS)
        )
        rounds = [
            int(m.rsplit("-", 1)[1])
            for m in markers
            if m.startswith("review round-") and m.rsplit("-", 1)[1].isdigit()
        ]
        # The PR branch pins the id, so renaming the issue never changes it.
        head = (pr or {}).get("headRefName") or ""
        if head.startswith(_branch_prefix(number)):
            jid = head[len("factory/"):]
        else:
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
            "blockerTip": "",
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
PR_FIELDS = "number,url,state,body,updatedAt,headRefName,isCrossRepository"
LIST_LIMIT = 500

# Tests (and Task 4) may override the runner; None means the real `gh`.
RUN: Optional[Callable] = None


def default_run(args: list) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


TRUSTED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


def fetch_state(repo: str, run: Callable):
    """(issues, prs, {open issue number: [comment bodies]}) from GitHub via `run(argv) -> stdout`.

    Comments are fetched only for open issues: a closed issue's stage comes from its
    state and PR alone.
    """
    limit = str(LIST_LIMIT)
    issues = json.loads(run([
        "gh", "issue", "list", "--repo", repo, "--label", "factory", "--state", "all",
        "--limit", limit, "--json", ISSUE_FIELDS]))
    prs = json.loads(run([
        "gh", "pr", "list", "--repo", repo, "--state", "all",
        "--limit", limit, "--json", PR_FIELDS]))
    for kind, items in (("gh issue list", issues), ("gh pr list", prs)):
        if len(items) >= LIST_LIMIT:
            sys.stderr.write("warning: %s results may be truncated at %d\n" % (kind, LIST_LIMIT))
    comments = {}
    for issue in issues:
        if issue.get("state") == "CLOSED":
            continue
        n = issue["number"]
        data = json.loads(run(["gh", "issue", "view", str(n), "--repo", repo, "--json", "comments"]))
        # Only repo insiders may move a job's state; comments without the field are dropped.
        comments[n] = [
            c.get("body", "") for c in data.get("comments") or []
            if c.get("authorAssociation") in TRUSTED_ASSOCIATIONS
        ]
    return issues, prs, comments


def _resolve_me(args, run: Callable, optional: bool) -> str:
    """The caller's login: `--me`, else `gh api user`.

    With `optional`, a refused lookup (e.g. GITHUB_TOKEN in Actions, which may not
    read /user) yields "" — nothing counts as mine. Otherwise the failure propagates.
    """
    if args.me:
        return args.me
    try:
        return run(["gh", "api", "user", "--jq", ".login"]).strip()
    except subprocess.CalledProcessError:
        if optional:
            return ""
        raise


def _board_for(args, run: Callable, me: str) -> dict:
    issues, prs, comments = fetch_state(args.repo, run)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return build_board(args.repo, issues, prs, comments, me, now)


# Orchestrator-owned fields that cannot be derived from GitHub; kept across rebuilds.
LOCAL_FIELDS = ("reviews", "rounds", "decision", "blockedBy",
                "base", "plan", "ticket", "epic", "blockerTip")
# Derived stages that override the orchestrator's own `stage` (GitHub truth wins).
TERMINAL_STAGES = ("merged", "closed", "needs-human")


def merge_local_state(new_board: dict, old_board: dict, me: Optional[str] = None) -> dict:
    """Carry orchestrator-edited fields from the old board into a rebuilt one.

    Only jobs present in both are merged; jobs only in `old_board` are dropped
    (GitHub is the truth for existence). For a job owned by `me` the orchestrator
    is authoritative for `stage`, unless the derived stage is merged/closed/needs-human.
    """
    old_jobs = {j.get("id"): j for j in (old_board or {}).get("jobs") or [] if isinstance(j, dict)}
    for job in new_board.get("jobs", []):
        old = old_jobs.get(job.get("id"))
        if not old:
            continue
        for key in LOCAL_FIELDS:
            if key in old:
                job[key] = old[key]
        if not job.get("round") and old.get("round"):
            job["round"] = old["round"]
        if (me and job.get("owner") == me and old.get("stage")
                and job.get("stage") not in TERMINAL_STAGES):
            job["stage"] = old["stage"]
    return new_board


def _load_board(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_board(board: dict, out: str, me: Optional[str] = None) -> None:
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "board.json")
    board = merge_local_state(board, _load_board(path), me)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(board, f, indent=2)
        f.write("\n")


def _cmd_claim(args, run):
    me = _resolve_me(args, run, optional=False)
    issue = json.loads(run([
        "gh", "issue", "view", str(args.issue), "--repo", args.repo,
        "--json", "number,url,assignees,labels"]))
    if args.claim_action == "check":
        c = claim_state(issue, me)
        if c.state == "other":
            sys.stdout.write("other %s %s\n" % (c.holder or "none", c.url))
        else:
            sys.stdout.write(c.state + "\n")
    else:
        events = _assigned_events(args.repo, args.issue, run)
        won = decide_claim_winner_by_events(issue, events, me)
        sys.stdout.write("won\n" if won else "lost\n")


ASSIGNED_EVENTS_JQ = '[.[] | select(.event=="assigned") | {login: .assignee.login, at: .created_at}]'


def _json_values(text: str) -> list:
    """Every JSON value in `text` (`gh --paginate --jq` prints one array per page)."""
    decoder = json.JSONDecoder()
    values, i, text = [], 0, text or ""
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return values
        value, i = decoder.raw_decode(text, i)
        values.append(value)


def _assigned_events(repo: str, number: int, run: Callable) -> list:
    """[{login, at}] of the issue's `assigned` events; [] when unavailable."""
    try:
        out = run(["gh", "api", "repos/%s/issues/%d/events" % (repo, number),
                   "--paginate", "--jq", ASSIGNED_EVENTS_JQ])
        pages = _json_values(out)
    except (subprocess.CalledProcessError, ValueError):
        return []
    events = []
    for page in pages:
        if isinstance(page, list):
            events.extend(page)
    return events


def _cmd_status(args, run):
    me = _resolve_me(args, run, optional=False)
    sys.stdout.write(render_status(_board_for(args, run, me), args.repo))


def _cmd_board(args, run):
    me = _resolve_me(args, run, optional=True)
    _write_board(_board_for(args, run, me), args.out, me)


def _cmd_dashboard(args, run):
    me = _resolve_me(args, run, optional=True)
    _write_board(_board_for(args, run, me), args.out, me)
    template = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "dashboard.html")
    shutil.copyfile(template, os.path.join(args.out, "dashboard.html"))


def detect_dashboard_mode(plan_name: Optional[str], private: bool) -> str:
    """"pages" (Enterprise only), "projects" (free/pro/team) or "ask" (unknown plan).

    `private` is accepted for the interface but never promotes "ask" to "pages":
    Pages access control for private repos is an Enterprise feature, and an unknown
    plan must be confirmed with the user.
    """
    plan = (plan_name or "").strip().lower()
    if plan == "enterprise":
        return "pages"
    if plan in ("free", "pro", "team"):
        return "projects"
    return "ask"


def _cmd_mode(args, run):
    info = run(["gh", "api", "repos/" + args.repo, "--jq", ".owner.type,.private"]).split()
    owner_type = info[0] if info else ""
    private = len(info) > 1 and info[1] == "true"
    owner = args.repo.split("/", 1)[0]
    endpoint = "orgs/" + owner if owner_type == "Organization" else "user"
    try:
        plan = run(["gh", "api", endpoint, "--jq", ".plan.name"]).strip()
        plan_name = plan if plan and plan != "null" else None
    except subprocess.CalledProcessError:
        plan_name = None
    sys.stdout.write(detect_dashboard_mode(plan_name, private) + "\n")


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
        p.add_argument("--me", help="GitHub login (default: gh api user%s)" % (
            "" if name == "status" else "; empty if that is refused"))
        if name != "status":
            p.add_argument("--out", default="factory", help="output directory (default: factory)")
        p.set_defaults(handler=handler)
    p = sub.add_parser("claim", help="check or verify the claim on an issue")
    p.add_argument("claim_action", choices=("check", "verify"))
    p.add_argument("--repo", required=True, help="OWNER/NAME")
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--me", help="GitHub login (default: gh api user)")
    p.set_defaults(handler=_cmd_claim)
    p = sub.add_parser("mode", help="print the dashboard mode: pages|projects|ask")
    p.add_argument("--repo", required=True, help="OWNER/NAME")
    p.set_defaults(handler=_cmd_mode)
    return parser


class GhNotFound(Exception):
    """The `gh` executable itself could not be started."""


def _guard_gh(run: Callable) -> Callable:
    """Wrap a runner so only a failure to launch `gh` reads as "gh not found"."""
    def guarded(args):
        try:
            return run(args)
        except FileNotFoundError as e:
            raise GhNotFound() from e
    return guarded


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    run = _guard_gh(RUN or default_run)
    try:
        args.handler(args, run)
    except GhNotFound:
        sys.stderr.write("error: the gh CLI was not found; install it and run `gh auth login`\n")
        return 1
    except json.JSONDecodeError as e:
        sys.stderr.write("error: gh returned invalid JSON (%s)\n" % e.msg)
        return 1
    except OSError as e:
        sys.stderr.write("error: %s: %s\n" % (e.strerror or e, e.filename or ""))
        return 1
    except subprocess.CalledProcessError as e:
        detail = ((e.stderr or "").strip().splitlines() or ["gh failed (run `gh auth login`?)"])[0]
        sys.stderr.write("error: gh failed: %s\n" % detail)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
