# Software Factory — a Claude Code plugin

Hands-off feature delivery. `/software-factory:factory` is the orchestrator; nine role agents do
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
└── agents/                         # planner, spec-writer, builder, reviewer-{security,ux,code,adversary}, ux-tester, approver
```

```
grill (you) ─► ADRs + decisions ─► planner ─► GitHub epic + ticket issues (native blocked-by)
                                                   │ independent tickets run in parallel
   ticket ─► spec-writer ─► builder ─► PR ─► [security · ux · code · adversary] ─► ux-tester* ─► approver
              (opus)         (opus)           (opus  sonnet sonnet  opus)         (sonnet)     (opus)
   * UI-impacting jobs only, one at a time: starts the app locally (base + branch), drives it with
     Playwright, posts before/after screenshots + video on the PR, stops the app. CHANGES → builder → full re-review.
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
| `jobs/<id>/` | `spec.md`, `build.md`, `round-N/review-*.md`, `round-N/ux-test.md` + `evidence/`, `decision.md` |
| `ux.lock/`, `.ux-tools/` | single-instance UX-test lock; Playwright + Chromium for the ux-tester |
| `dashboard.html` | visual board (refreshed from the plugin on every setup) |

## Agents → bundled skills (`skills/factory/library/`)
| Agent | Skills |
|---|---|
| (orchestrator) | grilling, grill-with-docs |
| planner | to-tickets, domain-modeling |
| spec-writer | wayfinder, to-spec, domain-modeling |
| builder | implement, tdd, codebase-design, diagnosing-bugs |
| reviewer-security | code-review (diff process) + security checklist |
| reviewer-ux | prototype/UI.md lens + experience & visual checklist |
| reviewer-code | code-review (Standards + Spec), tdd |
| reviewer-adversary | none — reads only spec + diff (not build.md), tries to break each AC with throwaway repro scripts; blockers need a repro |
| ux-tester | Playwright (headless) against the app it starts locally |
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

UX testing needs, for UI repos: Node (Playwright is installed into `factory/.ux-tools/` by setup),
the dev-server fields setup writes to `profile.md` (`dev_start`, `dev_url`, `dev_port`, …), and
`gh` ≥ 2.99 for inline evidence (`gh pr comment --attach`; older gh falls back to an orphan
`factory-evidence` branch). Login credentials come only from env vars named in `ux_login`.
