# Engineering Pipeline — a Claude Code plugin

A self-contained Claude Code plugin that packages an engineering workflow as a set of
composable Skills. It gives you a clean 5-step pipeline for taking a piece of work from
"rough idea" to "reviewed, committed code" — plus the supporting disciplines the pipeline
leans on.

The skills stay **modular and composable** on purpose: you drive, the agent assists. Nothing
here tries to own the whole development process.

## Using it on a project

Three phases: install once, configure each repo once, then run the flow whenever you pick up
a piece of work.

**1. Install (one time, machine-wide).** This repo is its own marketplace, so
add it straight from GitHub — the skills then become available in *any* project you open:

```
/plugin marketplace add yogendrasgautam/skills
/plugin install engineering-pipeline@engineering-skills
/plugin install diagram-studio@engineering-skills   # optional
/plugin install software-factory@engineering-skills # optional: hands-off /factory (see software-factory/README.md)
```

**2. Configure a project (one time per repo).** In the target project, run `setup` — it
scaffolds `docs/agents/` (issue tracker, triage labels, domain docs) that the other skills
read, so do it before your first flow:

```
/engineering-pipeline:setup
```

**3. Run the pipeline.** Start with `guide` if you're unsure which entry point fits, then walk
the numbered steps in order:

```
/engineering-pipeline:guide          # routes you to the right step
/engineering-pipeline:wayfinder      # 1  orient  (or :grill-with-docs to stress-test a design)
/engineering-pipeline:to-spec        # 2  conversation → spec on the tracker
/engineering-pipeline:to-tickets     # 3  spec → grabbable tickets
/engineering-pipeline:implement      # 4  build (TDD) → self-review → commit
/engineering-pipeline:code-review    # 5  review the diff: Standards + Spec
```

You drive — pick the step that fits and skip the rest. The supporting disciplines (`tdd`,
`codebase-design`, `domain-modeling`, etc.) fire automatically inside these steps, so you
rarely invoke them by hand. See [Install](#install) and [Project configuration](#project-configuration)
below for the full details.

## The pipeline

```
  0     │  setup               │   configure the repo once (issue tracker, triage labels, docs)
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
  1     │  grill-with-docs     │   sharpen the design (relentless interview + ADRs/glossary)
        │        OR            │
        │  wayfinder           │   get your bearings fast (a map, not a grilling)
        └──────────┬──────────┘
                   ▼
  2     │  to-spec             │   synthesize the conversation into a spec on the tracker
                   ▼
  3     │  to-tickets          │   break the spec into independently-grabbable tickets
                   ▼
  4     │  implement           │   build it (TDD at agreed seams) → self-review → commit
                   ▼
  5     │  code-review         │   two-axis review: Standards + Spec
```

| # | Skill | What it does |
|---|-------|--------------|
| 0 | **setup** | Configures the repo once — issue tracker (GitHub / GitLab / local / other), an optional **GitHub Project** mapping so new tickets land on your board, triage label vocabulary, and domain doc layout. Writes `docs/agents/*.md`. Run before your first flow. |
| — | **guide** | A router over these skills — ask it which skill or flow fits your situation and it maps you to the right entry point. Start here if you're unsure. |
| 1 | **grill-with-docs** | A relentless interview that sharpens a plan/design and captures ADRs + glossary entries as you go. Use when the shape of the work is contested. |
| 1 (alt) | **wayfinder** | The fast front door: orient in an unfamiliar codebase/problem and produce a short "where things live + what to do next" map, then hand off to `to-spec`. Use when you need bearings, not a full grilling. |
| 2 | **to-spec** | Turns the current conversation into a spec and publishes it to the project issue tracker — no interview, just synthesis. |
| 3 | **to-tickets** | Breaks a plan/spec into independently-grabbable tickets using tracer-bullet vertical slices. |
| 4 | **implement** | Implements the work from a spec or tickets, using TDD at agreed seams, then self-reviews and commits. |
| 5 | **code-review** | Reviews the diff since a fixed point along two axes — **Standards** (repo conventions + a Fowler smell baseline) and **Spec** (does it match what was asked?) — in parallel sub-agents. |

### Supporting disciplines (model-invoked)

These are auto-invoked by the pipeline skills when relevant — you rarely call them directly:

- **tdd** — red/green/refactor at real seams (`mocking.md`, `tests.md`).
- **codebase-design** — disciplined module shape and interfaces (`DEEPENING.md`, `DESIGN-IT-TWICE.md`).
- **domain-modeling** — build and sharpen the project's shared vocabulary (`ADR-FORMAT.md`, `CONTEXT-FORMAT.md`).
- **diagnosing-bugs** — structured debugging for intermittent/complex issues.
- **prototype** — throwaway code to answer a design question (`LOGIC.md`, `UI.md`).
- **triage** — move issues through a triage state machine (`AGENT-BRIEF.md`, `OUT-OF-SCOPE.md`).
- **grilling** — the underlying interview discipline used by `grill-with-docs` and `wayfinder`.

### Pipeline-adjacent

- **improve-codebase-architecture** — scan the codebase for "deepening" opportunities, present
  them as a visual HTML report, then grill through whichever one you pick (`HTML-REPORT.md`).

## Architecture

The plugin follows the current Claude Code conventions:

- **Skills, not legacy commands.** Every capability is a Skill in
  `engineering-skills/skills/<name>/SKILL.md`, auto-discovered from that `skills/`
  directory — there is no hand-maintained path list and no duplicate `commands/` wrappers. A skill with `disable-model-invocation: true` is a
  user-invoked step; skills without it can also be auto-invoked by the model.
- **Two tiers.** The numbered pipeline steps are user-invoked; the disciplines are
  model-invoked so they fire automatically at the right moment (e.g. `tdd` during `implement`,
  `grilling`/`domain-modeling` during `grill-with-docs`).
- **One source of truth.** Each step's behavior lives in its `SKILL.md` and nowhere else.

```
.
├── .claude-plugin/
│   └── marketplace.json    # GENERATED catalog — written by CI, never in a PR
├── engineering-skills/     # the engineering-pipeline plugin
│   ├── .claude-plugin/     #   plugin.json + its marketplace-entry.json fragment
│   └── skills/             #   auto-discovered skills (pipeline + disciplines)
├── diagram-studio/         # a second plugin, same shape
├── software-factory/       # /factory orchestrator + role agents (depends on engineering-pipeline)
├── tools/                  # marketplace catalog generator + its tests
├── Makefile                # make check / make marketplace-preview
├── CLAUDE.md               # repo conventions
└── README.md
```

The marketplace catalog is generated from per-plugin
`<plugin>/.claude-plugin/marketplace-entry.json` fragments, and is written only by CI on
`main`. A PR ships the fragment (or the deleted plugin directory) and **never**
`marketplace.json` itself — CI rejects a PR that touches it. Run `make marketplace-preview`
to see what the reconcile will do. See [CLAUDE.md](CLAUDE.md).

## Install

This repo is its own marketplace, holding two plugins: `engineering-pipeline` (the pipeline
and disciplines) and `diagram-studio` (editorial diagrams). Install straight from GitHub:

```
/plugin marketplace add yogendrasgautam/skills
/plugin install engineering-pipeline@engineering-skills
/plugin install diagram-studio@engineering-skills   # optional
/plugin install software-factory@engineering-skills # optional: hands-off /factory (see software-factory/README.md)
```

Then check `/help` — the pipeline skills are invoked namespaced:

```
/engineering-pipeline:setup
/engineering-pipeline:guide
/engineering-pipeline:wayfinder
/engineering-pipeline:to-spec
/engineering-pipeline:to-tickets
/engineering-pipeline:implement
/engineering-pipeline:code-review
/engineering-pipeline:improve-codebase-architecture
```

### Publishing

Once you push this to your own git repo, others can add it as a marketplace directly:

```
/plugin marketplace add <your-owner>/<your-repo>
/plugin install engineering-pipeline@engineering-skills
/plugin install diagram-studio@engineering-skills   # optional
/plugin install software-factory@engineering-skills # optional: hands-off /factory (see software-factory/README.md)
```

(Set `homepage`/`repository` in that plugin's `<plugin>/.claude-plugin/plugin.json` to your repo
URL when you do.)

## Project configuration

Several skills expect your project to describe its issue tracker and triage labels under
`docs/agents/` (e.g. `docs/agents/issue-tracker.md` and a triage-labels doc). Run
**`/engineering-pipeline:setup`** once to scaffold these interactively — it walks you through the
issue tracker choice, triage labels, and domain doc layout, and writes the files (plus an
`## Agent skills` block in `CLAUDE.md`/`AGENTS.md`). If the docs are missing when you invoke a skill,
it will ask you where that information lives before publishing or triaging.

### GitHub Projects

If your tracker is GitHub, `/setup` can also map new issues onto a GitHub **Project** (v2) board:
whenever a skill creates an issue it's added to the Project and its **Status** field is set. This
needs the `project` scope on your `gh` token (`gh auth refresh -s project`); `/setup` records the
Project's node id and field ids in `docs/agents/issue-tracker.md` so `to-tickets` and `triage` follow
the mapping with no further wiring. See the `setup` skill's `github-project.md` for the commands.
