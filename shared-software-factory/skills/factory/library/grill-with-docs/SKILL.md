---
name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADRs and glossary) as we go. The factory orchestrator runs this before any spec or ticket is written.
---

Run a `grilling` session (see `../grilling/SKILL.md`), using the `domain-modeling` skill
(`../domain-modeling/SKILL.md`). This is interactive: **only the orchestrator session runs it**,
because the agents (planner, spec-writer, builder, …) cannot ask the user anything.

The goal is that **no open question survives into a spec**. Keep grilling until every branch of
the design tree is resolved or explicitly parked as out of scope.

## Capture as you go
- **Decisions** → `factory/plans/<slug>/decisions.md` (create the folder). One entry per resolved
  question, in the order resolved:
  ```
  ## D<n>: <question, as a short title>
  Decision: <what was decided>
  Why: <one or two lines>
  Affects: <tickets / areas, if known>
  ```
  End the file with `## Out of scope` and `## Parked` (questions deferred, each with a reason).
- **ADRs** → `docs/adr/NNNN-slug.md`, only for decisions that pass the three tests in
  `../domain-modeling/ADR-FORMAT.md` (hard to reverse, surprising, real trade-off). Link each
  ADR from the decision that produced it (`ADR: docs/adr/0007-….md`). ADRs are committed to the
  repo (they ride in the planning PR — see the orchestrator's `plan` command).
- **Terminology** → `CONTEXT.md` glossary, per `../domain-modeling/CONTEXT-FORMAT.md`.

## Rules
- One question at a time, each with your recommended answer.
- Explore the codebase before asking anything the code can answer. Research (web) before asking
  anything that depends on outside facts.
- When the user says "you decide", record your pick as a decision and mark it `(agent's call)`.
- Finish by reading the decisions back as a short list and asking the user to confirm. Only then
  hand off to planning / spec-writing.
