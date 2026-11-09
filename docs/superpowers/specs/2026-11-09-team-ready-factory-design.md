# Team-ready software factory — design

Status: draft for review. Plugin: new `shared-software-factory` (v0.1.0), a copy of `software-factory` that is left untouched. First target repo: insta-connect (private, GitHub Free).

## Intent

The factory works for one developer on one machine because all job state lives in an untracked, per-clone `factory/` folder. insta-connect will soon have two or more developers. They must be able to plan, take tickets, see each other's progress and approve work, without colliding or duplicating work.

## Goals

1. Any developer can plan an epic; any developer can take any ticket.
2. Two developers can never build the same ticket or create the same job ID.
3. Every developer sees the status of every job, including jobs started on other machines.
4. Any teammate can run `approve` / `rework` on any job.
5. Everything the factory names (job, ticket, epic, PR) is a clickable GitHub issue or PR link, in the dashboard, the status output, PR comments, flag comments and reports.
6. Setup is done once per repo and committed; a teammate only installs the plugin.

## Non-goals / anti-goals

- No extra human approval gate. The factory still merges by itself when every review passes and the approver writes APPROVE (unchanged).
- No externally hosted dashboard (no outside accounts or secrets).
- Not a failure-avoidance rewrite: single-developer use must keep working.

## Design

### 1. GitHub is the source of truth
- Job ID = `<issue-number>-<slug>` (e.g. `123-rate-limiting`). Issue numbers are globally unique, so IDs and `factory/<id>` branches cannot collide. Replaces the local "max + 1" counter.
- ADR numbers and plan slugs are checked against `origin/main` and open PRs before use.
- `board.json` becomes a local cache. `/factory status` and every `run` rebuild it from issues, labels, PRs and the `<!-- factory:spec -->` comments.

### 2. Claiming
- Before starting a ticket the factory checks assignee and the `in-progress` label. If held by someone else it skips it and says who holds it (with a link).
- If free, it assigns the issue to the running developer's `gh` user and sets `in-progress`, then re-reads to confirm it won (guards against a simultaneous claim).
- Epic task-list edits use read-modify-write with a re-read and retry, not a blind overwrite.

### 3. Shared history
- Review verdicts, build notes and the approver's decision are posted as PR comments (marked, e.g. `<!-- factory:review round-N -->`), so any teammate can read them and `rework` can rebuild context from GitHub when `factory/jobs/` is absent.

### 4. Commands that work from GitHub state
- New `/factory status`: table of all jobs (id, stage, owner, round, issue link, PR link).
- `approve <job>` and `rework <job> <note>` reconstruct the job from GitHub if it is not in the local board; a fresh builder is spawned from the PR comments and spec.
- `run` only picks unclaimed, unblocked tickets.

### 5. Links
Every mention of a job, ticket, epic or PR is a full URL or markdown link: board entries (`issueUrl`, `prUrl`), dashboard cards, `status` output, the `run` report table, needs-human flag comments, epic task list, and commit/PR bodies (`Closes #N`).

### 6. Shared dashboard, chosen at setup
- Setup detects the plan with `gh api` (org plan, else user plan) and repo visibility. This often fails for non-admins, so it falls back to asking.
- **Enterprise Cloud**: GitHub Pages site with access restricted to repo members, rebuilt by a workflow on issue/PR/label events.
- **Free / Team (insta-connect)**: a GitHub Projects board; a workflow moves cards by stage and shows assignee and links.
- The existing local `dashboard.html` remains as an offline view fed by `/factory status`.

### 7. Committed, shared setup
- Setup writes shared config into the repo via the `factory/setup` PR: the Actions workflow(s), labels, a `.claude/settings.json` plugin prompt, and a committed profile (stack, test command).
- `skills_dir` becomes derived from the plugin location, not an absolute path. Per-clone items (`.git/info/exclude`, local cache) stay local.
- Following the repo rule in CLAUDE.md, any marketplace change ships as a `marketplace-entry.json` fragment, never `marketplace.json`.

## Constraints
- Prompt-driven plugin; the orchestrator is `skills/factory/SKILL.md`. No scripts exist today; any helper (status rebuild, dashboard generation) should be small, stdlib-only.
- Private repo on GitHub Free: no GitHub Pages.

## Left to the builder
Exact comment markers, workflow YAML, how the Projects board field mapping is created, and the claim race-recheck details. Choices marked "my call" in conversation (issue-number IDs, assignee-as-claim, PR-comment history, `/factory status`, committed setup) are proposals pending your approval.

## Open questions for the owner
- Should a claim expire if a developer abandons a ticket (e.g. stale `in-progress` after N days)?
