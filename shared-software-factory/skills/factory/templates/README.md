# Shared Software Factory

A feature goes in; a reviewed, tested branch merged to `main` comes out.
Plugin: `/plugin install shared-software-factory@engineering-skills` (self-contained; the skills the agents use are bundled).

```
grill (you) ─► ADRs + decisions ─► planner ─► GitHub epic + ticket issues (native blocked-by)
                                                   │ independent tickets run in parallel
   ticket ─► spec-writer ─► builder ─► PR ─► [security · ux · ui · code] ─► approver
              (opus)         (opus)           (opus  sonnet sonnet sonnet)   (opus)
                                                   │
                       APPROVE + green CI ─► gh pr merge (squash)   |   doubt ─► PR flagged needs-human-review
```

## This folder
| Path | What |
|---|---|
| `profile.md` | repo profile (stack, test cmd, conventions, skills dir) — written by setup |
| `board.json` | job state; only the orchestrator writes it; drives the dashboard |
| `backlog.md` | local mirror of ready tickets for `/factory run` |
| `plans/<slug>/` | `decisions.md` (grilling output) and `plan.md` (planner ticket breakdown) |
| `jobs/<id>/` | `spec.md`, `build.md`, `round-N/review-*.md`, `decision.md` |
| `dashboard.html` | visual board (refreshed from the plugin on every setup) |

## Agents → bundled skills (`skills/factory/library/`)
| Agent | Skills |
|---|---|
| (orchestrator) | grilling, grill-with-docs |
| planner | to-tickets, domain-modeling |
| spec-writer | wayfinder, to-spec, domain-modeling |
| builder | implement, tdd, codebase-design, diagnosing-bugs |
| reviewer-security | code-review (diff process) + security checklist |
| reviewer-ux / reviewer-ui | prototype/UI.md lens + checklist |
| reviewer-code | code-review (Standards + Spec), tdd |
| approver | codebase-design |

## Use
```
/shared-software-factory:factory setup                      # scaffold factory/, detect stack
/shared-software-factory:factory plan "Todo app with tags"  # grill → ADRs → epic + ticket issues, then run
/shared-software-factory:factory run                        # run every ready ticket in parallel (next = one)
/shared-software-factory:factory "Add rate limiting"        # grill, then run one feature directly
/shared-software-factory:factory approve 42-rate-limiting
/shared-software-factory:factory rework 42-rate-limiting "use a token bucket"
```
Dashboard: `cd factory && python3 -m http.server 8000` → http://localhost:8000/dashboard.html

Builders work in git worktrees (`.worktrees/<id>`, branch `factory/<id>`) and open PRs; nothing reaches `main` except a merged PR (squash, after approval + green CI). Anything doubtful is left open with the `needs-human-review` label.

## Working as a team

Several developers can run the factory against one repo at the same time. GitHub is the board;
there is no shared local state.

- **GitHub is the board.** Issues labelled `factory` are the tickets. Each clone derives its
  `factory/board.json` from GitHub (`factory_team.py board`), so two clones always agree.
- **Job ids** are `<issue>-<slug>` (for example `42-rate-limiting`). The issue number comes from
  GitHub, so two developers can never mint the same id.
- **Claims.** To work a ticket the factory assigns the issue to you and adds `in-progress`, then
  re-reads the issue to confirm it still holds the claim. If someone else won the race it backs off.
  It never drives a job another developer owns.
- **See everything:** `/shared-software-factory:factory status` lists every ticket, who holds it
  and its PR, with links.
- **Approve and rework from any clone** (`/shared-software-factory:factory approve <id>`,
  `/shared-software-factory:factory rework <id> "<note>"`) when the PR targets `main` and has no
  stacked dependents. Otherwise run it from the owner's clone.
- **History lives on the issue.** Review rounds, decisions and approvals are posted as issue
  comments carrying hidden markers, so a fresh clone can rebuild a job's history. Only comments
  whose `authorAssociation` is OWNER, MEMBER or COLLABORATOR are trusted; the rest are ignored.
  Caveat: members of a private organisation whose membership is private can appear as CONTRIBUTOR
  or NONE, and their marker comments would be ignored. Make their membership public, or add them
  as repo collaborators.
- **Shared dashboard**, chosen at setup by GitHub plan:

  | Plan | Mode | What you get |
  |---|---|---|
  | Enterprise Cloud | Pages | a dashboard site; restricting it to repo members is a manual, Enterprise-only setting (Settings -> Pages) |
  | Free / Pro / Team | Projects | a Projects v2 board kept in sync by a workflow |

  When the plan cannot be detected the helper answers `ask`; setup resolves that by asking
  you which plan the repo is on, so a workflow is never installed in mode `ask`.

  Projects mode needs a token: the default `GITHUB_TOKEN` cannot write Projects v2. Create a token
  with the `project` scope, add it with `gh secret set FACTORY_PROJECT_TOKEN`, and set the variable
  `FACTORY_PROJECT_NUMBER` (setup sets the variable). Without the secret the workflow warns and exits 0.
- **Setup has three cases.** *First*: the first developer runs `setup`, which opens a PR with the
  shared config (`.factory/profile.md`, helper, dashboard workflow, optional `.claude/settings.json`).
  *Join*: later developers run `setup` after that PR merges; it only builds their local cache.
  *Refresh*: `setup refresh` re-ships the helper and workflow through a PR after a plugin upgrade.
- **Install:** `/plugin install shared-software-factory@engineering-skills`

## Not yet verified live

The helper and the orchestrator rules are unit-tested against a fake `gh`, but these parts have
not yet been exercised against real GitHub:

- the `gh api ... --paginate --jq` comment lookups (marker dedupe, rebuilding a job) and the
  issue-events lookup behind `claim verify`;
- `gh project field-create` (the `Stage` options) and `gh project item-list` returning
  `content.url` for each card;
- the native dependencies (`issues/<n>/dependencies/blocked_by`) and sub-issues
  (`issues/<epic>/sub_issues`) endpoints;
- the Pages deploy and its access setting (restricting the site to repo members is manual and
  Enterprise-only);
- the `.claude/settings.json` key names (`extraKnownMarketplaces`, `enabledPlugins`);
- the claim-race ordering (earliest `assigned` event wins) under a real simultaneous claim.

Before relying on the factory for a team, a dry run is recommended on a throwaway private repo
with two accounts: setup (first and join), a claim race, a stacked pair of tickets, a flagged PR approved
from the other clone, and one dashboard workflow run.
