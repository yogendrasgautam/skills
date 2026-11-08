# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line
  bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching
  labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate
  `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests;
`/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr`
equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`,
  or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`,
  `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with
`gh pr view 42` and fall back to `gh issue view 42`.

## GitHub Project mapping

**No GitHub Project — issues only.** _(This section is filled in by `/setup` when the user opts to map
issues onto a GitHub Project (v2) board. When it says the line above, skills create issues only and do
nothing with Projects.)_

When a Project is configured, this section records:

- **Project:** `OWNER / #NUMBER` — `<project URL>`  (OWNER is a **user login** for a personal project
  or an **org login** for an org project)
- **Project node id:** `PVT_xxxxxxxx`
- **Fields (name → id):**
  - `Status` → `PVTSSF_xxx`  (options: `Todo`=`<opt-id>`, `In Progress`=`<opt-id>`, `Done`=`<opt-id>`)
  - _(any other fields to set on creation)_
- **New AFK-ready tickets get:** `Status = Todo` (unless told otherwise)
- **Triage state → Status** (optional, if configured): e.g. `ready-for-agent`/`ready-for-human` →
  `In Progress`, `wontfix` → `Done`

**Prerequisite:** the `gh` token needs the `project` scope. If a `gh project ...` command fails with a
missing-scope error, the user must run `gh auth refresh -s project` in their own terminal (interactive
login).

**After creating an issue**, add it to the Project and set its Status:

```bash
# 1. Add the issue to the project; --format json returns the created item's id.
ITEM_ID=$(gh project item-add NUMBER --owner OWNER --url <ISSUE_URL> --format json --jq '.id')

# 2. Set the Status single-select field (ids from this doc)
gh project item-edit --id "$ITEM_ID" --project-id <PROJECT_NODE_ID> \
  --field-id <STATUS_FIELD_ID> --single-select-option-id <TODO_OPTION_ID>
```

Field-type flags for `item-edit` (use instead of `--single-select-option-id` for non-select fields):
`--text "..."`, `--number 3`, `--date 2026-09-07`, `--iteration-id <id>`, `--clear`.

For how these ids are discovered and refreshed (and the token-scope prerequisite), see the `setup`
skill's `github-project.md` reference, or re-run `/setup`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue. If a Project is configured above, also run the `item-add` + `item-edit` recipe
so the new issue lands on the board with the right Status.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
