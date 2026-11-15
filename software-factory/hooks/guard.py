#!/usr/bin/env python3
"""PreToolUse(Bash) guard: enforces the factory's hard rules instead of trusting prose.

In scope only for (a) this plugin's own agents (`agent_type` = software-factory:<name>) and
(b) any session in a project while a factory run holds `factory/run.lock`. Everything else
passes untouched, so the plugin never interferes with ordinary work.

Blocks (exit 2, reason on stderr):
  - git push to main/master — by name (any spelling), or as `HEAD` / `@` while on it
  - a push that names no branch, or whose branch can't be told (it would go wherever git
    config or an unresolvable directory says)
  - plain --force / -f (also clustered, -uf) / `+refspec`, --mirror, --all; any force push to
    a branch other than factory/*; --force-with-lease without --force-if-includes or a
    <branch>:<full sha> pin (a background fetch would let it clobber commits it never saw)
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


def expand(path):
    """~ and $VAR expanded; None when something is left that only the shell could resolve."""
    path = os.path.expandvars(os.path.expanduser(path))
    return None if re.search(r"[$`~*?]", path) else path


def join(cwd, path):
    path = expand(path)
    if path is None:
        return None
    if os.path.isabs(path):
        return path
    return os.path.join(cwd, path) if cwd else None


def git_cwd(toks, cwd):
    """The directory a git invocation runs in: its -C (relative to cwd), else cwd."""
    if "git" not in toks:
        return cwd
    t = toks[toks.index("git") + 1:]
    for i, tok in enumerate(t[:-1]):
        if tok == "-C":
            cwd = join(cwd, t[i + 1])
        elif not tok.startswith("-") and (i == 0 or t[i - 1] not in ("-C", "-c")):
            break
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


# git accepts any unique prefix of a long option, and clusters short ones (-uf).
PUSH_LONG = ("all", "atomic", "branches", "delete", "dry-run", "exec", "follow-tags", "force",
             "force-if-includes", "force-with-lease", "ipv4", "ipv6", "mirror",
             "no-atomic", "no-follow-tags", "no-force-if-includes", "no-force-with-lease",
             "no-recurse-submodules", "no-signed", "no-thin", "no-verify", "porcelain",
             "progress", "prune", "push-option", "quiet", "receive-pack", "recurse-submodules",
             "repo", "set-upstream", "signed", "tags", "thin", "verbose", "verify")
PUSH_LONG_VALUE = ("exec", "push-option", "receive-pack", "repo")
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def parse_push(args):
    """(options, positionals). options: [(name, value)], long names resolved from prefixes
    (an ambiguous prefix yields every candidate), short clusters split into letters."""
    opts, positional = [], []
    i = 0
    while i < len(args):
        t = args[i]
        i += 1
        if t == "--":
            positional += args[i:]
            break
        if t.startswith("--"):
            name, eq, value = t[2:].partition("=")
            names = [name] if name in PUSH_LONG else [n for n in PUSH_LONG if n.startswith(name)]
            if not eq and any(n in PUSH_LONG_VALUE for n in names) and i < len(args):
                value = args[i]
                i += 1
            opts += [(n, value) for n in names or [name]]
        elif t.startswith("-") and len(t) > 1:
            for j, ch in enumerate(t[1:], 1):
                if ch == "o":  # -o <value> / -o<value>
                    if j == len(t) - 1:
                        i += 1
                    break
                opts.append((ch, ""))
        else:
            positional.append(t)
    return opts, positional


def branch_name(ref):
    for prefix in ("refs/heads/", "heads/"):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    return ref


def push_targets(refspecs, cwd):
    """[(destination branch, or None when it can't be told; forced by a +refspec)]."""
    out = []
    for r in refspecs:
        plus = r.startswith("+")
        src, _, dst = r.lstrip("+").partition(":")
        dest = dst or src
        if dest in ("HEAD", "@"):
            dest = current_branch(cwd)
        elif not dest or re.search(r"[*$`@^~]", dest):  # wildcard, shell or rev syntax
            dest = None
        out.append((branch_name(dest) if dest else None, plus))
    return out


NAME_IT = "name the branch you push: `git push origin factory/<id>`"


def check_push(args, cwd):
    opts, positional = parse_push(args)
    names = set(n for n, _ in opts)
    if names & set(("force", "f", "mirror", "all", "branches")):
        return ("git push --force/--mirror/--all is not allowed; use "
                "--force-with-lease --force-if-includes on factory/<id>")
    if "no-verify" in names:
        return "--no-verify is not allowed"
    refspecs = positional[1:]
    if not refspecs:
        if names & set(("tags", "follow-tags")) and "force-with-lease" not in names:
            return None
        return ("a push with no branch goes wherever git config says (upstream, push.default); "
                + NAME_IT)
    targets = push_targets(refspecs, cwd)
    if any(dest in PROTECTED for dest, _ in targets):
        return "nothing is pushed to main directly — work reaches main only through a merged PR"
    if any(plus for _, plus in targets):
        return ("a +refspec is a plain force push (it overrides any lease); use "
                "--force-with-lease --force-if-includes without the +")
    if any(dest is None for dest, _ in targets):
        return "can't tell which branch this pushes to; " + NAME_IT
    leases = [v for n, v in opts if n == "force-with-lease"]
    if leases:
        for dest, _ in targets:
            if not dest.startswith("factory/"):
                return "force pushes are only for factory/<id> branches, not %s" % dest
        pinned = all(SHA_RE.match(v.partition(":")[2]) for v in leases)
        includes = "force-if-includes" in names and "no-force-if-includes" not in names
        if not pinned and not includes:
            return ("--force-with-lease alone can clobber commits a background fetch pulled in; "
                    "add --force-if-includes (or pin it: --force-with-lease=<branch>:<full sha>)")
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
    """Walk the command's segments, following directory changes. A directory the guard can't
    follow becomes None, which blocks only pushes that depend on it (HEAD, @)."""
    saved = []  # cwd before each open subshell / brace group
    for seg in SPLIT_RE.split(command):
        toks = tokens(seg)
        while toks and toks[0] in ("(", "{"):
            saved.append(cwd)
            toks = toks[1:]
        while toks and toks[0][:1] == "(":
            saved.append(cwd)
            toks[0] = toks[0][1:]
            if not toks[0]:
                toks = toks[1:]
        closes = 0
        while toks and toks[-1] and set(toks[-1]) <= set(")}"):
            closes += len(toks[-1])
            toks = toks[:-1]
        while toks and toks[-1].endswith(")"):
            closes += 1
            toks[-1] = toks[-1][:-1]
        if toks[:1] in (["cd"], ["pushd"]):
            rest = [t for t in toks[1:] if t != "--"]
            cwd = join(cwd, rest[0] if rest else "~") if rest[:1] != ["-"] else None
        elif toks[:1] == ["popd"]:
            cwd = None
        else:
            reason = check_segment(toks, is_agent, cwd)
            if reason:
                return reason
        for _ in range(closes):
            cwd = saved.pop() if saved else cwd
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
