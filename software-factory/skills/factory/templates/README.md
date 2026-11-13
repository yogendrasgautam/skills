# Software Factory

A feature goes in; a reviewed, tested branch merged to `main` comes out.
Plugin: `/plugin install software-factory@engineering-skills` (self-contained; the skills the agents use are bundled).

```
grill (you) ─► ADRs + decisions ─► planner ─► GitHub epic + ticket issues (native blocked-by)
                                                   │ independent tickets run in parallel
   ticket ─► spec-writer ─► builder ─► PR ─► [security · ux · code · adversary] ─► ux-tester* ─► approver
              (opus)         (opus)           (opus  sonnet sonnet  opus)         (sonnet)     (opus)
   * UI-impacting jobs only, one at a time: runs the app (base + branch), before/after evidence on the PR
                                                   │
     APPROVE + green CI ─► gh pr merge (squash, pinned to the approved commit)
     doubt · risk paths · no CI ─► PR flagged needs-human-review
     epic's last ticket merged ─► epic check on main (tests + adversary across tickets)
```

## This folder
| Path | What |
|---|---|
| `profile.md` | repo profile (stack, test cmd, conventions, `risk_globs`, `no_ci`, skills dir) — written by setup |
| `board.json` | job state; written only by the state script (`factory.py`), which refuses illegal moves; drives the dashboard |
| `events.jsonl`, `metrics.json` | append-only log of every state change; rounds / cycle time / escalation / flaky rates |
| `run.lock/` | present while a factory run is in progress (one scheduler per repo) |
| `backlog.md` | local mirror of ready tickets for `/factory run` |
| `plans/<slug>/` | `decisions.md` (grilling output) and `plan.md` (planner ticket breakdown) |
| `jobs/<id>/` | `spec.md`, `build.md`, `round-N/tests.txt`, `round-N/review-*.md`, `round-N/ux-test.md` + `evidence/`, `round-N/ci.md`, `decision.md` |
| `ux.lock/` | present while a UX test runs (single instance) |
| `.ux-tools/` | Playwright + Chromium for the ux-tester (installed by setup) |
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
| ux-tester | Playwright (headless) against the locally running app |
| approver | codebase-design |

## Safety rails
- **State script** (`skills/factory/scripts/factory.py`): the only writer of `board.json`. Stage
  moves are validated (four PASS reviews + green tests before approval, UI jobs can't skip the UX
  test, max review rounds), and reviews → approval → merge are pinned to one commit — anything
  pushed after approval goes back to review.
- **Guard hook** (`hooks/guard.py`, PreToolUse on Bash): for the factory's agents always, and for
  your session while a run is in progress, blocks pushes to `main`, `--force`, `--no-verify`,
  `--admin`, agent-issued merges and merges not pinned with `--match-head-commit`. Outside a
  factory run it does nothing. It is a guardrail, not a sandbox — protect `main` on GitHub too
  (setup checks and tells you).
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

Builders work in git worktrees (`.worktrees/<id>`, branch `factory/<id>`) and open PRs; nothing reaches `main` except a merged PR (squash, after approval + green CI). Anything doubtful is left open with the `needs-human-review` label.
