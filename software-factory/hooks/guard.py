#!/usr/bin/env python3
"""PreToolUse(Bash) guard: enforces the factory's hard rules instead of trusting prose.

In scope only for (a) this plugin's own agents (`agent_type` = software-factory:<name>) and
(b) any session in a project while a factory run holds `factory/run.lock`. Everything else
passes untouched, so the plugin never interferes with ordinary work.

Blocks (exit 2, reason on stderr):
  - git push to main/master, plain --force / -f, --mirror, --all
  - --no-verify on git commit / git push
  - gh pr merge from a factory agent (only the orchestrator merges)
  - gh pr merge by the orchestrator without --squash + --match-head-commit, or with --admin
  - merging or editing branch protection through `gh api`

This is a guardrail against mistakes, not a sandbox: shell can be obfuscated. Branch
protection on `main` is the real boundary. Fails open on its own errors.

Stdlib only; Python 3.9+.
"""
from __future__ import annotations

import json
import os
import re
import shlex
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


def is_protected_ref(tok):
    ref = tok.split(":")[-1]
    if ref.startswith("+"):
        ref = ref[1:]
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    return ref in PROTECTED


def check_segment(toks, is_agent):
    sub, args = git_sub(toks)
    if sub == "push":
        if any(t in ("--force", "-f", "--mirror", "--all") for t in args):
            return "git push --force/--mirror/--all is not allowed; use --force-with-lease on factory/<id>"
        if "--no-verify" in args:
            return "--no-verify is not allowed"
        positional = [t for t in args if not t.startswith("-")]
        if any(is_protected_ref(t) for t in positional[1:]):
            return "nothing is pushed to main directly — work reaches main only through a merged PR"
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


def check(command, is_agent):
    for seg in SPLIT_RE.split(command):
        reason = check_segment(tokens(seg), is_agent)
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
        reason = check(str((data.get("tool_input") or {}).get("command") or ""), is_agent)
    except Exception:  # noqa: BLE001 — a broken guard must not brick the session
        return 0
    if reason:
        sys.stderr.write("software-factory guard: %s\n" % reason)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
