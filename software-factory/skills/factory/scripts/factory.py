#!/usr/bin/env python3
"""Deterministic state for the software factory.

The orchestrator (an LLM session) decides *what* to do; this script owns *whether it is
allowed* and writes the result. It is the only writer of factory/board.json, and every
change is appended to factory/events.jsonl (audit trail + metrics source).

Stdlib only; runs on Python 3.9+.

Exit codes: 0 ok · 1 bad input/state · 2 illegal transition · 3 review rounds exhausted
            4 unreadable verdict · 5 lock stale · 6 lock held · 10 diff-match found files
            11 conflicts: builder resolves · 12 conflicts: needs a human
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

REVIEWERS = ("security", "ux", "code", "adversary")
STAGES = ("blocked", "spec", "build", "review", "ux-queue", "ux-test", "approve",
          "pr-open", "merged", "needs-human", "closed")
ACTIVE = ("spec", "build", "review", "ux-queue", "ux-test", "approve")
TERMINAL = ("merged", "closed")

# stage -> stages reachable with `transition`. `review` is entered only by `round-start`,
# `build` from needs-human only by `rework`; merged/closed from anywhere need --external.
TRANSITIONS = {
    "blocked": ("spec", "needs-human"),
    "spec": ("build", "needs-human"),
    "build": ("spec", "needs-human"),
    "review": ("build", "ux-queue", "approve", "needs-human"),
    "ux-queue": ("ux-test", "build", "needs-human"),
    "ux-test": ("build", "approve", "needs-human"),
    "approve": ("pr-open", "build", "needs-human"),
    "pr-open": ("merged", "build", "needs-human"),
    "needs-human": ("pr-open",),
    "merged": (),
    "closed": (),
}

ROUND_ENUMS = {
    "uxTest": ("queued", "running", "PASS", "CHANGES", "SKIPPED", "BLOCKED"),
    "ci": ("PASS", "FAILED", "none", "flaky"),
    "tests": ("PASS", "FAILED"),
    "mode": ("full", "delta"),
}
ROUND_FREE = ("ciReason", "ciRerun", "sha", "prevSha")
JOB_INT = ("pr", "issue", "epic", "conflicts")
JOB_BOOL = ("uiImpact",)
JOB_STR = ("base", "uxQueuedAt", "note", "title", "sha", "epicBase", "plan", "ticket")
JOB_LIST = ("risk", "blockedBy")

ID_RE = re.compile(r"^\d+-[a-z0-9]+(?:-[a-z0-9]+)*$")
VERDICT_RE = {
    "review": re.compile(r"^VERDICT:\s*(PASS|CHANGES)\s*$"),
    "ux": re.compile(r"^VERDICT:\s*(PASS|CHANGES|BLOCKED|SKIPPED)\s*$"),
    "decision": re.compile(r"^(APPROVE|ESCALATE)\b"),
}

LOCK_STALE_MIN = {"run": 120, "ux": 45}


class Fail(Exception):
    def __init__(self, code, msg):
        Exception.__init__(self, msg)
        self.code = code


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------- storage

def board_path(d):
    return os.path.join(d, "board.json")


def load(d):
    p = board_path(d)
    if not os.path.exists(p):
        raise Fail(1, "no %s — run /factory setup" % p)
    with open(p, encoding="utf-8") as f:
        try:
            board = json.load(f)
        except ValueError as e:
            raise Fail(1, "board.json is not valid JSON: %s" % e)
    if not isinstance(board, dict) or not isinstance(board.get("jobs"), list):
        raise Fail(1, 'board.json must be {"jobs": [...]}')
    return board


def save(d, board):
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".board.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(board, f, indent=2)
        f.write("\n")
    os.replace(tmp, board_path(d))
    owner = os.path.join(d, "run.lock", "owner")
    if os.path.exists(owner):  # heartbeat: an active run keeps its lock fresh
        os.utime(owner, None)


def event(d, kind, job=None, **data):
    rec = {"ts": now(), "event": kind}
    if job:
        rec["job"] = job
    rec.update(data)
    with open(os.path.join(d, "events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def find(board, job_id):
    for j in board["jobs"]:
        if j.get("id") == job_id:
            return j
    raise Fail(1, "no job %r on the board" % job_id)


def cur_round(job):
    rounds = job.get("rounds") or []
    if not rounds:
        raise Fail(1, "job %s has no review round yet" % job["id"])
    return rounds[-1]


def touch(job):
    job["updated"] = now()


def rounds_left(job, max_rounds):
    return max_rounds - (job.get("round", 0) - job.get("roundBase", 0))


# ---------------------------------------------------------------- guards

def all_pass(rnd):
    return all(rnd.get("reviews", {}).get(r) == "PASS" for r in REVIEWERS)


def guard(job, dst):
    """Preconditions a legal edge still has to meet. Returns an error string or None."""
    src = job["stage"]
    if src == "review" and dst in ("ux-queue", "approve"):
        rnd = cur_round(job)
        if rnd.get("tests") != "PASS":
            return "round %s tests are not PASS" % rnd["n"]
        if not all_pass(rnd):
            return "round %s does not have four PASS reviews" % rnd["n"]
        if dst == "approve" and rnd.get("uxTest") != "SKIPPED":
            return "review → approve needs uxTest SKIPPED (UI jobs go through ux-queue)"
    if src == "ux-test" and dst == "approve" and cur_round(job).get("uxTest") != "PASS":
        return "ux-test → approve needs uxTest PASS"
    if dst == "pr-open":
        if job.get("decision") != "APPROVE" or not job.get("approvedSha"):
            return "pr-open needs decision APPROVE with an approved sha (use `decision`)"
        if src == "needs-human" and not job.get("humanApproved"):
            return "needs-human → pr-open needs `decision <id> APPROVE --human`"
    return None  # → merged is recorded after the fact; `merge-check` is the gate before it


def merge_blocker(job, head, board):
    if job["stage"] != "pr-open":
        return "stage is %s, not pr-open" % job["stage"]
    if job.get("decision") != "APPROVE":
        return "decision is not APPROVE"
    if not head or job.get("approvedSha") != head:
        return "PR head %s is not the approved sha %s — new commits need review" % (
            head, job.get("approvedSha"))
    if job.get("base", "main") != "main":
        return "base is %s, not main (restack first)" % job.get("base")
    if job.get("risk") and not job.get("humanApproved"):
        return "risk paths touched (%s) — needs a human approve" % ", ".join(job["risk"])
    if job.get("noCi") and not job.get("humanApproved"):
        return "no CI on this PR and profile no_ci is not `allow` — needs a human approve"
    if board is not None and board.get("halt"):
        return "factory halted: %s" % board["halt"]
    return None


# ---------------------------------------------------------------- commands

def cmd_add(a, d):
    board = load(d)
    if not ID_RE.match(a.id):
        raise Fail(1, "id must be <issue>-<slug> (e.g. 42-rate-limiting), got %r" % a.id)
    if any(j.get("id") == a.id for j in board["jobs"]):
        raise Fail(1, "job %s already exists" % a.id)
    if a.issue is not None and not a.id.startswith("%d-" % a.issue):
        raise Fail(1, "id %s must start with its issue number %d" % (a.id, a.issue))
    job = {
        "id": a.id, "title": a.title, "plan": a.plan or "", "ticket": a.ticket or "",
        "issue": a.issue, "epic": a.epic, "epicBase": a.epic_base or "", "pr": None,
        "blockedBy": split_list(a.blocked_by), "branch": "factory/" + a.id, "base": "main",
        "stage": "blocked", "round": 0, "roundBase": 0, "reviews": {}, "rounds": [],
        "uiImpact": None, "uxQueuedAt": "", "risk": [], "sha": "", "approvedSha": "",
        "decision": None, "humanApproved": False, "noCi": False, "note": "",
        "updated": now(),
    }
    board["jobs"].append(job)
    save(d, board)
    event(d, "add", a.id, issue=a.issue, blockedBy=job["blockedBy"])
    print("added %s" % a.id)


def split_list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip() and x.strip() != "none"]


def cmd_transition(a, d):
    board = load(d)
    job = find(board, a.id)
    src, dst = job["stage"], a.stage
    if dst not in STAGES:
        raise Fail(1, "unknown stage %r (one of: %s)" % (dst, ", ".join(STAGES)))
    if a.external:
        if dst not in TERMINAL or src in TERMINAL:
            raise Fail(2, "--external is only for a non-terminal job a human merged/closed")
    elif dst not in TRANSITIONS[src]:
        hint = ""
        if dst == "review":
            hint = " (use `round-start`)"
        elif src == "needs-human" and dst == "build":
            hint = " (use `rework`)"
        raise Fail(2, "illegal transition %s → %s for %s%s; legal: %s" % (
            src, dst, a.id, hint, ", ".join(TRANSITIONS[src]) or "none (terminal)"))
    else:
        if dst == "needs-human" and not a.note:
            raise Fail(1, "needs-human requires --note <reason>")
        err = guard(job, dst)
        if err:
            raise Fail(2, "%s → %s refused for %s: %s" % (src, dst, a.id, err))
    if dst == "build" and src in ("approve", "pr-open"):
        job["decision"], job["approvedSha"], job["humanApproved"] = None, "", False
    if dst == "ux-queue":
        job["uxQueuedAt"] = now()
    job["stage"] = dst
    if a.note is not None:
        job["note"] = a.note
    elif dst != "needs-human":
        job["note"] = ""
    touch(job)
    save(d, board)
    event(d, "transition", a.id, src=src, dst=dst, note=a.note or "",
          external=bool(a.external), round=job.get("round", 0))
    print("%s: %s → %s" % (a.id, src, dst))


def cmd_round_start(a, d):
    board = load(d)
    job = find(board, a.id)
    if job["stage"] not in ("build", "approve", "pr-open"):
        raise Fail(2, "round-start needs stage build (or approve/pr-open when the PR head "
                      "moved), not %s" % job["stage"])
    if not a.sha:
        raise Fail(1, "--sha <PR head sha> is required: reviews are pinned to a commit")
    left = rounds_left(job, a.max_rounds)
    if left <= 0:
        raise Fail(3, "%s used all %d review rounds — flag it (needs-human)" % (
            a.id, a.max_rounds))
    n = job.get("round", 0) + 1
    prev = job.get("sha") or ""
    mode = a.mode or ("delta" if n - job.get("roundBase", 0) > 1 and prev else "full")
    if mode == "delta" and not prev:
        raise Fail(1, "delta mode needs a previous round sha")
    rnd = {"n": n, "sha": a.sha, "prevSha": prev, "mode": mode,
           "reviews": dict((r, "pending") for r in REVIEWERS)}
    job.setdefault("rounds", []).append(rnd)
    job["round"], job["reviews"], job["sha"] = n, dict(rnd["reviews"]), a.sha
    job["decision"], job["approvedSha"], job["humanApproved"] = None, "", False
    job["stage"] = "review"
    touch(job)
    save(d, board)
    event(d, "round-start", a.id, round=n, sha=a.sha, mode=mode)
    print("%s: round %d (%s) at %s, %d left after this" % (a.id, n, mode, a.sha[:10], left - 1))


def read_verdict(path, kind):
    try:
        with open(path, encoding="utf-8") as f:
            first = f.readline().strip()
    except (IOError, OSError):
        raise Fail(4, "INVALID: %s is missing" % path)
    m = VERDICT_RE[kind].match(first)
    if not m:
        raise Fail(4, "INVALID: first line of %s is %r" % (path, first[:80]))
    return m.group(1)


def cmd_verdict(a, d):
    print(read_verdict(a.file, a.kind))


def cmd_review(a, d):
    board = load(d)
    job = find(board, a.id)
    if job["stage"] != "review":
        raise Fail(2, "%s is in %s, not review" % (a.id, job["stage"]))
    if a.reviewer not in REVIEWERS:
        raise Fail(1, "reviewer must be one of %s" % ", ".join(REVIEWERS))
    if bool(a.file) == bool(a.verdict):
        raise Fail(1, "give exactly one of --file or --verdict")
    v = a.verdict or read_verdict(a.file, "review")
    if v not in ("PASS", "CHANGES"):
        raise Fail(1, "verdict must be PASS or CHANGES")
    rnd = cur_round(job)
    rnd["reviews"][a.reviewer] = v
    job["reviews"] = dict(rnd["reviews"])
    touch(job)
    save(d, board)
    event(d, "review", a.id, round=rnd["n"], reviewer=a.reviewer, verdict=v)
    pending = [r for r in REVIEWERS if rnd["reviews"][r] == "pending"]
    print("%s R%d %s=%s%s" % (a.id, rnd["n"], a.reviewer, v,
                              " · waiting on " + ",".join(pending) if pending else " · round complete"))


def parse_kv(pairs):
    out = []
    for p in pairs:
        if "=" not in p:
            raise Fail(1, "expected key=value, got %r" % p)
        k, v = p.split("=", 1)
        out.append((k, v))
    return out


def cmd_round_set(a, d):
    board = load(d)
    job = find(board, a.id)
    rnd = cur_round(job)
    for k, v in parse_kv(a.pairs):
        if k in ROUND_ENUMS:
            if v not in ROUND_ENUMS[k]:
                raise Fail(1, "%s must be one of %s" % (k, ", ".join(ROUND_ENUMS[k])))
        elif k not in ROUND_FREE:
            raise Fail(1, "unknown round field %r" % k)
        rnd[k] = v
        if k == "ci" and v == "none":
            job["noCi"] = True
        elif k == "ci":
            job["noCi"] = False
    touch(job)
    save(d, board)
    event(d, "round-set", a.id, round=rnd["n"], **dict(parse_kv(a.pairs)))
    print("%s R%d: %s" % (a.id, rnd["n"], " ".join(a.pairs)))


def cmd_set(a, d):
    board = load(d)
    job = find(board, a.id)
    for k, v in parse_kv(a.pairs):
        if k in JOB_INT:
            try:
                job[k] = int(v)
            except ValueError:
                raise Fail(1, "%s must be a number" % k)
        elif k in JOB_BOOL:
            if v not in ("true", "false"):
                raise Fail(1, "%s must be true or false" % k)
            job[k] = v == "true"
        elif k in JOB_LIST:
            job[k] = split_list(v)
        elif k in JOB_STR:
            job[k] = v
        else:
            raise Fail(1, "field %r is not settable (stage/round/reviews/decision have "
                          "their own commands)" % k)
    touch(job)
    save(d, board)
    event(d, "set", a.id, **dict(parse_kv(a.pairs)))
    print("%s: %s" % (a.id, " ".join(a.pairs)))


def cmd_decision(a, d):
    board = load(d)
    job = find(board, a.id)
    if a.decision == "APPROVE":
        if not a.sha:
            raise Fail(1, "APPROVE needs --sha <PR head sha that was approved>")
        if a.human:
            if job["stage"] not in ("needs-human", "approve", "pr-open"):
                raise Fail(2, "human approve needs stage needs-human/approve/pr-open")
            job["humanApproved"] = True
        else:
            if job["stage"] != "approve":
                raise Fail(2, "%s is in %s, not approve" % (a.id, job["stage"]))
            rnd = cur_round(job)
            if not all_pass(rnd) or rnd.get("uxTest") not in ("PASS", "SKIPPED"):
                raise Fail(2, "round %s is not review-clean" % rnd["n"])
            if rnd.get("sha") != a.sha:
                raise Fail(2, "approved sha %s is not the reviewed sha %s — commits landed "
                              "after review; start a new round" % (a.sha, rnd.get("sha")))
        job["decision"], job["approvedSha"] = "APPROVE", a.sha
    else:
        job["decision"], job["approvedSha"] = "ESCALATE", ""
    touch(job)
    save(d, board)
    event(d, "decision", a.id, decision=a.decision, sha=a.sha or "", human=bool(a.human))
    print("%s: %s%s" % (a.id, a.decision, " (human)" if a.human else ""))


def cmd_rework(a, d):
    board = load(d)
    job = find(board, a.id)
    if job["stage"] in TERMINAL or job["stage"] == "blocked":
        raise Fail(2, "cannot rework a %s job" % job["stage"])
    src = job["stage"]
    job["roundBase"] = job.get("round", 0)
    job["decision"], job["approvedSha"], job["humanApproved"] = None, "", False
    job["stage"], job["note"] = "build", "human rework"
    touch(job)
    save(d, board)
    event(d, "rework", a.id, src=src, round=job.get("round", 0))
    print("%s: %s → build (human rework; round budget reset)" % (a.id, src))


def cmd_repin(a, d):
    """Restack with an unchanged patch-id: same content, new commit ids."""
    board = load(d)
    job = find(board, a.id)
    if job["stage"] != "pr-open" or job.get("decision") != "APPROVE":
        raise Fail(2, "repin is only for an approved pr-open job after a restack")
    old = job.get("approvedSha")
    job["approvedSha"] = job["sha"] = a.sha
    touch(job)
    save(d, board)
    event(d, "repin", a.id, old=old, sha=a.sha, reason=a.reason)
    print("%s: approval re-pinned %s → %s" % (a.id, (old or "")[:10], a.sha[:10]))


def cmd_merge_check(a, d):
    board = load(d)
    job = find(board, a.id)
    err = merge_blocker(job, a.head, board)
    if err:
        raise Fail(2, "do not merge %s: %s" % (a.id, err))
    if not job.get("pr"):
        raise Fail(1, "%s has no PR number on the board" % a.id)
    print("gh pr merge %d --squash --delete-branch --match-head-commit %s" % (job["pr"], a.head))


def readiness(board, max_parallel):
    by_id = dict((j["id"], j) for j in board["jobs"])
    slots = max_parallel - sum(1 for j in board["jobs"] if j["stage"] in ACTIVE)
    out = []
    blocked = sorted((j for j in board["jobs"] if j["stage"] == "blocked"),
                     key=lambda j: (j.get("issue") or 0, j["id"]))
    for j in blocked:
        action, base, reason = "start", "main", ""
        open_blockers = []
        for b in j.get("blockedBy") or []:
            bj = by_id.get(b)
            if bj is None:
                action, reason = "wait", "unknown blocker %s" % b
                break
            if bj["stage"] == "merged":
                continue
            if bj["stage"] == "pr-open":
                open_blockers.append(bj)
                continue
            action, reason = "wait", "blocker %s is %s" % (b, bj["stage"])
            break
        if action != "wait":
            if len(open_blockers) > 1:
                action, reason = "wait", "more than one unmerged blocker"
            elif open_blockers:
                action, base = "stack", open_blockers[0]["branch"]
                reason = "blocker %s approved, not merged" % open_blockers[0]["id"]
        if action != "wait":
            if board.get("halt"):
                action, reason = "wait", "halted: %s" % board["halt"]
            elif slots <= 0:
                action, reason = "wait", "max_parallel reached"
            else:
                slots -= 1
        out.append({"id": j["id"], "action": action,
                    "base": base if action != "wait" else "", "reason": reason})
    return out


def cmd_ready(a, d):
    for r in readiness(load(d), a.max_parallel):
        print(json.dumps(r, sort_keys=True))


def cmd_dependents(a, d):
    board = load(d)
    job = find(board, a.id)
    for j in board["jobs"]:
        if j.get("base") == job["branch"] and j["stage"] not in TERMINAL + ("blocked",):
            print("%s\t%s" % (j["id"], j["stage"]))


def cmd_halt(a, d):
    board = load(d)
    if a.action == "set":
        if not a.reason:
            raise Fail(1, "halt set needs a reason")
        board["halt"] = a.reason
    elif a.action == "clear":
        board["halt"] = ""
    else:
        print(board.get("halt") or "not halted")
        return
    save(d, board)
    event(d, "halt", reason=board["halt"])
    print("halted: %s" % board["halt"] if board["halt"] else "halt cleared")


def cmd_repo(a, d):
    """Record the GitHub "owner/name"; the dashboard builds issue and PR links from it."""
    board = load(d)
    if a.name is None:
        print(board.get("repo") or "no repo set")
        return
    if not re.match(r"^[\w.-]+/[\w.-]+$", a.name):
        raise Fail(1, "repo must be owner/name, got %r" % a.name)
    board["repo"] = a.name
    save(d, board)
    print("repo: %s" % a.name)


def cmd_stuck(a, d):
    board = load(d)
    cutoff = time.time() - a.minutes * 60
    for j in board["jobs"]:
        if j["stage"] not in ACTIVE:
            continue
        try:
            ts = parse_ts(j.get("updated", "")).timestamp()
        except ValueError:
            ts = 0
        if ts < cutoff:
            print("%s\t%s\t%d min" % (j["id"], j["stage"], (time.time() - ts) // 60 if ts else -1))


def cmd_show(a, d):
    board = load(d)
    if a.id:
        job = dict(find(board, a.id))
        job["roundsLeft"] = rounds_left(job, a.max_rounds)
        print(json.dumps(job, indent=2))
        return
    if board.get("halt"):
        print("HALTED: %s" % board["halt"])
    for j in board["jobs"]:
        print("\t".join([j["id"], "#%s" % j.get("issue"), "PR #%s" % j["pr"] if j.get("pr") else "-",
                         j["stage"], "R%d" % j.get("round", 0), j.get("note") or ""]))


def cmd_epic(a, d):
    board = load(d)
    jobs = [j for j in board["jobs"] if j.get("epic") == a.epic]
    if not jobs:
        raise Fail(1, "no jobs for epic #%d" % a.epic)
    open_jobs = [j["id"] for j in jobs if j["stage"] != "merged"]
    print(json.dumps({"epic": a.epic, "total": len(jobs), "merged": len(jobs) - len(open_jobs),
                      "open": open_jobs, "done": not open_jobs,
                      "base": next((j.get("epicBase") for j in jobs if j.get("epicBase")), "")},
                     sort_keys=True))


def cmd_validate(a, d):
    board = load(d)
    problems, seen = [], set()
    for j in board["jobs"]:
        jid = j.get("id", "?")
        if jid in seen:
            problems.append("%s: duplicate id" % jid)
        seen.add(jid)
        if not ID_RE.match(str(jid)):
            problems.append("%s: id is not <issue>-<slug>" % jid)
        if j.get("stage") not in STAGES:
            problems.append("%s: unknown stage %r" % (jid, j.get("stage")))
        if j.get("round", 0) != len(j.get("rounds") or []):
            problems.append("%s: round %s but %d round records" % (
                jid, j.get("round"), len(j.get("rounds") or [])))
        if j.get("stage") == "pr-open" and not j.get("approvedSha"):
            problems.append("%s: pr-open without an approved sha" % jid)
    ids = seen
    for j in board["jobs"]:
        for b in j.get("blockedBy") or []:
            if b not in ids:
                problems.append("%s: blockedBy unknown job %s" % (j.get("id"), b))
    for p in problems:
        print(p)
    if problems:
        raise Fail(1, "%d problem(s)" % len(problems))
    print("board ok: %d job(s)" % len(board["jobs"]))


# ---------------------------------------------------------------- locks

def cmd_lock(a, d):
    path = os.path.join(d, a.name + ".lock")
    owner_file = os.path.join(path, "owner")
    if a.action == "release":
        if os.path.isdir(path):
            held = read_owner(owner_file)[0]
            if a.owner and held and held != a.owner and not a.force:
                raise Fail(6, "%s lock is held by %r, not %r (use --force)" % (a.name, held, a.owner))
            shutil.rmtree(path)
            event(d, "lock-release", lock=a.name, owner=held)
        print("%s lock released" % a.name)
        return
    if a.action == "status":
        if not os.path.isdir(path):
            print("free")
            return
        held, age = read_owner(owner_file)
        print("held by %s, last activity %d min ago" % (held or "?", age))
        return
    if not a.owner:
        raise Fail(1, "acquire needs --owner <text>")
    stale = a.stale_min if a.stale_min is not None else LOCK_STALE_MIN[a.name]
    try:
        os.mkdir(path)
    except OSError:
        held, age = read_owner(owner_file)
        if held == a.owner:
            os.utime(owner_file, None)
            print("%s lock already yours" % a.name)
            return
        if age >= stale:
            raise Fail(5, "STALE: %s lock held by %r, no activity for %d min" % (a.name, held, age))
        raise Fail(6, "HELD: %s lock held by %r, last activity %d min ago" % (a.name, held, age))
    with open(owner_file, "w", encoding="utf-8") as f:
        f.write(a.owner + "\n")
    event(d, "lock-acquire", lock=a.name, owner=a.owner)
    print("%s lock acquired" % a.name)


def read_owner(owner_file):
    try:
        with open(owner_file, encoding="utf-8") as f:
            held = f.readline().strip()
        age = int((time.time() - os.path.getmtime(owner_file)) // 60)
    except (IOError, OSError):
        return "", 10 ** 6  # lock dir with no owner file: a crashed acquire
    return held, age


# ---------------------------------------------------------------- git / profile

def profile_value(profile, key):
    with open(profile, encoding="utf-8") as f:
        for line in f:
            if line.startswith(key + ":"):
                return line.split(":", 1)[1].split("#", 1)[0].strip()
    return ""


def matching_changes(repo, base, head, globs):
    """Files changed in base...head that match any of the git pathspec globs."""
    if not globs:
        return []
    cmd = ["git", "-C", repo, "diff", "--name-only", "%s...%s" % (base, head), "--"]
    cmd += [":(glob)" + g for g in globs]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if p.returncode != 0:
        raise Fail(1, "git diff failed: %s" % p.stderr.strip())
    return [f for f in p.stdout.splitlines() if f]


def cmd_diff_match(a, d):
    globs = []
    for key in a.key:
        globs += split_list(profile_value(a.profile, key))
    files = matching_changes(a.repo, a.base, a.head, globs)
    for f in files:
        print(f)
    if files:
        raise Fail(10, "")


def conflicted_files(repo, base, head):
    """Files a merge of head into base would conflict on ([] = merges cleanly). git >= 2.38."""
    p = subprocess.run(["git", "-C", repo, "merge-tree", "--write-tree", "--name-only",
                        "--no-messages", base, head],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if p.returncode == 0:
        return []
    if p.returncode != 1:
        raise Fail(1, "git merge-tree failed: %s" % p.stderr.strip())
    files = []
    for line in p.stdout.splitlines()[1:]:  # line 1 is the tree id
        if not line:
            break
        if line not in files:
            files.append(line)
    return files


def cmd_conflicts(a, d):
    """Would factory/<id> conflict with its base? Counts conflicts, decides builder vs human."""
    board = load(d)
    job = find(board, a.id)
    files = conflicted_files(a.repo, a.base, a.head)
    if not files:
        print("clean")
        return
    job["conflicts"] = job.get("conflicts", 0) + 1
    risky = []
    if os.path.exists(a.profile):
        risky = sorted(set(files) & set(matching_changes(
            a.repo, a.base, a.head, split_list(profile_value(a.profile, "risk_globs")))))
    touch(job)
    save(d, board)
    event(d, "conflict", a.id, n=job["conflicts"], files=files, risky=risky)
    for f in files:
        print(f)
    if risky:
        raise Fail(12, "conflict in risk paths: %s" % ", ".join(risky))
    if job["conflicts"] > a.max:
        raise Fail(12, "conflict #%d (max %d): main keeps moving under %s"
                   % (job["conflicts"], a.max, ", ".join(files)))
    raise Fail(11, "")


# ---------------------------------------------------------------- metrics

def cmd_metrics(a, d):
    path = os.path.join(d, "events.jsonl")
    jobs = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                jid = e.get("job")
                if not jid:
                    continue
                m = jobs.setdefault(jid, {"id": jid, "started": "", "merged": "", "rounds": 0,
                                          "escalations": 0, "ciFailed": 0, "flaky": 0,
                                          "uxChanges": 0, "reasons": []})
                if e["event"] == "transition":
                    if e.get("src") == "blocked" and not m["started"]:
                        m["started"] = e["ts"]
                    if e.get("dst") == "merged":
                        m["merged"] = e["ts"]
                    if e.get("dst") == "needs-human":
                        m["escalations"] += 1
                        m["reasons"].append(e.get("note", ""))
                elif e["event"] == "round-start":
                    m["rounds"] = max(m["rounds"], e.get("round", 0))
                elif e["event"] == "round-set":
                    if e.get("ci") == "FAILED":
                        m["ciFailed"] += 1
                    if e.get("ci") == "flaky":
                        m["flaky"] += 1
                    if e.get("uxTest") == "CHANGES":
                        m["uxChanges"] += 1
    rows = sorted(jobs.values(), key=lambda m: m["started"] or "~")
    for m in rows:
        m["cycleMin"] = None
        if m["started"] and m["merged"]:
            m["cycleMin"] = int((parse_ts(m["merged"]) - parse_ts(m["started"])).total_seconds() // 60)
    merged = [m for m in rows if m["merged"]]
    started = [m for m in rows if m["started"]]
    summary = {
        "generated": now(), "started": len(started), "merged": len(merged),
        "avgRounds": round(sum(m["rounds"] for m in merged) / float(len(merged)), 2) if merged else None,
        "avgCycleMin": int(sum(m["cycleMin"] for m in merged) / len(merged)) if merged else None,
        "firstPassRate": round(sum(1 for m in merged if m["rounds"] <= 1 and not m["escalations"])
                               / float(len(merged)), 2) if merged else None,
        "escalationRate": round(sum(1 for m in started if m["escalations"]) / float(len(started)), 2)
        if started else None,
        "ciFailures": sum(m["ciFailed"] for m in rows), "flaky": sum(m["flaky"] for m in rows),
    }
    with open(os.path.join(d, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "jobs": rows}, f, indent=2)
        f.write("\n")
    print(json.dumps(summary, sort_keys=True))
    for m in rows:
        print("\t".join([m["id"], "rounds %d" % m["rounds"],
                         "cycle %s min" % m["cycleMin"] if m["cycleMin"] is not None else "open",
                         "escalations %d" % m["escalations"], "ci-fail %d" % m["ciFailed"],
                         "flaky %d" % m["flaky"]]))


# ---------------------------------------------------------------- cli

def build_parser():
    p = argparse.ArgumentParser(prog="factory.py", description=__doc__.split("\n")[0])
    p.add_argument("--dir", default="factory", help="factory state folder (default: ./factory)")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    s = sub.add_parser("add", help="add a job (stage blocked)")
    s.add_argument("--id", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--issue", type=int)
    s.add_argument("--epic", type=int)
    s.add_argument("--epic-base")
    s.add_argument("--plan")
    s.add_argument("--ticket")
    s.add_argument("--blocked-by", default="")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("transition", help="move a job to a stage (validated)")
    s.add_argument("id")
    s.add_argument("stage")
    s.add_argument("--note")
    s.add_argument("--external", action="store_true",
                   help="a human merged/closed the PR on GitHub")
    s.set_defaults(fn=cmd_transition)

    s = sub.add_parser("round-start", help="open review round N+1 at a commit (stage → review)")
    s.add_argument("id")
    s.add_argument("--sha", required=True)
    s.add_argument("--mode", choices=("full", "delta"))
    s.add_argument("--max-rounds", type=int, default=3)
    s.set_defaults(fn=cmd_round_start)

    s = sub.add_parser("review", help="record a reviewer verdict for the current round")
    s.add_argument("id")
    s.add_argument("reviewer")
    s.add_argument("--file")
    s.add_argument("--verdict")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("verdict", help="print the verdict on a file's first line")
    s.add_argument("file")
    s.add_argument("--kind", choices=sorted(VERDICT_RE), default="review")
    s.set_defaults(fn=cmd_verdict)

    s = sub.add_parser("round-set", help="set current-round fields: uxTest ci ciReason ciRerun tests")
    s.add_argument("id")
    s.add_argument("pairs", nargs="+")
    s.set_defaults(fn=cmd_round_set)

    s = sub.add_parser("set", help="set job fields: pr base uiImpact risk note …")
    s.add_argument("id")
    s.add_argument("pairs", nargs="+")
    s.set_defaults(fn=cmd_set)

    s = sub.add_parser("decision", help="record APPROVE (pinned to a sha) or ESCALATE")
    s.add_argument("id")
    s.add_argument("decision", choices=("APPROVE", "ESCALATE"))
    s.add_argument("--sha")
    s.add_argument("--human", action="store_true")
    s.set_defaults(fn=cmd_decision)

    s = sub.add_parser("rework", help="human rework: back to build, round budget reset")
    s.add_argument("id")
    s.set_defaults(fn=cmd_rework)

    s = sub.add_parser("repin", help="restack with unchanged patch-id: move the approval pin")
    s.add_argument("id")
    s.add_argument("--sha", required=True)
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_repin)

    s = sub.add_parser("merge-check", help="print the merge command, or refuse")
    s.add_argument("id")
    s.add_argument("--head", required=True, help="current PR head sha from GitHub")
    s.set_defaults(fn=cmd_merge_check)

    s = sub.add_parser("ready", help="what each blocked job may do now (start/stack/wait)")
    s.add_argument("--max-parallel", type=int, default=3)
    s.set_defaults(fn=cmd_ready)

    s = sub.add_parser("dependents", help="jobs stacked on this job's branch")
    s.add_argument("id")
    s.set_defaults(fn=cmd_dependents)

    s = sub.add_parser("halt", help="andon cord: stop promotions and merges")
    s.add_argument("action", choices=("set", "clear", "status"))
    s.add_argument("reason", nargs="?")
    s.set_defaults(fn=cmd_halt)

    s = sub.add_parser("repo", help="set/show the GitHub owner/name (dashboard links)")
    s.add_argument("name", nargs="?")
    s.set_defaults(fn=cmd_repo)

    s = sub.add_parser("stuck", help="active jobs with no state change for N minutes")
    s.add_argument("--minutes", type=int, default=60)
    s.set_defaults(fn=cmd_stuck)

    s = sub.add_parser("show", help="board summary, or one job as JSON (+roundsLeft)")
    s.add_argument("id", nargs="?")
    s.add_argument("--max-rounds", type=int, default=3)
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("epic", help="progress of an epic's tickets")
    s.add_argument("epic", type=int)
    s.set_defaults(fn=cmd_epic)

    s = sub.add_parser("validate", help="check board.json is consistent")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("lock", help="run / ux single-instance locks")
    s.add_argument("name", choices=sorted(LOCK_STALE_MIN))
    s.add_argument("action", choices=("acquire", "release", "status"))
    s.add_argument("--owner")
    s.add_argument("--stale-min", type=int)
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_lock)

    s = sub.add_parser("diff-match", help="files in base...head matching profile globs (exit 10 if any)")
    s.add_argument("--profile", default="factory/profile.md")
    s.add_argument("--key", action="append", required=True)
    s.add_argument("--base", required=True)
    s.add_argument("--head", required=True)
    s.add_argument("--repo", default=".")
    s.set_defaults(fn=cmd_diff_match)

    s = sub.add_parser("conflicts", help="conflict check vs base: exit 11 builder resolves, 12 flag")
    s.add_argument("id")
    s.add_argument("--base", required=True)
    s.add_argument("--head", required=True)
    s.add_argument("--profile", default="factory/profile.md")
    s.add_argument("--repo", default=".")
    s.add_argument("--max", type=int, default=2, help="conflict rounds before a human is asked")
    s.set_defaults(fn=cmd_conflicts)

    s = sub.add_parser("metrics", help="per-job and factory metrics from events.jsonl")
    s.set_defaults(fn=cmd_metrics)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        a.fn(a, a.dir)
    except Fail as e:
        if str(e):
            sys.stderr.write("factory: %s\n" % e)
        return e.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
