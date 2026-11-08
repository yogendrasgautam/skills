---
name: setup
description: Configure this repo for the engineering-pipeline skills — set up its issue tracker (optionally mapping issues onto a GitHub Project), triage label vocabulary, and domain doc layout. Run once before first use of the other skills.
disable-model-invocation: true
---

# Setup

Scaffold the per-repo configuration the pipeline skills (`to-spec`, `to-tickets`, `triage`,
`implement`, `diagnosing-bugs`, `improve-codebase-architecture`) assume:

- **Issue tracker** — where issues live (GitHub by default; GitLab and local markdown are also
  supported out of the box)
- **GitHub Project mapping** (optional) — if the tracker is GitHub, whether new issues are also added
  to a GitHub Project (v2) board and which of its fields get set
- **Triage labels** — the strings used for the five canonical triage roles
- **Domain docs** — where `CONTEXT.md` and ADRs live, and the consumer rules for reading them

This is a prompt-driven skill, not a deterministic script. Explore, present what you found, confirm
with the user, then write.

## Process

### 1. Explore

Look at the current repo to understand its starting state. Read whatever exists; don't assume:

- `git remote -v` and `.git/config` — is this a GitHub repo? A GitLab repo? Which one?
- `CLAUDE.md` and `AGENTS.md` at the repo root — does either exist? Is there already an
  `## Agent skills` section in either?
- `CONTEXT.md` and `CONTEXT-MAP.md` at the repo root
- `docs/adr/` and any `src/*/docs/adr/` directories
- `docs/agents/` — does this skill's prior output already exist?
- `.scratch/` — sign that a local-markdown issue tracker convention is already in use

### 2. Present findings and ask

Summarise what's present and what's missing. Then walk the user through the decisions **one at a
time** — present a section, get the user's answer, then move to the next. Don't dump them all at once.

Assume the user does not know what these terms mean. Each section starts with a short explainer (what
it is, why these skills need it, what changes if they pick differently). Then show the choices and the
default.

**Section A — Issue tracker.**

> Explainer: The "issue tracker" is where issues live for this repo. Skills like `to-spec`,
> `to-tickets`, and `triage` read from and write to it — they need to know whether to call
> `gh issue create`, `glab issue create`, write a markdown file under `.scratch/`, or follow some
> other workflow you describe. Pick the place you actually track work for this repo.

Default posture: these skills were designed for GitHub. If a `git remote` points at GitHub, propose
that. If a `git remote` points at GitLab (`gitlab.com` or a self-hosted host), propose GitLab.
Otherwise (or if the user prefers), offer:

- **GitHub** — issues live in the repo's GitHub Issues (uses the `gh` CLI)
- **GitLab** — issues live in the repo's GitLab Issues (uses the [`glab`](https://gitlab.com/gitlab-org/cli) CLI)
- **Local markdown** — issues live as files under `.scratch/<feature>/` in this repo (good for solo
  projects or repos without a remote)
- **Other** (Jira, Linear, etc.) — ask the user to describe the workflow in one paragraph; the skill
  will record it as freeform prose

If — and only if — the user picked **GitHub** or **GitLab**, ask one follow-up:

> Explainer: Open-source repos often receive feature requests as pull requests, not just issues — a
> PR is an issue with attached code. If you turn this on, `/triage` pulls *external* PRs into the same
> queue and runs them through the same labels and states as issues (collaborators' in-flight PRs are
> left alone). Leave it off if PRs aren't a request surface for you.

- **PRs as a request surface** — yes / no (default: no). Record the answer in
  `docs/agents/issue-tracker.md`. For local-markdown and other trackers, skip this question — there
  are no PRs.

**Section A.5 — GitHub Project (only if the tracker is GitHub).**

Skip this section entirely for GitLab, local-markdown, and other trackers — Projects (v2) is a
GitHub-only feature.

> Explainer: A GitHub **Project** (v2) is a board/table owned by a **user or org** (not the repo). It
> is separate from GitHub **Issues**: an issue can exist without being on any board. "Mapping" means
> that whenever a skill creates an issue, it also adds that issue to your Project as an item and sets
> the item's fields — most commonly a **Status** column (Todo / In Progress / Done), and optionally
> Priority or other custom fields. Turn this on if you run your work off a Project board and want new
> tickets to land there automatically instead of only in the Issues list.

Ask: **Also add new issues to a GitHub Project and set their fields?** — yes / no (default: no). If
**no**, record "No GitHub Project — issues only" in the mapping section and move on.

If **yes**, follow [github-project.md](./github-project.md) to gather the mapping. In short:

1. **Check the token scope.** Run `gh auth status`. If `project` (or `read:project`) is not among the
   scopes, tell the user to run this in their own terminal — it's an interactive login the skill
   cannot perform:

   ```
   gh auth refresh -s project
   ```

   Pause until they confirm it's done, then continue.

2. **Get the project.** Ask for the project **OWNER** (the user login for a personal project, or the
   org login for an org project) and its **NUMBER** (the number in the project URL
   `https://github.com/orgs/<org>/projects/<NUMBER>` or `.../users/<user>/projects/<NUMBER>`). Accept a
   URL and parse it.

3. **Discover ids once** (names don't work with `item-edit` — it needs node ids):

   ```bash
   gh project view NUMBER --owner OWNER --format json --jq '{id,title,number}'
   gh project field-list NUMBER --owner OWNER --format json \
     --jq '.fields[] | {name, id, type, options: (.options // [] | map({name,id}))}'
   ```

4. **Pick the Status mapping.** Ask which field represents "Status" and which of its options a newly
   published AFK-ready ticket should get (default: the first / "Todo"). Optionally capture other
   fields the user wants set on creation.

Record the project node id, field ids, and option ids in the Project-mapping section of
`docs/agents/issue-tracker.md` (step 4). These ids are stable — capturing them once means the other
skills don't re-query on every run.

**Section B — Triage label vocabulary.**

> Explainer: When the `triage` skill processes an incoming issue, it moves it through a state machine —
> needs evaluation, waiting on reporter, ready for an AFK agent to pick up, ready for a human, or
> won't fix. To do that, it needs to apply labels (or the equivalent in your issue tracker) that match
> strings *you've actually configured*. If your repo already uses different label names (e.g.
> `bug:triage` instead of `needs-triage`), map them here so the skill applies the right ones instead
> of creating duplicates.

The five canonical roles:

- `needs-triage` — maintainer needs to evaluate
- `needs-info` — waiting on reporter
- `ready-for-agent` — fully specified, AFK-ready (an agent can pick it up with no human context)
- `ready-for-human` — needs human implementation
- `wontfix` — will not be actioned

Default: each role's string equals its name. Ask the user if they want to override any. If their issue
tracker has no existing labels, the defaults are fine.

If Section A.5 set up a Project, note that triage state changes can also move the Project's Status
field — record which Status option each state maps to (a sensible default: `ready-for-agent` /
`ready-for-human` → "In Progress" or a "Ready" column, `wontfix` → "Done"). Keep it simple; the user
can edit later.

**Section C — Domain docs.**

> Explainer: Some skills (`improve-codebase-architecture`, `diagnosing-bugs`, `tdd`) read a
> `CONTEXT.md` file to learn the project's domain language, and `docs/adr/` for past architectural
> decisions. They need to know whether the repo has one global context or multiple (e.g. a monorepo
> with separate frontend/backend contexts) so they look in the right place.

Confirm the layout:

- **Single-context** — one `CONTEXT.md` + `docs/adr/` at the repo root. Most repos are this.
- **Multi-context** — `CONTEXT-MAP.md` at the root pointing to per-context `CONTEXT.md` files
  (typically a monorepo).

### 3. Confirm and edit

Show the user a draft of:

- The `## Agent skills` block to add to whichever of `CLAUDE.md` / `AGENTS.md` is being edited (see
  step 4 for selection rules)
- The contents of `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`,
  `docs/agents/domain.md`

Let them edit before writing.

### 4. Write

**Pick the file to edit:**

- If `CLAUDE.md` exists, edit it.
- Else if `AGENTS.md` exists, edit it.
- If neither exists, ask the user which one to create — don't pick for them.

Never create `AGENTS.md` when `CLAUDE.md` already exists (or vice versa) — always edit the one that's
already there.

If an `## Agent skills` block already exists in the chosen file, update its contents in-place rather
than appending a duplicate. Don't overwrite user edits to the surrounding sections.

The block:

```markdown
## Agent skills

### Issue tracker

[one-line summary of where issues are tracked, whether external PRs are a triage surface, and whether
issues are mapped onto a GitHub Project]. See `docs/agents/issue-tracker.md`.

### Triage labels

[one-line summary of the label vocabulary]. See `docs/agents/triage-labels.md`.

### Domain docs

[one-line summary of layout — "single-context" or "multi-context"]. See `docs/agents/domain.md`.
```

Then write the three docs files using the seed templates in this skill folder as a starting point:

- [issue-tracker-github.md](./issue-tracker-github.md) — GitHub issue tracker (includes the GitHub
  Project mapping section)
- [issue-tracker-gitlab.md](./issue-tracker-gitlab.md) — GitLab issue tracker
- [issue-tracker-local.md](./issue-tracker-local.md) — local-markdown issue tracker
- [triage-labels.md](./triage-labels.md) — label mapping
- [domain.md](./domain.md) — domain doc consumer rules + layout

For "other" issue trackers, write `docs/agents/issue-tracker.md` from scratch using the user's
description.

When a Project was configured in Section A.5, fill the `## GitHub Project mapping` section of the
written `docs/agents/issue-tracker.md` with the captured OWNER/NUMBER, project node id, field ids, and
Status option ids. When no Project was configured, leave that section saying "No GitHub Project —
issues only."

### 5. Done

Tell the user the setup is complete and which skills will now read from these files. Mention they can
edit `docs/agents/*.md` directly later — re-running this skill is only necessary if they want to switch
issue trackers, add/remove the Project mapping, or restart from scratch. If a Project mapping was
written, remind them to re-run this skill (or edit the ids) if they ever recreate the Project, since
the node ids change.
