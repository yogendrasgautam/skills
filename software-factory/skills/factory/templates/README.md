# Software Factory

A feature goes in; a reviewed, tested branch merged to `main` comes out.
Plugin: `/plugin install software-factory@engineering-skills` (self-contained; the skills the agents use are bundled).

```
[epic → planner → backlog.md]  (optional, /factory plan)
feature → spec-writer → builder ⇄ [security · ux · ui · code] → approver → merge | needs-human
           (opus)        (opus)     (opus  sonnet sonnet sonnet)   (opus)
```

## This folder
| Path | What |
|---|---|
| `profile.md` | repo profile (stack, test cmd, conventions, skills dir) — written by setup |
| `board.json` | job state; only the orchestrator writes it; drives the dashboard |
| `backlog.md` | feature queue for `/factory next` |
| `plans/<slug>.md` | ticket breakdown of an epic (planner) |
| `jobs/<id>/` | `spec.md`, `build.md`, `round-N/review-*.md`, `decision.md` |
| `dashboard.html` | visual board (refreshed from the plugin on every setup) |

## Agents → bundled skills (`skills/factory/library/`)
| Agent | Skills |
|---|---|
| planner | to-tickets, domain-modeling |
| spec-writer | wayfinder, to-spec, domain-modeling |
| builder | implement, tdd, codebase-design, diagnosing-bugs |
| reviewer-security | code-review (diff process) + security checklist |
| reviewer-ux / reviewer-ui | prototype/UI.md lens + checklist |
| reviewer-code | code-review (Standards + Spec), tdd |
| approver | codebase-design |

## Use
```
/software-factory:factory setup                      # scaffold factory/, detect stack
/software-factory:factory plan "Todo app with tags"  # epic → tickets in backlog.md
/software-factory:factory next                       # run first ready backlog item
/software-factory:factory "Add rate limiting"        # run one feature directly
/software-factory:factory approve 003-rate-limiting
/software-factory:factory rework 003-rate-limiting "use a token bucket"
```
Dashboard: `cd factory && python3 -m http.server 8000` → http://localhost:8000/dashboard.html

Builders work in git worktrees (`.worktrees/<id>`, branch `factory/<id>`); `main` stays checked out.
