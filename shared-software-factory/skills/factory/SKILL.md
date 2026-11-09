---
name: factory
description: Run the software factory — grill the user, write specs as GitHub issues with dependencies, build independent tickets in parallel, review, and merge only through PRs (flagged for a human when in doubt). Use for "/factory <feature>", "/factory plan <epic>", "/factory run", "/factory approve <id>", "/factory rework <id> <note>", "/factory status", "/factory setup".
argument-hint: "<feature> | plan <epic> | run | next | status | approve <job-id> | rework <job-id> <note> | setup"
disable-model-invocation: true
---

# Software Factory — orchestrator

You (this session) are the **orchestrator**. You grill the user, run the scheduler, spawn every
agent, and (with `factory_team.py`) are the **only writer of `factory/board.json`** and the only one who talks to the
user. Agents get context from files, never from this conversation, and each writes only its own
file. Agents are non-interactive — **all user questions happen here, before specs exist.**

Arguments: `$ARGUMENTS`

## The loop (edit this to change the factory)

```
 feature / epic
      │
      ▼
 ┌──────────────┐   you, interactive: grilling + grill-with-docs
 │    GRILL     │──► decisions.md · ADRs + CONTEXT.md (docs PR → main) · no open questions
 └──────┬───────┘
        ▼
 ┌──────────────┐   planner (opus) → you quiz the user on slices & dependencies
 │     PLAN     │──► GitHub: epic issue + 1 sub-issue per ticket, native "blocked by" links
 └──────┬───────┘
        ▼   scheduler: every READY ticket runs in parallel (max_parallel)
 ┌──────────────────────────────────────────────────────────────────┐
 │ per ticket:  spec-writer ─► builder ─► opens PR (never merges)   │
 │              ─► security · ux · ui · code reviews in parallel    │
 │              ─► any CHANGES: resume builder (max 3 rounds) ─┐    │
 │              ─► all PASS: approver ◄────────────────────────┘    │
 └───────────────┬───────────────────────────────┬──────────────────┘
          APPROVE + CI green               ESCALATE / any doubt
                 ▼                               ▼
      you: gh pr merge (squash)        PR labelled needs-human-review
      issue closed, dependents go      + comment; stays OPEN; human
                                       decides  ◄── /factory approve | rework
```

Readiness of a ticket (blockers come from the issue's native "blocked by" links):

| Blocker state | Dependent does |
| --- | --- |
| all blockers `merged` | start now, branch from `main` |
| a blocker is `pr-open` (approved, PR not yet merged) and every other blocker is merged | **stack**: branch from the blocker's branch, PR targets that branch |
| a blocker is anywhere else (blocked/spec/build/review/approve/`needs-human`) | wait |

Agents ship in this plugin and are namespaced `shared-software-factory:<name>` — `planner`,
`spec-writer`, `builder`, `reviewer-security`, `reviewer-ux`, `reviewer-ui`, `reviewer-code`,
`approver`. Plugin root: `${CLAUDE_PLUGIN_ROOT}`; templates in
`${CLAUDE_PLUGIN_ROOT}/skills/factory/templates/`; the skills the agents follow (including
`grilling` and `grill-with-docs`, which **you** follow) are in `${CLAUDE_SKILL_DIR}/library/`.

`MAX_ROUNDS = 3` review rounds. `max_parallel` comes from `factory/profile.md` (default 3).

## Hard rules

1. **Nothing reaches `main` except by a merged pull request.** No `git merge`, `git push origin
   main`, `git commit` on `main`, `--admin`, or `--no-verify` — even if you have permission.
   (Sole exception: `setup` on a repo with zero commits makes the bootstrap commit.)
2. **Merging is `gh pr merge --squash --delete-branch` and only when** the approver wrote
   `APPROVE`, the PR's base is `main`, every check is green, and the PR is mergeable. If GitHub
   refuses (branch protection, required reviews), flag it — never work around it.
3. **Any doubt → flag for human review** (see "Flagging"). Doubt is a legitimate reason.
4. **No unresolved question reaches a spec.** Grill first; agents return `OPEN QUESTIONS`
   rather than guess, and you grill those out.
5. GitHub is the board and the durable record (issues, assignees, labels, dependencies, PRs,
   ADRs in `docs/adr/`). `factory/` is a per-clone cache of working state, excluded from git
   (`.git/info/exclude`), never committed, and never trusted over GitHub. Never drive a job
   whose owner is another developer.

## Files

```
factory/profile.md                    repo profile: stack, test cmd, conventions, skills_dir, max_parallel
factory/board.json                    per-clone cache of the board (rebuilt from GitHub by factory_team.py; the dashboard reads it)
factory/backlog.md                    local mirror of ready tickets (you write it)
factory/plans/<slug>/decisions.md     grilling output (you)        — binding for planner/spec-writer
factory/plans/<slug>/plan.md          planner: ticket breakdown
factory/jobs/<id>/ticket.md           copy of the GitHub issue body (you)
factory/jobs/<id>/spec.md             spec-writer
factory/jobs/<id>/build.md            builder
factory/jobs/<id>/round-N/review-{security,ux,ui,code}.md   reviewers
factory/jobs/<id>/round-N/human-note.md                     you (rework only)
factory/jobs/<id>/decision.md                               approver
docs/adr/NNNN-slug.md, CONTEXT.md     in the repo, via a docs PR
```

## board.json

Rewrite the whole file on every transition, then validate with `python3 -m json.tool factory/board.json >/dev/null`.

The board is rebuilt from GitHub on every `run` (Sync) by `factory_team.py board`. That rebuild
leaves `blockedBy`, `reviews`, `rounds` and `decision` empty, because they cannot be derived
from GitHub inputs. It is **not** the complete board: read blocked-by links from GitHub
(`gh api repos/<repo>/issues/<n>/dependencies/blocked_by`, falling back to the issue's
`## Blocked by` body line), and record review chips, rounds, decision and blockedBy yourself by
editing those four fields in `factory/board.json`; `factory_team.py board` preserves them across
rebuilds for every job still on GitHub (jobs gone from GitHub are dropped). Jobs of other developers appear with `owner` = their login; they are visible
but never yours to drive. Each job also carries `issueUrl` (and a PR URL) for links.

```json
{ "jobs": [ {
  "id": "42-rate-limiting", "title": "Rate limiting on the API",   // <issue>-<slug>; slug = kebab-case, at most 4 words
  "plan": "api-hardening", "ticket": "T3",
  "issue": 42, "epic": 40, "pr": 57,
  "blockedBy": ["41-token-store"],        // job ids; mirrors the issue's native blocked-by links
  "branch": "factory/42-rate-limiting",
  "base": "main",                          // or the blocker's branch when stacked
  "stage": "review",   // blocked | spec | build | review | approve | pr-open | merged | needs-human
  "round": 2,
  "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" },
  "rounds": [ { "n": 1, "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "PASS", "code": "CHANGES" } } ],
  "decision": null,    // APPROVE | ESCALATE | null
  "note": "",
  "updated": "2026-11-04T12:00:00Z"
} ] }
```

## Commands

### `setup` (also run automatically when `factory/profile.md` is missing)

1. **GitHub is required.** Run `gh auth status` and `gh repo view --json nameWithOwner,defaultBranchRef`.
   No `gh`, not logged in, or no GitHub remote → stop and tell the user exactly what to fix.
   Git: if not a repo, `git init -b main`. If the repo has **zero commits**, make the bootstrap
   commit and (after the user supplies/creates the GitHub remote) push `main` — the only direct
   push the factory ever does. Otherwise ensure branch `main` exists and the main checkout is
   clean outside `factory/`; other dirt → ask the user to commit/stash first.
2. Scaffold (skip files that already exist — never overwrite project state):
   - copy `${CLAUDE_PLUGIN_ROOT}/skills/factory/templates/{dashboard.html,board.json,backlog.md,README.md}`
     into `factory/`, and `mkdir -p factory/jobs factory/plans`;
   - append `factory/` and `.worktrees/` to `.git/info/exclude` if missing (local-only, no commit);
   - create the labels (idempotent, `gh label create <name> --force`): `factory`, `epic`,
     `ready`, `blocked`, `in-progress`, `factory-approved`, `needs-human-review`;
   - `dashboard.html` is refreshed from the template on every setup (it holds no state);
   - offer (AskUserQuestion) a `.claude/settings.json` that prompts teammates to install this
     plugin. If accepted, ship it as a PR from branch `factory/setup` and **flag it for human
     review** (it is config) — never commit it to `main`.
3. Skills dir is the bundled library: `${CLAUDE_SKILL_DIR}/library` (resolve to an absolute path).
   Check it has `grilling`, `grill-with-docs`, `to-spec`, `implement`, `tdd`, `code-review`,
   `to-tickets`, `domain-modeling`. Missing → the plugin install is broken; stop and say so.
4. Inspect the repo (manifest files, test dirs, lint configs, README/CONTRIBUTING/CLAUDE.md,
   CONTEXT.md, docs/adr) and write `factory/profile.md`:
   ```
   # Repo profile
   skills_dir: <abs path from step 3>
   repo: <owner/name>
   stack: <language/framework, or "undecided" if no app code yet>
   install: <cmd or none>
   test: <cmd, or "undecided">
   lint: <cmd or none>
   has_ui: <yes|no|undecided>
   max_parallel: 3
   conventions: <bullets: layout, naming, test style, standards docs found>
   ```
   Empty repo → `stack: undecided`; the grilling picks the stack, the first ticket scaffolds it,
   and you re-run setup after that ticket merges. Re-run setup after a plugin update.

### Grill (used by `plan` and `<feature>`)

Before any spec or ticket exists, run the `grill-with-docs` skill **yourself, interactively**
(`${CLAUDE_SKILL_DIR}/library/grill-with-docs/SKILL.md`, which uses `grilling` and
`domain-modeling`). Slug = kebab of the epic/feature (≤4 words).

1. Explore the repo first; ask only what the code and research can't answer; one question at a
   time with your recommended answer (AskUserQuestion is fine).
2. Write `factory/plans/<slug>/decisions.md` as you go. Draft ADRs (`docs/adr/NNNN-…md`) and
   `CONTEXT.md` glossary entries in a docs worktree:
   `git worktree add .worktrees/docs-<slug> -b factory/docs-<slug> main`.
3. When the user confirms the decision list, ship the docs: commit in that worktree, `git push
   -u origin factory/docs-<slug>`, `gh pr create --base main` titled `docs: ADRs for <slug>`.
   Then merge it by the normal merge path **only if** the diff touches nothing but `docs/adr/**`
   and `CONTEXT.md` and checks are green; otherwise flag it and tell the user to merge PR #N,
   then re-run. Do not start planning/jobs until the docs PR is merged (or there are no docs).
   Remove the docs worktree afterwards.

### `plan <epic>` — grill → breakdown → GitHub

1. Ensure setup. Run **Grill**.
2. Spawn `planner` (name it `planner-<slug>`): `Epic: "<epic>". Decisions: factory/plans/<slug>/decisions.md. Write factory/plans/<slug>/plan.md.`
   Reply `OPEN QUESTIONS` → grill the user on exactly those (append to decisions.md), then
   `SendMessage` the planner to continue.
3. Show the breakdown as a numbered list (title · blocked by · ACs count) and mark which tickets
   are independent (will run in parallel). Ask (AskUserQuestion): approve / too coarse / too
   fine / change dependencies. Feedback → `SendMessage` the planner; repeat.
4. **Publish to GitHub** on approval (blockers first, so you have real issue numbers):
   - Epic: `gh issue create --label factory,epic --title "Epic: <epic>"` with a body of the
     decisions summary (each D<n> one line, ADR links) and a task list `- [ ] #N` filled in
     after the tickets exist.
   - Each ticket: `gh issue create --label factory,ready|blocked` (use `blocked` if it has
     blockers), title = ticket title, body = the to-tickets template (`## Parent #<epic>`,
     `## What to build`, `## Acceptance criteria`, `## Decisions`, `## Blocked by` as
     `- #N`/`None - can start immediately`).
   - Link each ticket as a sub-issue of the epic and set native dependencies:
     `ID=$(gh api repos/<repo>/issues/<N> --jq .id)`;
     `gh api -X POST repos/<repo>/issues/<epic>/sub_issues -F sub_issue_id=$ID`;
     `gh api -X POST repos/<repo>/issues/<ticket>/dependencies/blocked_by -F issue_id=<blocker's ID>`.
     If an endpoint 404s/422s (older GitHub plan), keep the `## Blocked by` body line as the
     only record, say so in the epic, and read dependencies from that body line on GitHub (GitHub stays the source).
5. Add one board entry per ticket with stage `blocked` (meaning "not started yet"; `blockedBy`
   may be empty, in which case it is simply queued and the scheduler promotes it). Append to `factory/backlog.md`: `- [ ] #<N> <title> {plan: <slug>#T<n>, after: #a,#b}`.
6. Report: epic as a link, N tickets (each as a `[#N](url)` link), which start immediately in parallel. Then run **`run`**.

### `<feature>` — one feature, no epic

Run **Grill**, then treat it as a one-ticket plan. The job id is `<issue>-<slug>`, so create the
GitHub issue **first** (label `factory,in-progress`, assign `@me`, title = feature, body = the
feature summary) and take its number as `<issue>`; there is no local counter. Spawn
`spec-writer` (Spec step below), then replace the issue body with **spec.md** and continue the
pipeline from Build. No epic, no dependencies. Print the issue as a link, `[#<issue>](<issueUrl>)`.

### `run` (alias `next`) — the scheduler

Repeat until nothing is runnable or in flight (`next` = at most one new job):

1. **Sync.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/factory_team.py board --repo <owner/name> --out factory`
   and treat the result as the board; local files hold only caches. Then, for each non-merged job
   that is yours, `gh pr view` (state, checks, base) and read its blocked-by links from GitHub
   (the rebuild leaves `blockedBy` empty; you edit `blockedBy`, `reviews`, `rounds` and
   `decision` in `factory/board.json`, and `board` preserves them for jobs still on GitHub). A PR a human merged/closed → update the board. Run
   `git fetch origin` and `git -C <main checkout> pull --ff-only`. Never drive a job whose
   owner is someone else.
2. **Promote.** For each `blocked` job apply the readiness table. Ready → check capacity
   **first**: respect `max_parallel` (count jobs in spec/build/review/approve); no free slot →
   leave it queued and do not claim. Otherwise **claim** it, then create its workspace and
   start it.

   **Claim.** Run `python3 ${CLAUDE_SKILL_DIR}/scripts/factory_team.py claim check --repo <owner/name> --issue <N>`.
   It prints one line:
   - `other <holder> <url>` → skip the job and print who has it with the link:
     `[#<N>](<url>) is held by @<holder>` (holder `none` → `[#<N>](<url>) is claimed (no assignee)`).
   - `mine` → proceed.
   - `free` → `gh issue edit <N> --add-assignee @me --add-label in-progress`, then re-read the
     issue with `factory_team.py claim verify --repo <owner/name> --issue <N>` (it re-reads via
     `gh issue view` and applies `decide_claim_winner`). `won` → keep the claim. `lost` → someone
     else was first: remove your own assignee (`gh issue edit <N> --remove-assignee @me`; also
     `--remove-label in-progress` only if no assignee remains, since the winner relies on it)
     and skip.
   - If a claim was won but the job then cannot start (workspace or setup failure), release it
     the same way: remove your assignee, and the `in-progress` label if no assignee remains.

   Workspace: `git worktree add .worktrees/<id> -b factory/<id> <base>` where `<base>` is
   `main`, or for a stacked job `factory/<blocker-id>` (set `base` on the board). The issue keeps
   the `in-progress` label from the claim; remove `ready`/`blocked`.
3. **Drive every active job one step**, and **issue the Agent calls for all jobs that need one in
   a single message** so independent tickets truly run in parallel. As each agent returns,
   advance only that job; others keep going. Each job's steps:

   **Spec.** Stage `spec`. Write the issue body to `factory/jobs/<id>/ticket.md`. Spawn
   `spec-writer`: `Job <id>. Decisions: factory/plans/<slug>/decisions.md. Ticket: factory/jobs/<id>/ticket.md (GitHub #<N>). Write factory/jobs/<id>/spec.md.`
   - `OPEN QUESTIONS` in spec.md → pause **that job only**, grill the user on them (append to
     decisions.md, ADR if warranted via a docs PR), re-run the spec-writer.
   - No `## Acceptance Criteria` otherwise → flag.
   - Post spec.md on the issue as a comment starting `<!-- factory:spec -->` (edit the same
     comment on re-runs).

   **Build.** Stage `build`. Spawn `builder` named `builder-<id>`: `Job <id>. Branch factory/<id>, worktree .worktrees/<id>, Base branch <base>, issue #<N>. Read factory/jobs/<id>/spec.md, build it in the worktree, push, open the PR against <base>, write factory/jobs/<id>/build.md.`
   Record the PR number on the board. Builder reports a push/PR failure → flag.

   **Review round N** (start N=1). `mkdir -p factory/jobs/<id>/round-N`; stage `review`; append
   `{n:N, reviews: all "pending"}`. Spawn **all four reviewers in one message**, each with:
   `Job <id>. Branch factory/<id>, worktree .worktrees/<id>, Base branch <base>. Round folder factory/jobs/<id>/round-N/. Write your review there.`
   As each returns read the first line of its file and set its chip (PASS / CHANGES).
   **WAIT FOR ALL four** — never message the builder mid-round. A missing file or first line that
   isn't `VERDICT: PASS`/`VERDICT: CHANGES` → re-spawn just that reviewer once; still bad → CHANGES.
   - Any CHANGES and N < MAX_ROUNDS → stage `build`, `SendMessage` `builder-<id>`:
     `Round N reviews are in factory/jobs/<id>/round-N/. Fix every [blocker], re-run tests, commit, push, update build.md ("Round N fixes").`
     (If it can't be resumed, spawn a fresh `builder` named `builder-<id>` with the same message
     plus "read build.md for your previous work".) Then review round N+1.
   - Any CHANGES and N = MAX_ROUNDS → **flag**: "reviews still CHANGES after N rounds".

   **Approve.** All four PASS → stage `approve`. Spawn `approver`: `Job <id>. Branch factory/<id>, worktree .worktrees/<id>, Base branch <base>, PR #<pr>. Rounds 1..N. Write factory/jobs/<id>/decision.md.`
   Read the first word of decision.md:
   - `APPROVE` → add label `factory-approved` to the PR, set decision `APPROVE`, stage `pr-open`,
     then **Merge**.
   - `ESCALATE` or anything else → **flag**, note = the approver's first reason.

   **Merge** (a `pr-open` job; re-evaluated on every scheduler pass):
   - PR base ≠ `main` (stacked): wait until the base blocker is `merged`. Then **restack**: in the
     job's worktree `git fetch origin && git rebase --onto origin/main factory/<blocker-id>`
     (squash-merged base: use the blocker's pre-merge tip SHA recorded on the board as the
     `--onto` upstream); `git push --force-with-lease`; `gh pr edit <pr> --base main`; set
     `base: main`. Rebase conflict → `git rebase --abort`, **flag** "restack conflict". If the
     restacked diff's `git patch-id` differs from before the rebase, send the job back to
     **Review** round N+1 (stage `review`); otherwise continue.
   - PR base is `main`: check `gh pr checks <pr>` and `gh pr view <pr> --json mergeable`.
     Pending → stay `pr-open` (flag if pending > 30 min). Failing/conflicting → **flag**.
     All green → `gh pr merge <pr> --squash --delete-branch`. Refused → **flag**.
   - Merged: stage `merged`; `git worktree remove .worktrees/<id>`; ensure the issue is closed
     (`gh issue close <N> --comment "merged in #<pr>"` if GitHub didn't auto-close it); `git -C <main> pull
     --ff-only`; tick the ticket in the epic's task list: re-read the epic body right before
     `gh issue edit <epic> --body-file …` (another developer may have ticked theirs), and if it
     changed since you read it, re-apply your tick to the fresh body and retry once. If `stack: undecided` was resolved by this job, re-run setup.

4. Loop back to step 1 whenever any job changed state (a merge can ready new dependents).
5. Finish by reporting a table: id · issue · PR · stage · note. The issue and PR cells are
   markdown links (`[#42](<issueUrl>)`, `[#57](<PR url>)`). Name every flagged PR with its
   reason (as a link), and what is still waiting on whom.

### `status` — read-only team view

`/factory status`: run `python3 ${CLAUDE_SKILL_DIR}/scripts/factory_team.py status --repo <owner/name>`
and print its table as is (every job from every developer, owner column included, issue and PR
as links). Then name each stale claim (an `in-progress` issue with no recent activity, as the
table marks it) with its owner and link. It changes nothing on GitHub or locally.

### Flagging (`flag(job, reason)`)

Never merge. Set stage `needs-human`, note = reason; label the PR and issue `needs-human-review`;
post one PR comment with the reason, a link to the PR, the "Notes for the human" from decision.md if any, and the
exact commands to continue (`/factory approve <id>` or `/factory rework <id> "<note>"`). Leave
the PR **open**. Jobs stacked on or blocked by this one keep waiting (the readiness table).

### `approve <job-id>`

Job must be `needs-human` (or `approve`/`pr-open`) and yours (owner is you). First `gh pr view` — if the human already
merged it on GitHub, just sync the board. Otherwise append `\n---\nHUMAN APPROVE <date>` to
decision.md, set decision `APPROVE`, remove `needs-human-review`, add `factory-approved`, set
stage `pr-open`, and run **Merge** (same gates: base `main`, checks green; a human approval
overrides the approver's ESCALATE, not a failing CI). Then run `run` to release dependents.

### `rework <job-id> <note>`

1. Next round number N = last round + 1. `mkdir -p round-N`, write the note to
   `factory/jobs/<id>/round-N/human-note.md` (a blocker by definition). Remove `needs-human-review`.
2. Stage `build`, note "human rework". `SendMessage` `builder-<id>` (or re-spawn it):
   `Human feedback is in factory/jobs/<id>/round-N/human-note.md. Address it, re-run tests, commit, push, update build.md.`
3. Continue at review round N+1, with MAX_ROUNDS counted from this rework.
4. Every job stacked on this one: once this job's new tip is pushed, `SendMessage` that job's
   builder `Base changed: rebase onto factory/<id>, re-run tests, push --force-with-lease`, set
   its stage `build`, then re-review it. If its builder can't be resumed, spawn a fresh one.

## Rules

- Agents get context from files, not the conversation; each writes only its own file.
- Every review's first line is `VERDICT: PASS` or `VERDICT: CHANGES`; decision.md starts with `APPROVE` or `ESCALATE`.
- Builders work and commit only on `factory/<id>` and open PRs; **only you merge, only via `gh pr merge`.**
- Independent tickets run in parallel; never serialise work that has no blocker.
- Keep GitHub current: labels follow the stage, the PR/issue links are on the board, one comment
  per event (spec posted, PR flagged, merged) — not per step.
- Keep chatter minimal: one line to the user per stage transition, except during grilling.
- Whenever you name a job, ticket, epic or PR to the user, give it as a markdown link.
