# Repository conventions

This repo is a Claude Code plugin marketplace. The root holds only the catalog
(`.claude-plugin/marketplace.json`); each plugin lives in its own subdirectory:

- **`engineering-pipeline`** — in `engineering-skills/`, manifest at
  `engineering-skills/.claude-plugin/plugin.json`, skills in
  `engineering-skills/skills/<name>/SKILL.md`.
- **`diagram-studio`** — in `diagram-studio/`, manifest at
  `diagram-studio/.claude-plugin/plugin.json`.

Note the plugin's *name* (`engineering-pipeline`) differs from its *directory*
(`engineering-skills`) and from the *marketplace* name (`engineering-skills`). Installs use
the name, not the directory: `/plugin install engineering-pipeline@engineering-skills`.

## The marketplace catalog is generated — never put `marketplace.json` in a PR

`.claude-plugin/marketplace.json` is a **generated** catalog, and the only thing that writes
it is the `regen` job on `main`, after your PR merges. It is the one file two concurrent
changes would collide on, and hand-editing is what lets it drift from the plugin manifests
(it already had `diagram-studio` pinned at `0.1.0` while its `plugin.json` said `0.1.1`).

**A PR that creates, updates or deletes a plugin must not contain `marketplace.json` at
all.** CI enforces this: a pull request whose diff touches the catalog fails, with one
exception — a PR carrying the `catalog-override` label, for the rare deliberate repair
(a bad generated state, or the `--force-prune` case below).

To **add or update** a plugin's catalog entry, ship a fragment in that plugin's own
directory — `<plugin>/.claude-plugin/marketplace-entry.json`:

```json
{ "category": "Engineering", "description": "<catalog-facing description>" }
```

That is the whole change. Do **not** run `make marketplace`, and do not commit the catalog:
after the merge, `regen` folds the fragment into `marketplace.json`, deletes the fragment,
and pushes a `chore(marketplace): reconcile catalog from fragments [skip ci]` commit. Expect
that bot commit on `main` after any plugin change, and pull before your next push.

`make marketplace-preview` shows exactly what regen will do (`added` / `updated` / `pruned`)
and writes nothing.

`name`, `version` (both from the sibling `plugin.json`) and `source` (the directory path)
are derived automatically. The fragment carries only what cannot be derived: the curated
`category` (Title Case, from the allowed vocabulary in `tools/marketplace.py`) and the
catalog `description`.

**This is enforced, not just advised.** `make marketplace-lint` fails when a plugin
directory holds a `plugin.json` but is described by neither a catalog entry nor a fragment —
the generator cannot invent one, since `category` and `description` are curated, so without
that rule the plugin would be silently missing from the marketplace on green CI. The same
error catches a hand edit that deletes a live plugin's entry.

To **remove** a plugin, delete its directory (or just its `plugin.json`). To
**rename/move** one, move its directory (the fragment moves with it) — the stale entry is
pruned and the name carries over. That is exactly how `engineering-pipeline` moved out of
the repo root into `engineering-skills/`.

Removing the **last** plugin is the one case the pipeline will not do unattended: a reconcile
that would prune every entry (or that finds no plugin manifest anywhere, the signature of a
bad checkout) refuses and exits 1, failing CI with a pointer. If the catalog really should
empty out, run `python3 tools/marketplace.py apply --force-prune` locally and land it with
the `catalog-override` label (or push it straight to `main`).

A plugin's liveness is decided by "does a `plugin.json` still live here", never by "does
this directory exist". The generator still supports a plugin at the repo root
(`source: "./"`), which this repo used to have; the directory check would have made such an
entry permanently unprunable, so moving it out would have collided with its own stale entry.

Because each change only touches files inside its own plugin directory, two changes can
never conflict.

### Commands

- `make marketplace-preview` — **the one to run before pushing.** Prints what the regen job
  will do on `main` (`added` / `updated` / `pruned`) and writes nothing.
- `make marketplace-lint` — validate the fragments, and that every plugin is described.
- `make test` — the tooling's unit tests (`unittest`, no installs needed).
- `make check` — `test` + `marketplace-lint`: what CI runs on a PR, in CI's order.
- `make marketplace` — rewrite the catalog locally. **Repair only** (a bad generated state,
  `--force-prune`); its output does not belong in an ordinary PR.
- `make marketplace-check` — fail if the catalog is not already up to date. For inspecting
  `main` or debugging the generator: a feature branch is *expected* to fail it.
- `make install-hooks` — **optional, per-clone.** Installs a `pre-commit` hook that runs
  `marketplace-lint`, so an undescribed plugin or a broken fragment blocks the commit rather
  than the PR. It only ever fails; it never rewrites files mid-commit. Git hooks are not
  version-controlled, so run this in each clone where you want it.

### CI

One workflow, `.github/workflows/marketplace.yml`, with two jobs:

- **`validate`** runs on PRs and on pushes to `main`: unit tests and fragment lint. On a PR
  it then enforces that the diff does **not** touch `marketplace.json` (skipped by the
  `catalog-override` label). On a push it instead runs the *gate*: a single
  `apply --check --delete-fragments`, which writes nothing and whose exit code decides
  whether `regen` runs at all (`0` nothing to do, `2` reconcile, `1` broken — fail).
- **`regen`** is what actually writes the catalog. It `needs: validate` and runs only on a
  push to `main`, and only when the gate said there is work: it folds each fragment in,
  refreshes derived fields, prunes dead entries, deletes the merged fragments, commits with
  `[skip ci]`, pushes — and then lints and re-checks the reconciled tree. Expect its bot
  commit on `main` after any plugin change, and pull before your next push.

On a PR, `actions/checkout` gives the job `refs/pull/N/merge` — your branch merged into the
base — so `lint` sees **the plugins as your PR leaves them and the catalog as it is on
`main`**. That pairing is what lets a catalog-free PR pass: an added plugin is covered by
its fragment, an updated one by its existing entry, and a deleted one is simply no longer
live.

The gate fires on **either** kind of pending work: a fragment waiting to be folded in and
consumed — the usual case now that PRs never carry the catalog — **or** catalog drift with
no fragment at all — a `version` bumped in a
`plugin.json`, or an entry to prune for a deleted plugin. Plain `apply --check` would miss
the first case: an already-folded fragment leaves the catalog unchanged while regen still
has to consume it. `tools/test_marketplace.py::test_cli_gate_signal_for_ci` pins that
contract.

The jobs are **chained, not parallel**. Regen rewrites a shared file on `main` and pushes
it, so it only runs once the tooling has been shown to work: a green `validate` is that
evidence. If the unit tests or fragment lint are red, regen is skipped and the catalog is
left alone — fix the tooling and push again. Lint runs **again after** the regenerate, this
time against the reconciled tree, and there the `apply --check` is **blocking**: once the
script has run, remaining drift means the generator disagrees with itself.

Only one reconcile happens at a time — the regen job holds a `marketplace-regen`
concurrency group with `cancel-in-progress: false`, so two runs can never rewrite
`marketplace.json` concurrently. GitHub keeps at most one *pending* run per group, which is
safe here: `tools/marketplace-regen.sh` fetches and hard-resets to the live `origin/main` on
each attempt, so the in-flight run already picks up the newer push's fragments.

#### What the pipeline does with each kind of change

No row puts `marketplace.json` in the PR.

| Change | What the PR contains | What happens after the merge |
| --- | --- | --- |
| **Add** a plugin | its directory + `plugin.json` + the fragment | the gate sees the fragment; regen **appends** the entry and deletes the fragment |
| **Add** a plugin with no fragment | `plugin.json` only | the PR fails `lint` — nothing can derive the entry (see the enforced invariant above) |
| **Update** the curated fields | a changed fragment | regen **replaces** that entry in place, order preserved |
| **Update** `version` in a `plugin.json` | the manifest change alone | re-derived on every reconcile; no fragment needed |
| **Update** `description` in a `plugin.json` | the manifest change alone | deliberately *not* copied to the catalog — see "Three descriptions, three jobs" |
| **Delete** a plugin | the removed directory (or just its `plugin.json`) | regen **prunes** its entry. The *last* plugin needs `--force-prune`, above |
| **Edit** `marketplace.json` | — | rejected: the PR fails the catalog guard unless it carries the `catalog-override` label |

### CI prerequisites (one-time repo settings)

The `regen` job pushes to `main`, so it needs:

- **Actions enabled.** If they are not, the workflow silently never appears — no error and
  no signal, while this file promises a backstop that isn't running.
- **Settings → Actions → General → Workflow permissions = "Read and write".** The
  `permissions: contents: write` block on the job can only *narrow* the token, never
  exceed the repository ceiling. With GitHub's read-only default, every regen run gets a 403
  at the push.
- **`main` unprotected.** If you protect it, add a PAT or GitHub App with **Contents: write
  *and* Workflows: write** (the tree contains `.github/workflows/`) as the
  `MARKETPLACE_REGEN_TOKEN` secret. Note that a PAT push *does* re-trigger workflows, unlike
  `GITHUB_TOKEN` — so the `[skip ci]` marker in the reconcile commit becomes load-bearing:
  it stops the reconcile commit from re-running the workflow and, through it, regen itself.

If regen is red with *"Failed to push reconciled catalog"*, check the above before suspecting
a race; the script tells these apart and fails fast on a permissions refusal.

### Three descriptions, three jobs

Don't sync them by hand; they answer different questions:

| Where | Purpose |
| --- | --- |
| `plugin.json` `description` | the full description of the plugin |
| `marketplace-entry.json` `description` | the short, catalog-facing line (what shows in the marketplace) |
| `SKILL.md` `description` | the trigger text Claude matches against to decide to load the skill |

## Tooling constraints

`tools/marketplace.py` is **stdlib-only** and must run on the macOS system interpreter
(Python 3.9) as well as the CI runner's 3.12+. No third-party imports, no `tomllib`, no
`Path.walk`, and no subscripted builtins or `X | Y` outside annotations (the file relies
on `from __future__ import annotations`). Tests are `unittest`, not pytest — pytest is not
installed locally and CI installs nothing.
