# Software Factory — a Claude Code plugin

Hands-off feature delivery. `/shared-software-factory:factory` is the orchestrator; eight role agents do
the work, each following bundled engineering skills (`skills/factory/library/`).

## Install
```
/plugin marketplace add yogendrasgautam/skills
/plugin install shared-software-factory@engineering-skills
```

## Layout
```
shared-software-factory/
├── .claude-plugin/plugin.json      # self-contained, no dependencies
├── skills/factory/SKILL.md         # the orchestrator (loop diagram + commands)
├── skills/factory/templates/       # copied into a project's factory/ by setup
└── agents/                         # planner, spec-writer, builder, reviewer-{security,ux,ui,code}, approver
```

```
grill (you) ─► ADRs + decisions ─► planner ─► GitHub epic + ticket issues (native blocked-by)
                                                   │ independent tickets run in parallel
   ticket ─► spec-writer ─► builder ─► PR ─► [security · ux · ui · code] ─► approver
              (opus)         (opus)           (opus  sonnet sonnet sonnet)   (opus)
                                                   │
                       APPROVE + green CI ─► gh pr merge (squash)   |   doubt ─► PR flagged needs-human-review
```

## What setup creates in your project (`factory/`)
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
/shared-software-factory:factory approve 003-rate-limiting
/shared-software-factory:factory rework 003-rate-limiting "use a token bucket"
```
Dashboard: `cd factory && python3 -m http.server 8000` → http://localhost:8000/dashboard.html

Builders work in git worktrees (`.worktrees/<id>`, branch `factory/<id>`) and open PRs; nothing reaches `main` except a merged PR (squash, after approval + green CI). Anything doubtful is left open with the `needs-human-review` label.
