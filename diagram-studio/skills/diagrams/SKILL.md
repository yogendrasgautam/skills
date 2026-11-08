---
name: diagrams
description: "Generate clean, editorial technical diagrams — architecture, flowchart, sequence, state machine, ER/data model, timeline, tree, and database schema — as self-contained HTML with inline SVG and CSS (exportable to PNG/SVG), or as a Mermaid code block when the user wants to embed in a README, wiki, or docs site. Use when a reader would learn more from a picture than from prose: system overviews, request/response traces, lifecycles, entity relationships, event chronologies, hierarchies, and table schemas."
brand: playlist
function: engineering
version: "0.1.1"
category: Engineering
metadata:
  createdBy: Yogendra.Gautam@playlist.com
---

# Diagrams

Turn a system, process, or data model into a diagram a reader can absorb at a glance.

Eight types. The default deliverable is a **single-file HTML** with inline SVG and CSS — no build step, opens in any browser, exports cleanly to PNG or SVG. Fonts come from one Google Fonts request with system fallbacks, so it stays correct offline (see design-system.md). When the user asks for something to paste into a README, GitHub, Notion, or a wiki, emit a **Mermaid** code block instead.

The shared design system and SVG grammar live in `references/` and apply to every type. Per-type layout rules load only for the type you pick.

---

## 1. Principles

**A diagram earns its place by removing work from the reader, not by adding detail.**

- **One idea per node.** Two boxes that always appear together, travel together, and fail together are one box.
- **Every line must carry information.** If the relationship is already obvious from position, delete the line.
- **The accent is editorial, not a warning light.** Use the one accent color on **1–2 focal elements** per diagram — the thing the reader should look at first. Accent on six nodes is accent on zero.
- **Done is when nothing can be removed,** not when everything has been added.
- **Target density ≈ 4 on a scale of 10.** Complete enough to be correct, sparse enough to need no legend. Past ~9 nodes it is usually two diagrams.

Before drawing, ask yourself: *would a well-written paragraph or a small table serve the reader better?* If yes, write that instead.

---

## 2. When to use (and not)

**Use a diagram for:**

| The reader needs to see… | Type |
|---|---|
| Components of a system and how they connect | **Architecture** |
| Decision logic with branches and outcomes | **Flowchart** |
| Time-ordered messages between participants | **Sequence** |
| The states of a thing and what moves it between them | **State machine** |
| Entities, their fields, and how they relate | **ER / data model** |
| Events positioned along time | **Timeline** |
| A parent → children hierarchy | **Tree** |
| Physical database tables, columns, keys, and joins | **Database schema** |

**Don't use a diagram for:** a short list (use bullets), a simple before/after or a lookup (use a table), or a single shape with a label (write the sentence). A diagram that restates one sentence wastes the reader's attention.

---

## 3. Workflow

1. **Pick the type** from the table in §2. If the request spans two types, pick the one that carries the *primary* meaning and mention the alternative.
2. **Set the output dials** (§4). Infer what's obvious from the request ("for my slide deck" → presentation size); ask only if something material is genuinely ambiguous — and when you do, ask with the **question widget** (§3.1), not a wall of prose; otherwise use the defaults and state which you used.
3. **Load the references you need**, in this order:
   - [`references/design-system.md`](references/design-system.md) — colors, typography, dark mode. (Always.)
   - [`references/svg-grammar.md`](references/svg-grammar.md) — canvas, node boxes, connectors, arrowheads, labels, zones. (Always, for HTML output.)
   - `references/<type>.md` — the layout rules for the chosen type (see §5).
   - [`references/output-and-export.md`](references/output-and-export.md) — size presets, PNG/SVG export, and the **Mermaid** mapping. (When exporting or emitting Mermaid.)
4. **Draft the diagram**, holding the principles in §1 and the connector rules in the grammar reference.
5. **Run the taste check** (§6) before you hand it over. Fix anything that fails; don't ship around it.

### 3.1 Asking with the question widget

Default to inferring and drawing — most requests carry enough to pick sensible dials. Ask **only** when a choice is genuinely ambiguous *and* would change what you draw (redrawing to switch it is expensive). When you must ask, use the **`AskUserQuestion` widget** so the user taps a choice instead of typing:

- **One widget call, one or two questions max.** Each ambiguous dial becomes one question; its `§4` values become the options. Never open a widget to ask something you could infer, or that doesn't change the output.
- **Put the recommended default first**, suffixed `(Recommended)`, so a quick tap keeps moving. Keep each `header` ≤ 12 chars (e.g. `Format`, `Size`, `Detail`).
- **The single highest-value question is Format** (`html` vs `mermaid`) when the destination isn't stated — it splits into two different deliverables. If they've said "for my README/Notion/wiki," don't ask; emit Mermaid. If they've said "for a slide/post," don't ask; pick the size.
- **Don't stack the whole panel.** Asking Format + Size at once is fine; interrogating all five dials is worse than picking defaults and stating them. If nothing is ambiguous, skip the widget entirely and note the dials you used when you hand off (§7).

Example — destination unstated, one crisp question:

> **Format** — *Where will this live?* → `Styled HTML file (Recommended)` · `Mermaid block for Markdown/wiki`

---

## 4. Output dials

Five independent choices decide the deliverable. Set them before drawing — changing them later means redrawing.

| Dial | Question | Default |
|---|---|---|
| **Format** | Where does this land? | `html` (also `svg`, `png`, or `mermaid`) |
| **Size** | How big is the canvas / how far the reader? | `doc` (960×600) |
| **Detail** | Every element, or the ones that carry the story? | `balanced` (≤12 nodes) |
| **Audience** | How technical is the wording? | `mixed` |
| **Motion** | Animate the flow, or hold still? | `static` (also `flow`) |

- **Format** — `html` is the source of truth; `svg`/`png` are produced *from* it (see output-and-export.md). Choose `mermaid` when the user wants to embed in Markdown/wiki and is willing to trade styling control for portability.
- **Size** — `doc` for posts/READMEs, `wide` (1280×720) for full-width docs, `slide` (1280×720, larger type) for decks, `social` (1200×630) for link cards. Full table in output-and-export.md.
- **Detail** — `simplified` (≤7 nodes, capabilities only), `balanced` (≤12, the story-carrying components), `faithful` (every element, **zones mandatory** above 9 nodes).
- **Audience** — `business` (plain names, no jargon), `mixed` (names + a technical sublabel on key nodes), `technical` (protocols, types, versions on sublabels).
- **Motion** — `static` is the default and the right choice for most diagrams. Choose `flow` only when *direction of flow* or *order of events* is the point (architecture, flowchart, sequence, state machine); it animates the 1–2 focal edges with self-contained CSS/SVG, disables itself under `prefers-reduced-motion`, and always leaves a correct static frame for PNG export. Load [`references/animation.md`](references/animation.md) before adding any motion.

---

## 5. Type references

Load exactly one per diagram:

| Type | Reference |
|---|---|
| Architecture | [`references/architecture.md`](references/architecture.md) |
| Flowchart | [`references/flowchart.md`](references/flowchart.md) |
| Sequence | [`references/sequence.md`](references/sequence.md) |
| State machine | [`references/state-machine.md`](references/state-machine.md) |
| ER / data model | [`references/er-model.md`](references/er-model.md) |
| Timeline | [`references/timeline.md`](references/timeline.md) |
| Tree | [`references/tree.md`](references/tree.md) |
| Database schema | [`references/db-schema.md`](references/db-schema.md) |

A rendered, self-contained example of each type lives in [`assets/`](assets/) (`example-<type>.html`) — open one in a browser to see the grammar realized, and use it as the visual target. The architecture and sequence examples carry **play / pause / step** playback controls (a small, failure-safe inline controller) so one file is both the static and the animated reference — step a pulse through the flow, or leave it static; see [`references/animation.md`](references/animation.md).

---

## 6. Taste check (before handing over)

Run every item. A "no" means fix it, not ship it.

- [ ] **One primary flow direction** (left→right or top→down), held consistently.
- [ ] **Accent on 1–2 elements only.** Everything else is ink / muted.
- [ ] **No diagonal connectors.** Every line is horizontal, vertical, or an orthogonal (right-angle, rounded) elbow. Diagonals are a hard fail.
- [ ] **No crossing lines left ambiguous** — the less-important line hops/bridges at a crossing, or the layout is changed to avoid it.
- [ ] **Every node is a distinct idea;** no two that always travel together.
- [ ] **Nothing touches the canvas edge** — the outer margin is intact.
- [ ] **Labels are legible** at the chosen size; no overlap, no text outside its box.
- [ ] **Reads in both light and dark** (tokens, not hard-coded hex — see design-system.md).
- [ ] **Density ≤ ~9 nodes,** or it's zoned (faithful) or split into two diagrams.
- [ ] **A paragraph would not have been better.**

---

## 7. Handing it over

Save HTML to a sensible path (the user's working dir, or alongside the source it documents). Name it for its subject: `payments-architecture.html`, not `diagram.html`. Tell the user the path, the type and dials you used, and how to export to PNG/SVG if they want it (point to output-and-export.md). For Mermaid output, print the fenced block directly in the reply so they can copy it.
