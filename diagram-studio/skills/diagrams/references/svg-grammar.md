# SVG grammar

Shared drawing rules for every HTML diagram: the canvas, node boxes, connectors, arrowheads, labels, and zones. Colors come from [`design-system.md`](design-system.md) as `var(--token)`. Type references add layout on top of this grammar; they never override the connector rules.

---

## Canvas

- Use a `viewBox` from the size preset (default `0 0 960 600`); never set pixel `width`/`height` on the `<svg>` — let CSS make it fluid (`svg{width:100%;height:auto}`).
- **Outer margin: 40px on every side.** Nothing but the optional legend strip lives in it. Content must never touch the edge.
- **Snap coordinates to a 4px grid.** Every x, y, width, height divisible by 4. It keeps strokes crisp and spacing even.
- **Z-order, strictly:** background → zones → connectors → nodes → labels. Draw arrows *before* boxes so boxes sit on top of the lines that touch them.

---

## Node box

The default node is a rounded rect with a name, optionally a mono sublabel.

```svg
<g>
  <rect x="80" y="120" width="160" height="56" rx="8"
        fill="var(--paper)" stroke="var(--rule-solid)" stroke-width="1.2"/>
  <text x="160" y="144" text-anchor="middle"
        font-family="Inter,sans-serif" font-size="13" font-weight="600"
        fill="var(--ink)">API Gateway</text>
  <text x="160" y="160" text-anchor="middle"
        font-family="'JetBrains Mono',monospace" font-size="10"
        fill="var(--soft)">:443 · REST</text>
</g>
```

- **Target box:** 160×56 at `doc`; never so small the label crowds the border (≥10px padding). **Hard floor 40px tall.** Compact single-word boxes (a sequence participant header, a small leaf) may go narrower — down to ~120×40 — as long as the label keeps its padding; full component nodes should hold the 160×56 target.
- **Minimum gap between boxes:** 24px (`doc`), 40px (`slide`).
- **Focal node:** swap stroke to `var(--accent)` (width `1.6`) and fill to `var(--accent-tint)`. Max two per diagram.
- **Text baseline:** `y` of a vertically centered single line ≈ box top + height/2 + 4.

---

## Arrowheads

Define markers once in `<defs>`, reuse by `marker-end`. One neutral, one accent, one link.

```svg
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="var(--muted)"/>
  </marker>
  <marker id="arrow-accent" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="var(--accent)"/>
  </marker>
  <marker id="arrow-link" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="var(--link)"/>
  </marker>
</defs>
```

---

## Connectors — mandatory rules

1. **No diagonals.** Every connector is horizontal, vertical, or a rounded right-angle (orthogonal) elbow. A diagonal `<line>` between off-axis nodes is a hard fail.
2. **Straight line** only when endpoints share an x or a y:
   `<line x1=".." y1=".." x2=".." y2=".." stroke="var(--muted)" stroke-width="1.2" marker-end="url(#arrow)"/>`
3. **Elbow** for everything else — two bends, rounded with `r≈8` via quadratic corners. Right-then-down, from `(x1,y1)` to `(x2,y2)` with `mid=(x1+x2)/2`:
   ```svg
   <path d="M x1 y1 H {mid-8} Q {mid} y1 {mid} {y1+8} V {y2-8} Q {mid} y2 {mid+8} y2 H x2"
         fill="none" stroke="var(--muted)" stroke-width="1.2" marker-end="url(#arrow)"/>
   ```
   Flip the vertical signs for right-then-up.
4. **Port selection.** If the target is mostly *above/below* the source, exit the top/bottom edge and enter the target's top/bottom edge (single-bend L-path). Reserve left/right ports for mostly-horizontal travel. An arrow entering a node's side on a vertical path looks like it punctures the face.
5. **Semantic weight via style, not routing.** Optional / async / return / passive flows use `stroke-dasharray="4,3"` and `stroke-width="1"`. Same routing rules apply — the dashes only signal meaning.
6. **API / network calls** use `stroke="var(--link)"` + `marker-end="url(#arrow-link)"`. The one or two focal flows use `var(--accent)` + `url(#arrow-accent)`.

### Crossing — hop the less-important line

When two orthogonal connectors must cross, put a small semicircular hop on the *less* important one; draw the more important one unbroken. Never hop both.

```svg
<!-- horizontal line hopping over a vertical crossing at x=cx, y=y -->
<path d="M x1 y H {cx-8} a 8 8 0 0 1 16 0 H x2"
      fill="none" stroke="var(--muted)" stroke-width="1.2" marker-end="url(#arrow)"/>
```

Bridge the dashed / secondary / write-back line. If you can't route without a tangle, the layout — not the hop count — is wrong: re-flow or split.

---

## Edge labels

Mono, small, on a `paper`-filled mask so the line doesn't strike through the text. Center on the connector's long segment.

```svg
<rect x="{cx-28}" y="{cy-7}" width="56" height="14" rx="2" fill="var(--paper)"/>
<text x="{cx}" y="{cy+3}" text-anchor="middle"
      font-family="'JetBrains Mono',monospace" font-size="9"
      letter-spacing=".05em" fill="var(--muted)">POST /pay</text>
```

---

## Zones (grouping)

Group 2+ nodes of the same tier or boundary. Draw zones *after* the background, *before* connectors.

```svg
<rect x="56" y="88" width="360" height="200" rx="10"
      fill="var(--paper-2)" stroke="var(--rule)" stroke-width="0.8"/>
<rect x="68" y="92" width="66" height="14" rx="2" fill="var(--paper)"/>
<text x="72" y="102" font-family="'JetBrains Mono',monospace" font-size="8"
      letter-spacing=".16em" fill="var(--soft)">FRONTEND</text>
```

Rules: leave 16px between the zone label and the first node; keep zone fill quiet (`paper-2`, not a tint that competes with nodes); **max 3 zones** — more than that and it wants to be a swimlane. For a trust/security boundary use a dashed `var(--rule-solid)` border instead of a fill.

---

## Accessibility

Give the `<svg>` `role="img"` and an `aria-label` that states what it shows. Don't rely on color alone to carry meaning — the dashed/solid distinction and edge labels do that job so the diagram survives grayscale and color-blind readers.
