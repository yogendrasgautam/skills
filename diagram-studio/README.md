# Diagram Studio

A Claude Code plugin that generates clean, editorial technical diagrams from a plain-language description.

It produces a **single-file HTML** (inline SVG + CSS, no build step, exportable to PNG/SVG — fonts load from one Google Fonts request with system fallbacks) by default, or a **Mermaid** code block when you want to embed in a README, wiki, or docs site.

## Diagram types

| Type | Shows |
|---|---|
| **Architecture** | Components of a system and how they connect |
| **Flowchart** | Decision logic with branches and outcomes |
| **Sequence** | Time-ordered messages between participants |
| **State machine** | The states of a thing and what moves it between them |
| **ER / data model** | Entities, their fields, and how they relate |
| **Timeline** | Events positioned along time |
| **Tree** | A parent → children hierarchy |
| **Database schema** | Physical tables, columns, keys, and joins |

## How it works

One skill, `diagrams`, selects the right type and holds the shared design system. Per-type layout rules and the output/export details load only when needed:

```
skills/diagrams/
  SKILL.md                       # selection, principles, workflow, taste check
  references/
    design-system.md             # color tokens, typography, dark mode
    svg-grammar.md               # canvas, node boxes, connectors, zones
    output-and-export.md         # size presets, PNG/SVG export, Mermaid mapping
    architecture.md  flowchart.md  sequence.md  state-machine.md
    er-model.md      timeline.md   tree.md      db-schema.md
  assets/
    example-architecture.html  example-flowchart.html  ...   # one rendered example per type
```

Each type ships a rendered, self-contained `assets/example-<type>.html` — open it in a browser to see the design system realized.

### Animated flow (optional)

For types where direction or ordering is the point (architecture, flowchart, sequence, state machine), the `flow` motion dial animates the 1–2 focal edges with pure, self-contained CSS/SVG — a pulse travelling the request path, marching ants on an async edge, or a staggered message reveal. It always respects `prefers-reduced-motion` and leaves a correct static frame for PNG export.

The `architecture` and `sequence` examples add **play / pause / step** playback controls via a tiny, self-contained inline controller — walk a pulse through the flow one hop at a time. It's failure-safe: with JavaScript disabled or under `prefers-reduced-motion` the controls are hidden and the complete static diagram remains, and a `?step=N` query param can deep-link or export a specific frame. A pure-CSS on/off toggle (no JS) is documented as a lighter alternative. See `skills/diagrams/references/animation.md`.

## Usage

Once the plugin is installed, just ask:

- "Draw an architecture diagram of this service."
- "Make a sequence diagram for the checkout flow."
- "Give me a Mermaid ER diagram for these tables."
- "Flowchart the refund approval logic, for a slide."

The skill infers the output format and size from your request, asks at most one question if something material is ambiguous, and hands back the file path (or the Mermaid block).

## Design

Diagrams follow one quiet editorial skin — bone-white paper, slate ink, a single pine-teal accent — defined entirely as tokens in `design-system.md`. Swap those values to match a brand; the layout logic is untouched. Every diagram reads in both light and dark mode.

## Installation

This plugin lives in the `engineering-skills` marketplace in this repo. Add the marketplace, then install `diagram-studio`.
