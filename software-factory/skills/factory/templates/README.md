# Software Factory

A feature goes in; a reviewed, tested branch merged to `main` comes out.
Plugin: `/plugin install software-factory@engineering-skills` (self-contained; the skills the agents use are bundled).

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
/software-factory:factory setup                      # scaffold factory/, detect stack
/software-factory:factory plan "Todo app with tags"  # grill → ADRs → epic + ticket issues, then run
/software-factory:factory run                        # run every ready ticket in parallel (next = one)
/software-factory:factory "Add rate limiting"        # grill, then run one feature directly
/software-factory:factory approve 003-rate-limiting
/software-factory:factory rework 003-rate-limiting "use a token bucket"
```
Dashboard: `cd factory && python3 -m http.server 8000` → http://localhost:8000/dashboard.html

Builders work in git worktrees (`.worktrees/<id>`, branch `factory/<id>`) and open PRs; nothing reaches `main` except a merged PR (squash, after approval + green CI). Anything doubtful is left open with the `needs-human-review` label.
