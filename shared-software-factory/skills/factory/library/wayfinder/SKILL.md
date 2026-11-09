---
name: wayfinder
description: Orient fast in an unfamiliar codebase or problem — produce a short "where things live and what to do next" map, then hand off to the to-spec step. A lighter-weight alternative to a full grilling when you need bearings.
---

# Wayfinder

The fast front door to the pipeline. Use wayfinder when you need **bearings** — you're new to this codebase or problem and want a map before committing to a plan. If the shape of the work is contested, it needs a relentless interview instead.

Wayfinder orients; it does NOT design. Keep it short. Do not write production code here.

## Process

### 1. Frame the destination

State, in one or two sentences, what the user is trying to achieve. If it's genuinely unclear, ask ONE focused question — no more. Wayfinder is for finding your feet, not interrogation.

### 2. Scout the terrain

Explore the codebase with the `Agent` tool (fan out — don't read everything yourself). Anchor on the project's shared vocabulary: use the domain glossary and any ADRs, and lean on `/domain-modeling` if the vocabulary is thin. You're looking for:

- **Where things live** — the modules/seams the work will touch, named in domain terms (not "component"/"service").
- **What's already there** — existing utilities, patterns, and prior art to reuse instead of rebuilding.
- **The nearest seam** — the highest existing integration point the work could be tested at.
- **Unknowns** — the questions whose answers would change the approach.
- **External unknowns** — unknowns the repo can't answer: third-party library/API behavior, standards, how others solved it. Name them; don't research them here.

### 3. Draw the map

Report a short, scannable map — aim for well under a page:

- **Goal** — the destination in one line.
- **Lay of the land** — the 3–6 places the work touches, in domain vocabulary, with a one-line "why it matters" each.
- **Reuse** — existing code/patterns to build on.
- **Suggested seam** — where you'd test this, and why.
- **Open questions** — the unknowns worth resolving before writing a spec.

### 4. Choose the next step

Offer the fork:

- An open question hinges on outside facts → research it externally first, then come back to this fork.
- Bearings are enough → hand off to **to-spec** (`../to-spec/SKILL.md`) to synthesize a spec from what you now know.
- The approach is still contested → escalate to a full grilling that also captures ADRs and glossary entries.
