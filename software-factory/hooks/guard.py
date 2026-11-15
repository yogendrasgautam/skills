#!/usr/bin/env python3
"""PreToolUse(Bash) guard: enforces the factory's hard rules instead of trusting prose.

In scope only for (a) this plugin's own agents (`agent_type` = software-factory:<name>) and
(b) any session in a project while a factory run holds `factory/run.lock`. Everything else
passes untouched, so the plugin never interferes with ordinary work.

Blocks (exit 2, reason on stderr):
  - git push to main/master — by name, as `HEAD`, or as a bare `git push` while on it
  - plain --force / -f / `+refspec`, --mirror, --all; any force push to a branch other than
    factory/*; a bare --force-with-lease without --force-if-includes (a background fetch
    would let it clobber commits it never saw)
  - --no-verify on git commit / git push
  - gh pr merge from a factory agent (only the orchestrator merges)
  - gh pr merge by the orchestrator without --squash + --match-head-commit, or with --admin
  - merging or editing branch protection through `gh api`
  - resolving a conflict by picking a side: checkout/restore --ours/--theirs, -X ours|theirs,
    -s ours, and `rebase --skip` (silently drops the commit being replayed)

This is a guardrail against mistakes, not a sandbox: shell can be obfuscated. Branch
protection on `main` is the real boundary. Fails open on its own errors.

Stdlib only; Python 3.9+.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

PLUGIN = "software-factory"
PROTECTED = ("main", "master")
SPLIT_RE = re.compile(r"&&|\|\||[;|\n]")


def tokens(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def git_sub(toks):
    """Return (subcommand, args after it) for a git invocation, else (None, [])."""
    if "git" not in toks:
        return None, []
    i = toks.index("git") + 1
    while i < len(toks):
        t = toks[i]
        if t in ("-C", "-c", "--git-dir", "--work-tree"):
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return t, toks[i + 1:]
    return None, []


def git_cwd(toks, cwd):
    """The directory a git invocation runs in: its -C (relative to cwd), else cwd."""
    if "git" not in toks:
        return cwd
    t = toks[toks.index("git") + 1:]
    for i, tok in enumerate(t[:-1]):
        if tok == "-C":
            return os.path.join(cwd or "", t[i + 1]) if cwd else t[i + 1]
    return cwd


def current_branch(cwd):
    """Branch checked out in cwd, or None when it can't be told (no repo, detached, error)."""
    if not cwd:
        return None
    try:
        p = subprocess.run(["git", "-C", cwd, "symbolic-ref", "--short", "-q", "HEAD"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=5)
    except Exception:  # noqa: BLE001
        return None
    return p.stdout.strip() or None


PUSH_VALUE_OPTS = ("-o", "--push-option", "--repo", "--receive-pack", "--exec")


def push_targets(args, cwd):
    """[(destination branch or None, forced by a +refspec)] for a git push's arguments."""
    positional, skip = [], False
    for t in args:
        if skip:
            skip = False
        elif t in PUSH_VALUE_OPTS:
            skip = True
        elif not t.startswith("-"):
            positional.append(t)
    refspecs = positional[1:]
    if not refspecs:
        return [(current_branch(cwd), False)]
    out = []
    for r in refspecs:
        plus = r.startswith("+")
        src, _, dst = r.lstrip("+").partition(":")
        dest = dst or src
        if dest == "HEAD":
            dest = current_branch(cwd)
        if dest and dest.startswith("refs/heads/"):
            dest = dest[len("refs/heads/"):]
        out.append((dest, plus))
    return out


def check_push(args, cwd):
    if any(t in ("--force", "-f", "--mirror", "--all") for t in args):
        return ("git push --force/--mirror/--all is not allowed; use "
                "--force-with-lease --force-if-includes on factory/<id>")
    if "--no-verify" in args:
        return "--no-verify is not allowed"
    leases = [t for t in args if t.startswith("--force-with-lease")]
    targets = push_targets(args, cwd)
    if any(dest in PROTECTED for dest, _ in targets):
        return "nothing is pushed to main directly — work reaches main only through a merged PR"
    if any(plus for _, plus in targets) and not leases:
        return "a +refspec is a plain force push; use --force-with-lease --force-if-includes"
    if leases or any(plus for _, plus in targets):
        for dest, _ in targets:
            if dest is None:
                return ("force push with no branch I can tell: name it, "
                        "`git push --force-with-lease --force-if-includes origin factory/<id>`")
            if not dest.startswith("factory/"):
                return "force pushes are only for factory/<id> branches, not %s" % dest
        explicit = all(":" in t.partition("=")[2] for t in leases)
        if not explicit and "--force-if-includes" not in args:
            return ("bare --force-with-lease can clobber commits a background fetch pulled in; "
                    "add --force-if-includes (or use --force-with-lease=<branch>:<expected sha>)")
    return None


SIDE_PICK = "resolve conflicts by intent (keep both changes), never by picking a side wholesale"


def picks_side(sub, args):
    if sub in ("checkout", "restore") and any(t in ("--ours", "--theirs") for t in args):
        return True
    if sub in ("merge", "rebase", "pull", "cherry-pick", "revert"):
        for i, t in enumerate(args):
            nxt = args[i + 1] if i + 1 < len(args) else ""
            if t in ("-X", "--strategy-option") and nxt in ("ours", "theirs"):
                return True
            if t in ("-Xours", "-Xtheirs", "--strategy-option=ours", "--strategy-option=theirs"):
                return True
            if t in ("-s", "--strategy") and nxt == "ours" or t in ("-sours", "--strategy=ours"):
                return True
    return False


def check_segment(toks, is_agent, cwd=None):
    sub, args = git_sub(toks)
    if picks_side(sub, args):
        return SIDE_PICK
    if sub == "rebase" and "--skip" in args:
        return "git rebase --skip drops a commit; resolve it, or --abort and report the conflict"
    if sub == "push":
        reason = check_push(args, git_cwd(toks, cwd))
        if reason:
            return reason
    if sub == "commit" and ("--no-verify" in args or "-n" in args):
        return "--no-verify is not allowed"
    if "gh" in toks:
        g = toks[toks.index("gh") + 1:]
        if g[:2] == ["pr", "merge"]:
            if is_agent:
                return "factory agents never merge; the orchestrator merges after APPROVE"
            if "--admin" in g:
                return "gh pr merge --admin bypasses branch protection — flag the PR instead"
            if "--squash" not in g or not any(t.startswith("--match-head-commit") for t in g):
                return ("merge only with the command printed by `factory.py merge-check` "
                        "(--squash --match-head-commit <approved sha>)")
        if g[:1] == ["api"]:
            joined = " ".join(g)
            if re.search(r"pulls/\d+/merge\b", joined):
                return "merging through the API bypasses the merge gate"
            if re.search(r"/protection\b|/rulesets\b", joined) and re.search(
                    r"(-X|--method)[ =]?(PUT|POST|PATCH|DELETE)", joined):
                return "the factory never changes branch protection"
    return None


def check(command, is_agent, cwd=None):
    for seg in SPLIT_RE.split(command):
        toks = tokens(seg)
        if toks[:1] == ["cd"] and len(toks) > 1:  # follow `cd x && git push`
            target = os.path.expanduser(toks[1])
            cwd = os.path.join(cwd, target) if cwd else target
            continue
        reason = check_segment(toks, is_agent, cwd)
        if reason:
            return reason
    return None


def in_scope(data):
    agent = str(data.get("agent_type") or "")
    is_agent = agent.startswith(PLUGIN + ":")
    roots = [os.environ.get("CLAUDE_PROJECT_DIR"), data.get("cwd")]
    run_active = any(r and os.path.isdir(os.path.join(r, "factory", "run.lock")) for r in roots)
    return is_agent, (is_agent or run_active)


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return 0
        is_agent, scoped = in_scope(data)
        if not scoped:
            return 0
        reason = check(str((data.get("tool_input") or {}).get("command") or ""), is_agent,
                       data.get("cwd"))
    except Exception:  # noqa: BLE001 — a broken guard must not brick the session
        return 0
    if reason:
        sys.stderr.write("software-factory guard: %s\n" % reason)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
