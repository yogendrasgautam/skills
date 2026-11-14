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
├── skills/factory/scripts/factory.py  # state machine: only writer of board.json (stdlib, py3.9+)
├── hooks/                          # hooks.json + guard.py: hard rules enforced on Bash calls
├── tests/                          # unittest: state script, guard, skill rules
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
     APPROVE + green CI ─► gh pr merge (squash, pinned to the approved commit)
     doubt · risk paths · no CI ─► PR flagged needs-human-review
     epic's last ticket merged ─► epic check on main (tests + adversary across tickets)
```

## What setup creates in your project (`factory/`)
| Path | What |
|---|---|
| `profile.md` | repo profile (stack, test cmd, conventions, `risk_globs`, `no_ci`, skills dir) — written by setup |
| `board.json` | job state; written only by the state script (`factory.py`), which refuses illegal moves; drives the dashboard |
| `events.jsonl`, `metrics.json` | append-only log of every state change; rounds / cycle time / escalation / flaky rates |
| `run.lock/` | present while a factory run is in progress (one scheduler per repo) |
| `backlog.md` | local mirror of ready tickets for `/factory run` |
| `plans/<slug>/` | `decisions.md` (grilling output) and `plan.md` (planner ticket breakdown) |
| `jobs/<id>/` | `spec.md`, `build.md`, `round-N/tests.txt`, `round-N/review-*.md`, `round-N/ux-test.md` + `evidence/`, `round-N/ci.md`, `decision.md` |
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

## Safety rails
- **State script** (`skills/factory/scripts/factory.py`): the only writer of `board.json`. Stage
  moves are validated (four PASS reviews + green tests before approval, UI jobs can't skip the UX
  test, max review rounds), and reviews → approval → merge are pinned to one commit — anything
  pushed after approval goes back to review.
- **Guard hook** (`hooks/guard.py`, PreToolUse on Bash): for the factory's agents always, and for
  your session while a run is in progress, blocks pushes to `main`, `--force`, `--no-verify`,
  `--admin`, agent-issued merges, merges not pinned with `--match-head-commit`, and conflict
  "resolutions" that pick a side (`--ours`/`--theirs`, `-X ours|theirs`, `rebase --skip`). Outside a
  factory run it does nothing. It is a guardrail, not a sandbox — protect `main` on GitHub too
  (setup checks and tells you).
- **Merge conflicts** go back to the builder, who rebases and resolves by intent (keeps both
  changes, regenerates generated files, logs each file's resolution for the reviewers); the next
  review round is full. `F conflicts` flags a human instead when the conflict is in `risk_globs`
  or the job has conflicted more than twice. The planner chains tickets that edit the same hot spot.
- **Always a human**: diffs touching `risk_globs` (CI config, Dockerfiles, migrations, auth, …
  — edit the list in `profile.md`), and PRs with no CI unless the profile says `no_ci: allow`.
- **Andon cord**: if `main`'s checks go red the factory halts promotions and merges until it is green.
- **Metrics**: `python3 <plugin>/skills/factory/scripts/factory.py metrics` (also on the dashboard).

## Use
```
/software-factory:factory setup                      # scaffold factory/, detect stack
/software-factory:factory plan "Todo app with tags"  # grill → ADRs → epic + ticket issues, then run
/software-factory:factory run                        # run every ready ticket in parallel (next = one)
/software-factory:factory "Add rate limiting"        # grill, then run one feature directly
/software-factory:factory approve 42-rate-limiting    # job id = <issue number>-<slug>
/software-factory:factory rework 42-rate-limiting "use a token bucket"
/software-factory:factory unlock                      # clear a crashed session's run/ux lock
```
Dashboard: `cd factory && python3 -m http.server 8000` → http://localhost:8000/dashboard.html

Builders work in git worktrees (`.worktrees/<id>`, branch `factory/<id>`) and open PRs; nothing reaches `main` except a merged PR (squash, after approval + green CI, pinned to the approved commit). Anything doubtful is left open with the `needs-human-review` label.

UX testing needs, for UI repos: Node (Playwright is installed into `factory/.ux-tools/` by setup),
the dev-server fields setup writes to `profile.md` (`dev_start`, `dev_url`, `dev_port`, …), and
`gh` ≥ 2.99 for inline evidence (`gh pr comment --attach`; older gh falls back to an orphan
`factory-evidence` branch). Login credentials come only from env vars named in `ux_login`.
