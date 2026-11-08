---
name: factory
description: Run the software factory — take a feature through spec → build → 4 parallel reviews → approve → merge, tracked on factory/board.json. Use for "/factory <feature>", "/factory plan <epic>", "/factory next", "/factory approve <id>", "/factory rework <id> <note>", "/factory setup".
argument-hint: "<feature> | plan <epic> | next | approve <job-id> | rework <job-id> <note> | setup"
disable-model-invocation: true
---

# Software Factory — orchestrator

You (this session) are the **orchestrator**. You run the loop, spawn every agent, and are the
**only writer of `factory/board.json`**. Agents get context from files, never from this
conversation, and each writes only its own file.

Arguments: `$ARGUMENTS`

## The loop (edit this to change the factory)

```
                   ┌──────────────────┐
                   │     feature      │
                   └─────────┬────────┘
                             ▼
                   ┌──────────────────┐
                   │   spec-writer    │
                   │       opus       │
                   └─────────┬────────┘
                             ▼
                   ┌──────────────────┐
                   │     builder      │◄────────────────────┐
                   │       opus       │                     │
                   └─────────┬────────┘                     │
        ┌─────────────┬──────┴──────┬─────────────┐         │
        ▼             ▼             ▼             ▼         │
  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
  │  security │ │     ux    │ │ ui design │ │    code   │   │
  │    opus   │ │   sonnet  │ │   sonnet  │ │   sonnet  │   │
  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘   │
        └─────────────┴──────┬──────┴─────────────┘         │
                             ▼                              │
                   ┌──────────────────┐   any CHANGES:      │
                   │   WAIT FOR ALL   ├─────────────────────┘
                   │   4 reviews in   │   resume builder
                   └─────────┬────────┘   (max 2 rounds)
                             ▼ all PASS
                   ┌──────────────────┐
                   │     approver     │
                   │       opus       │
                   └─┬───────────────┬┘
             APPROVE │               │ ESCALATE
                     ▼               ▼
              ┌─────────────┐ ┌─────────────┐
              │merge to main│ │ needs-human │ ◄── /factory approve
              └─────────────┘ └─────────────┘
```

Before the loop, an optional **backlog breakdown**: `/factory plan <epic>` → `planner` (opus)
splits a big idea into vertical-slice tickets → you confirm with the user → tickets land in
`backlog.md` → `/factory next` feeds them through the loop one at a time.

Agents ship in this plugin and are namespaced: spawn them with `subagent_type`
`software-factory:<name>` — `planner`, `spec-writer`, `builder`, `reviewer-security`,
`reviewer-ux`, `reviewer-ui`, `reviewer-code`, `approver`. Below, "spawn `builder`" means
`software-factory:builder`.

Plugin root: `${CLAUDE_PLUGIN_ROOT}` — project templates live in
`${CLAUDE_PLUGIN_ROOT}/skills/factory/templates/`. The skills the agents follow
(tdd, to-spec, code-review, …) are bundled in `${CLAUDE_SKILL_DIR}/library/` — no other plugin needed.

`MAX_ROUNDS = 3` review rounds (= 2 rework rounds).

## Files

```
factory/profile.md           repo profile: stack, test cmd, conventions, skills_dir
factory/board.json           durable state (you write it, the dashboard reads it)
factory/backlog.md           "- [ ] feature" queue (you write it)
factory/plans/<slug>.md      planner: ticket breakdown of one epic
factory/jobs/<id>/spec.md    spec-writer
factory/jobs/<id>/build.md   builder
factory/jobs/<id>/round-N/review-{security,ux,ui,code}.md   reviewers
factory/jobs/<id>/round-N/human-note.md                     you (rework only)
factory/jobs/<id>/decision.md                               approver
```

## board.json

Rewrite the whole file on every transition, then validate with `python3 -m json.tool factory/board.json >/dev/null`.

```json
{ "jobs": [ {
  "id": "003-rate-limiting", "title": "Rate limiting on the API",
  "branch": "factory/003-rate-limiting",
  "stage": "review",              // spec | build | review | approve | merged | needs-human
  "round": 2,
  "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" },  // current round
  "rounds": [ { "n": 1, "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "PASS", "code": "CHANGES" } },
              { "n": 2, "reviews": { "security": "CHANGES", "ux": "PASS", "ui": "pending", "code": "PASS" } } ],
  "decision": null,               // APPROVE | ESCALATE | null
  "note": "",                     // short human-readable status, e.g. why needs-human
  "updated": "2026-11-04T12:00:00Z"
} ] }
```

## Commands

### `setup` (also run automatically when `factory/profile.md` is missing)

1. Git: if not a repo, `git init -b main` and make an initial commit. Ensure branch `main` exists.
   Ignore dirt under `factory/` (that's state); other
   uncommitted changes → ask the user to commit/stash first.
2. Scaffold (skip files that already exist — never overwrite project state):
   - copy `${CLAUDE_PLUGIN_ROOT}/skills/factory/templates/{dashboard.html,board.json,backlog.md,README.md}`
     into `factory/`, and `mkdir -p factory/jobs factory/plans`;
   - ensure `.gitignore` has `.worktrees/`;
   - offer (AskUserQuestion) to write/merge `.claude/settings.json` so teammates are prompted to
     install this plugin when they open the repo:
     `{"extraKnownMarketplaces":{"engineering-skills":{"source":{"source":"github","repo":"yogendrasgautam/skills"}}},"enabledPlugins":{"software-factory@engineering-skills":true}}`
   - `dashboard.html` is refreshed from the template on every setup (it holds no state).
3. Skills dir is the bundled library: `${CLAUDE_SKILL_DIR}/library` (resolve to an absolute path).
   Check it has `to-spec`, `implement`, `tdd`, `code-review`, `to-tickets`. Missing → the plugin install is broken; stop and say so.
4. Inspect the repo (manifest files, test dirs, lint configs, README/CONTRIBUTING/CLAUDE.md,
   CONTEXT.md, docs/adr) and write `factory/profile.md`:
   ```
   # Repo profile
   skills_dir: <abs path from step 3>
   stack: <language/framework, or "undecided" if no app code yet>
   install: <cmd or none>
   test: <cmd, or "undecided">
   lint: <cmd or none>
   has_ui: <yes|no|undecided>
   conventions: <bullets: layout, naming, test style, standards docs found>
   ```
   Empty repo → `stack: undecided`; the first spec picks the stack, the builder scaffolds it,
   and you re-run setup after that job merges.
   Re-run setup after a software-factory update so `skills_dir` points at the new version.

### `<feature>` — new job

1. Ensure setup done; main checkout is on `main` and clean outside `factory/`.
   Create the job's isolated workspace: `git worktree add .worktrees/<id> -b factory/<id> main`.
   The main checkout **stays on main** the whole time, so `factory/` state never moves.
2. Id = next 3-digit number (max existing in `factory/jobs/` + 1) + `-` + kebab slug (≤4 words).
   `mkdir -p factory/jobs/<id>`. Add a board entry: stage `spec`, round 0, rounds `[]`.
3. **Spec.** Spawn `spec-writer` (Agent tool, subagent_type `spec-writer`) with prompt:
   `Job <id>. Feature: "<feature text>". Write factory/jobs/<id>/spec.md.`
   Then check spec.md exists and contains `## Acceptance Criteria`. If not, needs-human.
4. **Build.** Board stage `build`. Spawn `builder` **with name `builder-<id>`** (Agent tool `name`
   param) and prompt: `Job <id>. Branch factory/<id>, worktree .worktrees/<id>. Read factory/jobs/<id>/spec.md, build it in the worktree, write factory/jobs/<id>/build.md.`
5. **Review round N** (start N=1):
   - `mkdir -p factory/jobs/<id>/round-N`; board stage `review`, round N, append
     `{n:N, reviews: all "pending"}`, set `reviews` to the same.
   - Spawn **all four reviewers in one message** (parallel Agent calls), each with:
     `Job <id>. Branch factory/<id>, worktree .worktrees/<id>. Round folder factory/jobs/<id>/round-N/. Write your review there.`
   - As each returns, read the first line of its file and set its chip (PASS / CHANGES) on the board.
6. **WAIT FOR ALL.** The round is done only when all four `review-*.md` files exist in `round-N/`.
   Never message the builder mid-round. A missing file or a first line that isn't
   `VERDICT: PASS` / `VERDICT: CHANGES` → re-spawn just that reviewer once; still bad → treat as CHANGES.
7. **Any CHANGES:**
   - N < MAX_ROUNDS → board stage `build`; `SendMessage` to `builder-<id>`:
     `Round N reviews are in factory/jobs/<id>/round-N/. Fix every [blocker], re-run tests, commit, update build.md (add a "Round N fixes" section).`
     If the builder can't be resumed (new session), spawn a fresh `builder` named `builder-<id>`
     with the same message plus "read build.md for your previous work". Then go to step 5 with N+1.
   - N = MAX_ROUNDS → stage `needs-human`, note "reviews still CHANGES after N rounds". Stop.
8. **All PASS.** Board stage `approve`. Spawn `approver`:
   `Job <id>. Branch factory/<id>, worktree .worktrees/<id>. Rounds 1..N. Write factory/jobs/<id>/decision.md.`
   Read the first word of decision.md:
   - `APPROVE` → (main checkout, on main) `git merge --no-ff factory/<id> -m "factory: merge <id>"`.
     Success → stage `merged`, `git worktree remove .worktrees/<id>`. Conflict → `git merge --abort`, stage `needs-human`, note "merge conflict".
   - `ESCALATE` (or anything else) → stage `needs-human`, note = the approver's first reason.
9. Report to the user: id, final stage, rounds, one-line reason. If stack was `undecided`
   and the job merged, re-run setup.

### `plan <epic>` — backlog breakdown

1. Ensure setup done. Slug = kebab of the epic (≤4 words). `mkdir -p factory/plans`.
2. Spawn `planner`: `Epic: "<epic text>". Write factory/plans/<slug>.md.`
3. Show the user the breakdown from the plan file as a numbered list (title · blocked by · ACs count)
   and ask (AskUserQuestion): approve / too coarse / too fine / edit. This is the to-tickets "quiz"
   step — you do it, because agents are non-interactive.
   Feedback → `SendMessage` the planner (name it `planner-<slug>` when spawning) to revise; repeat.
4. On approval append one line per ticket to `factory/backlog.md`, in the plan's order:
   `- [ ] <title> {plan: <slug>#T<n>, after: T<a>,T<b>}` (omit `after:` when no blockers).
5. Report: N tickets queued; next one up.

### `next`

1. Take the first `- [ ]` line in `factory/backlog.md` that is **ready**: no `after:`, or every
   ticket it names (same plan) is already `- [x] … merged`. None ready → list what's blocked and stop.
2. Run it as `<feature>`. If the line has `{plan: <slug>#T<n>}`, add to the spec-writer prompt:
   `Ticket: factory/plans/<slug>.md section T<n> — use its What to build and Acceptance criteria as the contract.`
3. Change the line to `- [x] <text> {…} (<id>, <final stage>)`. Nothing unchecked → say so.

### `approve <job-id>`

Job must be `needs-human` (or `approve`). Merge as in step 8. Append to decision.md:
`\n---\nHUMAN APPROVE <date>` and set board decision `APPROVE`, stage `merged`.

### `rework <job-id> <note>`

1. Next round number N = last round + 1. `mkdir -p round-N`, write the note to
   `factory/jobs/<id>/round-N/human-note.md` (it is a blocker by definition).
2. Board stage `build`, note "human rework". `SendMessage` `builder-<id>` (or re-spawn it) with:
   `Human feedback is in factory/jobs/<id>/round-N/human-note.md. Address it, re-run tests, commit, update build.md.`
3. Continue at step 5 using round N+1 for the reviews (round N holds only the human note),
   with MAX_ROUNDS counted from this rework.

## Rules

- Agents get context from files, not the conversation; each writes only its own file.
- Every review's first line is `VERDICT: PASS` or `VERDICT: CHANGES`; decision.md starts with `APPROVE` or `ESCALATE`.
- Builder works and commits only on `factory/<id>`; only you merge to `main`.
- `factory/` state lives in the main checkout only. Commit it on `main` when a job ends:
  `git add factory && git commit -m "factory: <id> <stage>"`. The builder never touches `factory/`
  inside its worktree (its build.md goes to the main checkout's `factory/jobs/<id>/`).
- Keep chatter minimal: one line to the user per stage transition.
