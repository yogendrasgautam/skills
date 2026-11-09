# Team-ready software factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a new plugin, `shared-software-factory`, that lets two or more developers share one factory on a repo, with GitHub as the shared board, race-safe ticket claims, shared history, and a shared dashboard. The existing `software-factory` plugin is not modified.

**Architecture:** The new plugin starts as a copy of `software-factory` (Task 0) and is then changed; every edit below is inside `shared-software-factory/`. The plugin is prompt-driven (`skills/factory/SKILL.md` is the orchestrator). Everything deterministic moves into one small stdlib-only helper, `skills/factory/scripts/factory_team.py` (pure functions + a thin `gh`-calling CLI), unit-tested. `SKILL.md` is then edited to call the helper and follow the new rules. Workflow templates are shipped for the two dashboard modes and installed by `setup`.

**Tech Stack:** Python 3.9-compatible stdlib (`from __future__ import annotations`, `unittest`, no third-party imports), `gh` CLI, GitHub Actions YAML, Markdown prompts.

**Spec:** `docs/superpowers/specs/2026-11-09-team-ready-factory-design.md`

## Global Constraints

- Helper is **stdlib-only**, runs on Python 3.9 and 3.12+; no `tomllib`, no `Path.walk`, no `X | Y` or subscripted builtins outside annotations. Tests use `unittest`, not pytest.
- Job ID format is exactly `<issue-number>-<slug>` (e.g. `123-rate-limiting`); slug is kebab-case, at most 4 words.
- Claim = issue assignee **plus** label `in-progress`; claim is re-read after writing to confirm it was won.
- Factory comment markers are HTML comments: `<!-- factory:spec -->` (existing), `<!-- factory:review round-N -->`, `<!-- factory:build -->`, `<!-- factory:decision -->`.
- The factory still merges by itself once all reviews PASS and the approver writes `APPROVE`; no new human gate. Hard rules 1-3 in `SKILL.md` are unchanged.
- Dashboard mode is `pages` (Enterprise Cloud) or `projects` (Free/Team), chosen at setup; private repo on Free never gets `pages`.
- Every mention of a job, ticket, epic or PR in board data, dashboard, status output, comments and reports is a full `https://github.com/<repo>/issues/<n>` or `/pull/<n>` link.
- **Do not touch anything under `software-factory/`.** The new plugin is a separate directory; its manifest `name` is `shared-software-factory`, version `0.1.0`. Install name: `shared-software-factory@engineering-skills`; command: `/shared-software-factory:factory`; agents are namespaced `shared-software-factory:<name>`.
- Never put `.claude-plugin/marketplace.json` in the change (repo `CLAUDE.md`). Ship `shared-software-factory/.claude-plugin/marketplace-entry.json` (`category` from the vocabulary in `tools/marketplace.py`, plus a catalog `description`); the catalog follows after merge.

## Review Focus

- Two developers claim the same ticket in the same second: after both write, exactly one still sees themselves as the assignee-first claimant and the other backs off. (Task 1)
- Issue has several assignees or an assignee who is not the running user: treated as claimed by someone else, with a link. (Task 1)
- PR closed without merge, or issue closed with a merged PR but labels still `in-progress`: stage derived from PR/issue state, not stale labels. (Task 2)
- Issue has no spec comment or no PR yet: board row still builds, with empty links rather than a crash. (Task 2)
- Two PRs reference one issue: the most recently updated open one wins; the others are listed in `note`. (Task 2)
- `gh` missing, unauthenticated, or `gh api orgs/<o>` returns 403/404 for a non-admin: plan detection returns `ask`, never `pages`. (Task 4)
- Claim older than 3 days with no activity is shown as `stale` in status but never auto-released. (Task 2)

---

## File Structure

| File | Responsibility |
| --- | --- |
| `shared-software-factory/skills/factory/scripts/factory_team.py` (create) | Pure logic: IDs, claims, stage derivation, board rebuild, status render, dashboard-mode detection; CLI wrapper around `gh` |
| `shared-software-factory/tests/test_factory_team.py` (create) | Unit tests for the helper, with a fake `gh` runner |
| `shared-software-factory/skills/factory/SKILL.md` (modify) | Orchestrator rules: IDs, claims, sync, status, shared history, approve/rework from GitHub, links, setup |
| `shared-software-factory/skills/factory/templates/dashboard.html` (modify) | Show issue/PR links, owner, stale badge |
| `shared-software-factory/skills/factory/templates/workflows/factory-dashboard-pages.yml` (create) | Enterprise: rebuild and deploy Pages |
| `shared-software-factory/skills/factory/templates/workflows/factory-dashboard-projects.yml` (create) | Free/Team: sync Projects board cards |
| `shared-software-factory/skills/factory/templates/profile.shared.md` (create) | Committed shared profile (no absolute paths) |
| `shared-software-factory/agents/*.md` (modify) | Replace `skills_dir` absolute-path reads with the injected value |
| `shared-software-factory/` (create, Task 0) | Copy of `software-factory/` as the starting point; nothing in `software-factory/` changes |
| `shared-software-factory/.claude-plugin/plugin.json` (modify), `marketplace-entry.json` (create) | New name, version `0.1.0`, catalog fragment |
| `shared-software-factory/README.md`, `skills/factory/templates/README.md` (modify) | Docs |
| `Makefile` (modify) | `test` also discovers `shared-software-factory/tests` |

---

### Task 0: Create the `shared-software-factory` plugin from a copy

**Files:**
- Create: `shared-software-factory/` (copy of `software-factory/`, excluding any `__pycache__`)
- Modify: `shared-software-factory/.claude-plugin/plugin.json`
- Create: `shared-software-factory/.claude-plugin/marketplace-entry.json`
- Test: `shared-software-factory/tests/test_plugin_identity.py` (create)

**Interfaces:**
- Produces: a plugin whose manifest `name` is `shared-software-factory`, so the command becomes `/shared-software-factory:factory` and agent names become `shared-software-factory:<agent>`. Later tasks assume these names.

- [ ] **Step 1: Write the failing test** `test_plugin_identity.py`:
  - `test_manifest_name_and_version`: `plugin.json` has `name == "shared-software-factory"`, `version == "0.1.0"`.
  - `test_no_stale_plugin_namespace`: no file under `shared-software-factory/` contains the string `software-factory:` that is not preceded by `shared-`, and none contains `software-factory@engineering-skills` without `shared-`.
  - `test_original_plugin_untouched`: `git diff --quiet origin/main -- software-factory/` exits 0 (skipped with a message when `origin/main` is unavailable).
- [ ] **Step 2: Run** `python3 -m unittest discover -s shared-software-factory/tests -p 'test_*.py'` — Expected: FAIL (directory/manifest missing).
- [ ] **Step 3: Copy** `software-factory/` to `shared-software-factory/` (`cp -r`, then delete `__pycache__`). Edit `plugin.json`: `name` → `shared-software-factory`, `version` → `0.1.0`, `description` → one sentence saying it is the team-shared variant of the factory (GitHub-backed board, claims, shared dashboard), keywords gain `team`. Replace every `software-factory:` agent namespace and the install line in `SKILL.md`, agent files and both READMEs with the `shared-` form.
- [ ] **Step 4: Write** `marketplace-entry.json`: `{ "category": "Engineering", "description": "Team-shared software factory: GitHub-backed board, ticket claims and a shared dashboard for several developers." }` (confirm `Engineering` is in the allowed vocabulary in `tools/marketplace.py`).
- [ ] **Step 5: Run** the unittest command and `make marketplace-lint` — Expected: PASS.
- [ ] **Step 6: Commit** `feat(shared-software-factory): create plugin from software-factory copy`

### Task 1: IDs and claims

**Files:**
- Create: `shared-software-factory/skills/factory/scripts/factory_team.py`
- Create: `shared-software-factory/tests/test_factory_team.py`
- Modify: `Makefile` (`test` target: add `$(PYTHON) -m unittest discover -s shared-software-factory/tests -p 'test_*.py'`)

**Interfaces:**
- Produces:
  - `job_id(issue: int, title_or_slug: str) -> str` — `"123-rate-limiting"`; slug lowercased, non-alphanumerics to `-`, collapsed, trimmed, first 4 words.
  - `@dataclass(frozen=True) Claim(state: str, holder: str | None, url: str)` where `state` ∈ `"free" | "mine" | "other"`.
  - `claim_state(issue: dict, me: str) -> Claim` — `issue` is `gh issue view --json number,url,assignees,labels` output.
  - `decide_claim_winner(issue_after_write: dict, me: str) -> bool` — True only if `me` is the **first** assignee in `assignees` and no other assignee exists ahead of it.

- [ ] **Step 1: Write the failing tests** in `test_factory_team.py`
  - `test_job_id_uses_issue_number_and_four_word_slug`: `job_id(123, "Rate limiting on the public API now")` == `"123-rate-limiting-on-the"`.
  - `test_claim_free_when_no_assignee_and_no_label`.
  - `test_claim_mine_when_me_is_sole_assignee`.
  - `test_claim_other_with_multiple_assignees_links_issue`: assignees `[bob, me]` → `state == "other"`, `holder == "bob"`, `url` is the issue URL. (Review Focus)
  - `test_claim_other_when_label_in_progress_but_no_assignee`: holder `None`, state `other`.
  - `test_race_loser_backs_off`: after both write, `assignees == [bob, me]` → `decide_claim_winner(..., "me")` is False, and for `"bob"` True. (Review Focus)
- [ ] **Step 2: Run** `python3 -m unittest discover -s shared-software-factory/tests -p 'test_*.py'` — Expected: FAIL (`ModuleNotFoundError: factory_team`). Tests insert `skills/factory/scripts` onto `sys.path`.
- [ ] **Step 3: Implement** the three functions and `Claim` in `factory_team.py` with `from __future__ import annotations` at the top. Slug: regex `[^a-z0-9]+` → `-`, then `split("-")[:4]`.
- [ ] **Step 4: Run** the same command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(factory): job ids from issue numbers and claim logic`

### Task 2: Rebuild the board from GitHub, render status

**Files:**
- Modify: `shared-software-factory/skills/factory/scripts/factory_team.py`
- Modify: `shared-software-factory/tests/test_factory_team.py`

**Interfaces:**
- Consumes: `job_id`, `claim_state` (Task 1).
- Produces:
  - `derive_stage(issue: dict, pr: dict | None, markers: set[str]) -> str` — returns one of the existing stages `blocked | spec | build | review | approve | pr-open | merged | needs-human`. Rules, first match wins: PR merged → `merged`; label `needs-human-review` → `needs-human`; PR open + label `factory-approved` → `pr-open`; PR open + marker `decision` → `approve`; PR open + marker starting `review` → `review`; PR open → `build`; marker `spec` → `build`; label `in-progress` → `spec`; else `blocked`. A PR closed unmerged is ignored (falls through). An issue that is closed with a merged PR is `merged` regardless of labels.
  - `build_board(repo: str, issues: list[dict], prs: list[dict], comments: dict[int, list[str]], me: str, now: str) -> dict` — returns the `board.json` shape from `SKILL.md` plus per job: `issueUrl`, `prUrl`, `owner` (first assignee or `None`), `stale: bool`. `stale` is True when the job is claimed, not `merged`/`needs-human`, and `updated` is more than 3 days before `now` (ISO-8601 UTC strings). Jobs are every issue labelled `factory` and not `epic`. PR for an issue = open PR whose body contains `#<n>`; with several, most recently updated wins and the rest are named in `note`.
  - `render_status(board: dict, repo: str) -> str` — Markdown table, columns `Job | Stage | Owner | Issue | PR | Note`, issue/PR cells are markdown links, `stale` rows suffixed ` (stale)`; empty `prUrl` renders `—`.
  - `markers_from_comments(bodies: list[str]) -> set[str]` — returns `{"spec", "build", "decision", "review round-1", ...}` from the HTML-comment markers.

- [ ] **Step 1: Write the failing tests**
  - `test_stage_merged_pr_beats_stale_labels` (issue closed, label `in-progress`, PR merged → `merged`). (Review Focus)
  - `test_stage_closed_unmerged_pr_is_ignored`.
  - `test_stage_needs_human_label_wins_over_review_marker`.
  - `test_board_row_without_spec_or_pr_has_empty_links` — `prUrl == ""`, no exception. (Review Focus)
  - `test_two_prs_one_issue_latest_wins_and_noted`. (Review Focus)
  - `test_stale_claim_flagged_not_released` — updated 4 days before `now` → `stale True`, `owner` unchanged. (Review Focus)
  - `test_status_table_has_links`: output contains `[#42](https://github.com/o/r/issues/42)` and `[#57](https://github.com/o/r/pull/57)`.
- [ ] **Step 2: Run** the unittest command — Expected: FAIL (names undefined).
- [ ] **Step 3: Implement** the four functions. Marker regex: `<!--\s*factory:(\S+(?: [^\s>-]+)?)\s*-->`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(factory): rebuild board and status from GitHub state`

### Task 3: CLI wrapper and dashboard output

**Files:**
- Modify: `shared-software-factory/skills/factory/scripts/factory_team.py`
- Modify: `shared-software-factory/tests/test_factory_team.py`
- Modify: `shared-software-factory/skills/factory/templates/dashboard.html`

**Interfaces:**
- Consumes: `build_board`, `render_status` (Task 2).
- Produces:
  - `fetch_state(repo: str, run: Callable[[list[str]], str]) -> tuple[list[dict], list[dict], dict[int, list[str]]]` — calls `gh issue list --label factory --state all --json …`, `gh pr list --state all --json …`, and `gh issue view <n> --json comments` per issue, via the injected `run` (tests pass a fake).
  - CLI: `python3 factory_team.py status|board|dashboard --repo OWNER/NAME [--out DIR] [--me USER]`. `status` prints the table; `board` writes `<out>/board.json`; `dashboard` writes `board.json` + a copy of `dashboard.html` to `<out>`. Exit 1 with a one-line message when `gh` is missing or unauthenticated.

- [ ] **Step 1: Write the failing tests**: `test_fetch_state_uses_injected_runner` (fake runner returns canned JSON; assert the three gh invocations and parsed result); `test_cli_board_writes_valid_json` (tmpdir, fake runner via module-level `RUN` override, file parses with `json.load`); `test_cli_exits_1_when_gh_missing` (runner raises `FileNotFoundError`).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** `fetch_state` and `main(argv)`; default runner is `subprocess.run(..., check=True, capture_output=True, text=True).stdout`.
- [ ] **Step 4: Update `dashboard.html`** (read it first): each card shows the owner, a `stale` badge when `job.stale`, and `issueUrl` / `prUrl` as links. It must still render a board.json without the new fields.
- [ ] **Step 5: Run** — Expected: PASS. Manually run `python3 -m http.server` over a generated `board.json` and confirm links render.
- [ ] **Step 6: Commit** `feat(factory): gh-backed status/board/dashboard CLI`

### Task 4: Dashboard mode detection and workflow templates

**Files:**
- Modify: `shared-software-factory/skills/factory/scripts/factory_team.py`, `shared-software-factory/tests/test_factory_team.py`
- Create: `shared-software-factory/skills/factory/templates/workflows/factory-dashboard-pages.yml`
- Create: `shared-software-factory/skills/factory/templates/workflows/factory-dashboard-projects.yml`

**Interfaces:**
- Produces: `detect_dashboard_mode(plan_name: str | None, private: bool) -> str` — `"pages"` only when `plan_name` lower-cased is `"enterprise"`; `"projects"` when it is `"free"`, `"pro"` or `"team"`; `"ask"` when `plan_name is None` or unrecognised. `private` does not turn `ask` into `pages`. CLI sub-command `mode --repo OWNER/NAME` runs `gh api repos/<repo> --jq .owner.type,.private`, then `gh api orgs/<owner>` or `gh api user` for `.plan.name`, tolerating 403/404 (→ `None`) and prints the mode.

- [ ] **Step 1: Write the failing tests**: `enterprise`→`pages`; `free`, `team`→`projects`; `None` and `"weird"`→`ask`; `test_403_from_org_lookup_gives_ask` via fake runner raising `CalledProcessError`. (Review Focus)
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.
- [ ] **Step 5: Write the Pages workflow**: triggers `issues`, `pull_request`, `issue_comment`, `schedule` (every 15 min); checks out, runs `python3 .factory/factory_team.py dashboard --repo ${{ github.repository }} --out site`, uploads and deploys with `actions/upload-pages-artifact` and `actions/deploy-pages` (pin exact versions at least two weeks old). Note in a header comment that access restriction is configured in repo Settings → Pages.
- [ ] **Step 6: Write the Projects workflow**: same triggers; runs `board`, then moves each job's card by stage using `gh project item-edit` with a `Stage` single-select field. It needs a token with `project` scope in secret `FACTORY_PROJECT_TOKEN` (the default `GITHUB_TOKEN` cannot write Projects v2); header comment says so, and the job exits 0 with a warning when the secret is missing.
- [ ] **Step 7: Validate** both YAML files parse (`python3 -c "import yaml"` is not available — use `ruby -ryaml -e` if present, otherwise review by eye and run `actionlint` if installed).
- [ ] **Step 8: Commit** `feat(factory): dashboard mode detection and workflow templates`

### Task 5: Orchestrator rules in SKILL.md (IDs, claims, sync, status, links)

**Files:**
- Modify: `shared-software-factory/skills/factory/SKILL.md`
- Test: `shared-software-factory/tests/test_skill_rules.py` (create)

**Interfaces:**
- Consumes: CLI from Tasks 1-3 (`${CLAUDE_SKILL_DIR}/scripts/factory_team.py`).

- [ ] **Step 1: Write the failing test** `test_skill_rules.py` that reads `SKILL.md` and asserts: it does not contain `max in` / `factory/jobs/` counter wording; contains `<issue>-<slug>`; contains `/factory status`; contains the text `re-read` in a Claim section; mentions `issueUrl`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Edit `SKILL.md`**:
  - `description`/`argument-hint`: add `status`.
  - `<feature>` (line ~200): job id = `<issue>-<slug>`, so create the GitHub issue **first**; remove the local counter.
  - New **Claim** subsection in `run` step 2: before promoting, run `claim_state`; `other` → skip and print the holder with link; `free` → `gh issue edit --add-assignee @me --add-label in-progress`, re-read with `gh issue view`, and keep only if `decide_claim_winner` is true, otherwise remove own assignee/label and skip.
  - `run` step 1 Sync: replace "board.json is truth" with "run `factory_team.py board` and treat the result as the board; local files hold only caches".
  - Add `### status` command: run `factory_team.py status`, print the table, name stale claims.
  - Report step 5 and Flagging: issue/PR cells are markdown links; flag comment includes the PR link.
  - Epic tick (step 3 Merged): re-read the epic body right before `gh issue edit` and retry once on change.
  - Hard rule 5: GitHub is the board; `factory/` is a per-clone cache.
- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `feat(factory): claims, GitHub-derived board and status in orchestrator`

### Task 6: Shared history and approve/rework from GitHub

**Files:**
- Modify: `shared-software-factory/skills/factory/SKILL.md`, `shared-software-factory/tests/test_skill_rules.py`

- [ ] **Step 1: Extend the test**: assert `SKILL.md` contains each of `<!-- factory:review round-N -->`, `<!-- factory:build -->`, `<!-- factory:decision -->` and a section titled `Rebuilding a job from GitHub`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Edit `SKILL.md`**:
  - After each review round, post one PR comment per reviewer file (first line verdict, link to the PR) with the marker; after the builder returns, post `build.md` as a `build` comment; after the approver, post `decision.md` as a `decision` comment. The orchestrator posts them; agents still write only their local files and agent files are unchanged.
  - **Rebuilding a job from GitHub**: if `approve`/`rework` find no local `factory/jobs/<id>/`, create it from the issue body (`ticket.md`), the `spec` comment (`spec.md`), and the marker comments (`build.md`, `round-N/review-*.md`, `decision.md`); the worktree is created from `origin/factory/<id>`; a fresh `builder-<id>` is spawned with "read build.md".
  - `approve`/`rework` accept the job when `derive_stage` is `needs-human`, `approve`, or `pr-open`, from any clone. Resolve `<id>` by number prefix as well (`/factory approve 123`).
- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `feat(factory): shared review history and cross-clone approve/rework`

### Task 7: Committed setup

**Files:**
- Modify: `shared-software-factory/skills/factory/SKILL.md` (setup section), `shared-software-factory/tests/test_skill_rules.py`
- Create: `shared-software-factory/skills/factory/templates/profile.shared.md`
- Modify: `shared-software-factory/agents/*.md` (each reads `skills_dir`)

- [ ] **Step 1: Extend the test**: `SKILL.md` setup mentions `factory_team.py mode`, `.factory/profile.md`, `FACTORY_PROJECT_TOKEN`; no agent file contains an absolute path example for `skills_dir`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Edit setup** in `SKILL.md`:
  - New step: run `factory_team.py mode`; `ask` → AskUserQuestion (Enterprise Cloud / Team / Free).
  - Ship, in the `factory/setup` PR (flagged for human review, as today): `.claude/settings.json` plugin prompt, `.factory/profile.md` (from `profile.shared.md`: stack, install, test, lint, has_ui, max_parallel, conventions — **no** `skills_dir`), `.factory/factory_team.py` (copy of the helper), and the one workflow matching the mode under `.github/workflows/`.
  - For `projects` mode: create the Project and `Stage` field with `gh project create` / `gh project field-create`, and tell the user to add `FACTORY_PROJECT_TOKEN`.
  - Local `factory/profile.md` is generated from `.factory/profile.md` if present; `skills_dir` is always resolved from `${CLAUDE_SKILL_DIR}/library` at run time and passed to agents in their prompt. Second developer: setup detects `.factory/profile.md` and only creates the local cache and `.git/info/exclude`.
- [ ] **Step 4: Edit each agent file** to say "skills dir is given in your prompt" instead of reading `factory/profile.md` for it (grep `skills_dir` in `shared-software-factory/agents/`).
- [ ] **Step 5: Run** — PASS. **Step 6: Commit** `feat(factory): committed shared setup and per-mode dashboard install`

### Task 8: Docs and final check

**Files:**
- Modify: `shared-software-factory/README.md`, `shared-software-factory/skills/factory/templates/README.md`, `shared-software-factory/.claude-plugin/plugin.json`

- [ ] **Step 1:** Add a "Working as a team" section to both READMEs (claims, `/factory status`, shared dashboard modes, PR-comment history, the token for Projects mode). Leave `plugin.json` version at `0.1.0`.
- [ ] **Step 2:** Run `make check` — Expected: all tests and marketplace lint pass.
- [ ] **Step 3:** Run `make marketplace-preview` — Expected: shows `shared-software-factory` as `added` and no change for `software-factory`; `git diff --stat origin/main` shows **no** `marketplace.json` and **nothing under `software-factory/`**.
- [ ] **Step 4: Dry run** (no real tickets): in a scratch GitHub repo, create two `factory`-labelled issues, run `factory_team.py status --repo <scratch>`, confirm links render; claim one issue as user A, run again with `--me B`, confirm it shows as held by A.
- [ ] **Step 5: Commit** `docs(factory): team workflow for shared-software-factory`

---

## Self-review notes

- Spec §1 → Tasks 1, 2, 5; §2 → Tasks 1, 5; §3 → Task 6; §4 → Tasks 3, 5, 6; §5 → Tasks 2, 3, 5; §6 → Tasks 3, 4, 7; §7 → Task 7. Claim expiry (spec open question) is implemented as a `stale` flag only, pending your decision.
- Known risk: Projects mode needs a `project`-scoped token as a repo secret, because `GITHUB_TOKEN` cannot write Projects v2. This is a small secret, not an external service.
- Unverified until Task 7: which agent files actually read `skills_dir` from `factory/profile.md` versus the prompt.
