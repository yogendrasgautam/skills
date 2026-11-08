# Issue tracker: GitLab

Issues and specs for this repo live as GitLab issues. Use the [`glab`](https://gitlab.com/gitlab-org/cli)
CLI for all operations.

## Conventions

- **Create an issue**: `glab issue create --title "..." --description "..."`. Use a heredoc for
  multi-line descriptions.
- **Read an issue**: `glab issue view <id> --comments`.
- **List issues**: `glab issue list --all` with `--label` and state filters (`--opened` / `--closed`).
- **Comment on an issue**: `glab issue note <id> --message "..."`
- **Apply / remove labels**: `glab issue update <id> --label "..."` / `--unlabel "..."`
- **Close**: `glab issue close <id>`

Infer the project from the git remote — `glab` does this automatically when run inside a clone.

## Merge requests as a triage surface

**MRs as a request surface: no.** _(Set to `yes` if this repo treats external merge requests as
feature requests; `/triage` reads this flag.)_

When set to `yes`, MRs run through the same labels and states as issues, using the `glab mr`
equivalents:

- **Read an MR**: `glab mr view <id> --comments` and `glab mr diff <id>` for the diff.
- **List MRs for triage**: `glab mr list --all`, then keep only those authored by non-members
  (external contributors); leave collaborators' in-flight MRs alone.
- **Comment / label / close**: `glab mr note`, `glab mr update --label`/`--unlabel`, `glab mr close`.

GitLab issues and MRs have separate id spaces (`#42` is an issue, `!42` is an MR).

## When a skill says "publish to the issue tracker"

Create a GitLab issue.

## When a skill says "fetch the relevant ticket"

Run `glab issue view <id> --comments`.
