# Software Factory — a Claude Code plugin

Hands-off feature delivery. `/software-factory:factory` is the orchestrator; eight role agents do
the work, each following bundled engineering skills (`skills/factory/library/`).

## Install
```
/plugin marketplace add yogendrasgautam/skills
/plugin install software-factory@engineering-skills
```

## Layout
```
software-factory/
├── .claude-plugin/plugin.json      # self-contained, no dependencies
├── skills/factory/SKILL.md         # the orchestrator (loop diagram + commands)
├── skills/factory/templates/       # copied into a project's factory/ by setup
└── agents/                         # planner, spec-writer, builder, reviewer-{security,ux,ui,code}, approver
```

```
[epic → planner → backlog.md]  (optional, /factory plan)
feature → spec-writer → builder ⇄ [security · ux · ui · code] → approver → merge | needs-human
           (opus)        (opus)     (opus  sonnet sonnet sonnet)   (opus)
```

## What setup creates in your project (`factory/`)
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
