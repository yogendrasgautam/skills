---
name: guide
description: Ask which skill or flow fits your situation. A router over the engineering-pipeline skills in this repo.
disable-model-invocation: true
---

# Guide

You don't remember every skill, so ask. `/guide` maps the situation you're in to the right skill or
flow.

A **flow** is a path through the skills. Most paths run along one **main flow**, and a couple of
**on-ramps** merge onto it. Everything else is standalone, or a vocabulary layer that runs underneath.

## The main flow: idea → ship

The route most work travels. You have an idea and want it built.

1. **Front door — get your bearings, or sharpen the design.**
   - **`/wayfinder`** — the fast front door. Use when you need a *map*: you're new to this
     codebase/problem and want "where things live + what to do next" before committing to a plan. It
     orients, then hands off to `/to-spec`.
   - **`/grill-with-docs`** — use instead when the *shape of the work is contested* and needs a
     relentless interview. It's stateful: it captures decisions as ADRs and glossary entries in
     `CONTEXT.md` as it goes. (It runs the `/grilling` primitive underneath and drives
     `/domain-modeling`.)
2. **Branch — can you settle every question in conversation?** If a question needs a runnable answer
   (a state model, business logic, a UI you have to see), detour through **`/prototype`** — throwaway
   code that answers one design question — then bring the decision back into the idea thread. If a
   question needs facts from *outside* the repo (library/API docs, standards, how others solved it),
   detour through **`/research`** instead — a short, cited brief whose sources later land in the spec.
3. **Synthesize → split → build.**
   - **`/to-spec`** — turn the current conversation into a spec and publish it to the issue tracker
     (no interview, just synthesis).
   - **`/to-tickets`** — break the spec into independently-grabbable tickets using tracer-bullet
     vertical slices. Because the tickets are independent, **clear context between each one**: start a
     fresh session per ticket for the build step.
   - **`/implement`** — build each ticket. It drives **`/tdd`** internally (red-green-refactor at real
     seams), then closes out by running **`/code-review`** before committing.

Reach for **`/tdd`** on its own when you just want to build a concrete behavior test-first without a
full spec, and **`/code-review`** on its own whenever you want to review a branch or PR against a fixed
point (two axes: Standards + Spec).

### Context hygiene

Keep the front-door → `/to-tickets` steps in **one unbroken context window** so the grilling, spec, and
tickets all build on the same thinking. Each `/implement` then starts fresh, working from the ticket.

## On-ramps

A starting situation that generates work, then merges onto the main flow.

- **Bugs and requests piling up** → **`/triage`**. It moves issues (and external PRs, if your tracker
  config treats them as a request surface) through triage roles and produces agent-ready tickets, which
  **`/implement`** later picks up. Triage is only for issues **you didn't create** — raw bug reports and
  incoming requests. Tickets that `/to-tickets` produced are already agent-ready, so **don't triage
  them**.
- **Something's broken** → **`/diagnosing-bugs`**. For the hard ones: the bug that resists a first
  glance, the intermittent flake, the regression between two known-good states. It refuses to theorise
  until it has a tight feedback loop (one command that already goes red on *this* bug), then fixes with
  a regression test. Its post-mortem hands off to **`/improve-codebase-architecture`** when the real
  finding is that there's no good seam to lock the bug down.

## Codebase health

Not feature work — upkeep.

- **`/improve-codebase-architecture`** — run whenever you have a spare moment to keep the codebase good
  for agents to operate in. It surfaces **deepening opportunities** as a visual HTML report; picking one
  *generates an idea* you can take into the main flow at the front door. It's the survey that finds the
  candidates; **`/codebase-design`** (below) is the bench you design the chosen one on.

## Vocabulary underneath

Two model-invoked references that run *beneath* the other skills — each the single source of truth for
its vocabulary. Reach for them directly when the **words**, not the process, are the problem; or let the
skills above pull them in.

- **`/domain-modeling`** — sharpen the project's *domain* language: challenge a fuzzy term, resolve an
  overloaded word ("account" doing three jobs), record a hard-to-reverse decision as an ADR. It's the
  active discipline `/grill-with-docs` drives to keep `CONTEXT.md` a clean glossary.
- **`/codebase-design`** — the deep-module vocabulary (module, interface, depth, seam, adapter,
  leverage, locality) for designing a module's *shape*: a lot of behavior behind a small interface at a
  clean seam. `/tdd` and `/improve-codebase-architecture` both speak it.

## Standalone

- **`/prototype`** — a small, throwaway program that answers one design question: does this state model
  feel right, or what should this UI look like. Throwaway from day one — keep the answer, delete the
  code. It's the detour in step 2 of the main flow, but reach for it any time a design question is hard
  to settle on paper.
- **`/research`** — answers a question with facts from outside the repo: library/API docs for the
  pinned version, standards, prior art in other projects, every claim cited. It fans out to parallel
  source lanes (docs, prior art, ecosystem) and has a verifier check every citation before reporting. It's the other detour in
  step 2 of the main flow — `/prototype` when the answer needs running code, `/research` when it needs
  outside facts — and Claude can pull it in mid-grill or mid-implement on its own.
- **`/grilling`** — the underlying relentless-interview discipline used by `/wayfinder` and
  `/grill-with-docs`. Usually pulled in for you; reach for it directly to stress-test any plan.

## Precondition

**`/setup`** — run once before your first flow to configure the issue tracker, triage labels, and
domain doc layout the other skills assume. It also sets up an optional **GitHub Project** mapping, so
new tickets land on your board with the right Status. Custom issue trackers (Jira, Linear, …) also
work — you describe the workflow and it's recorded.
