# Animation

Motion is **opt-in and static-by-default**. Add it only when *direction of flow* or *order of events* is the point, and only on the 1–2 focal edges — an animated diagram where everything moves is noise, not signal. Everything here is self-contained SVG + CSS: no JavaScript, no libraries.

## Two hard rules

1. **Respect `prefers-reduced-motion`.** Every animation lives inside `@media (prefers-reduced-motion: no-preference)`, and the diagram must be fully correct and legible with all motion removed. Vestibular-sensitive readers, and every PNG/SVG export, see the static frame — so motion may *emphasize* meaning but must never *carry* it.
2. **Focal only.** Animate the same 1–2 elements you'd accent. Motion is a stronger signal than color; spending it on every edge erases it.

## When it applies

| Type | Motion | Idiom |
|---|---|---|
| Architecture | ✅ flow | Comet along the focal request path; marching ants on an async/events edge |
| Data-ish flowchart | ✅ flow / reveal | Draw-on the happy path; pulse the focal terminal |
| Sequence | ✅ reveal | Staggered draw-on of messages top→down (mirrors time); optional comet per message |
| State machine | ➖ optional | Pulse the focal (goal) state; comet along the happy-path transitions |
| Timeline | ➖ optional | Reveal events left→right in time order |
| ER / data model | ❌ | Static relationships — motion adds nothing |
| Database schema | ❌ | Same |
| Tree | ➖ rarely | Draw-on branches as a reveal; usually static |

## Idiom 1 — Comet along an edge (directional flow)

The cleanest "data is flowing this way" cue. Keep the **base edge solid** (so the static frame is complete) and overlay a second copy of the path as a short accent dash that travels along it. Set `pathLength="100"` on the overlay so timing is independent of the actual path length.

```svg
<!-- base edge (already in your diagram) -->
<path id="e1" d="M216,300 H270 Q278,300 278,292 V208 Q278,200 286,200 H340"
      fill="none" stroke="var(--link)" stroke-width="1.2" marker-end="url(#arrow-link)"/>
<!-- comet overlay: a 9-unit dash on a 100-unit path, travelling start→end -->
<path d="M216,300 H270 Q278,300 278,292 V208 Q278,200 286,200 H340"
      fill="none" stroke="var(--accent)" stroke-width="2.6" stroke-linecap="round"
      pathLength="100" stroke-dasharray="9 91" class="flow"/>
```

```css
@media (prefers-reduced-motion: no-preference){
  .flow{ stroke-dashoffset:100; animation:flow 1.8s linear infinite; }
  @keyframes flow{ to{ stroke-dashoffset:0; } }   /* 100→0 travels start→end */
}
@media (prefers-reduced-motion: reduce){ .flow{ display:none; } }  /* base edge remains */
```

- **Direction:** `dashoffset:100 → 0` runs along the path's drawing direction (M-point to end). If it runs backwards, reverse the keyframe (`from{stroke-dashoffset:0} to{stroke-dashoffset:-100}`) rather than re-authoring the path.
- **Staggering a multi-hop path:** give each hop its own `.flow` overlay and add `animation-delay` (e.g. `0s`, `.6s`, `1.2s`) so the pulse hands off hop-to-hop like a packet crossing the system.

## Idiom 2 — Marching ants (continuous async flow)

For an edge that is *already dashed* (optional / async / events), animate its offset so the dashes crawl. Subtle; pair it with idiom 1 on the main path, never as the loudest thing.

```css
@media (prefers-reduced-motion: no-preference){
  .ants{ animation:ants 1s linear infinite; }
  @keyframes ants{ to{ stroke-dashoffset:-14; } }  /* = -(dash+gap), e.g. 4+3 doubled */
}
```
Apply `class="ants"` to the existing dashed `<path>`; its static `stroke-dasharray="4,3"` stays as the reduced-motion frame.

## Idiom 3 — Draw-on reveal (ordering)

Draw an edge in by animating a full-length dash's offset to 0. Stagger delays down a sequence diagram so messages appear in time order, then hold. Best as a **one-shot** (`forwards`), not an infinite loop, so it settles into the correct static diagram.

Set `pathLength="100"` **as an attribute on the `<path>`/`<line>`** (not in CSS — `pathLength` is an SVG attribute and is ignored as a CSS property), so the `100`-unit dash matches the path regardless of its real length:

```svg
<path class="draw" pathLength="100" d="…" fill="none" stroke="var(--accent)"/>
```
```css
@media (prefers-reduced-motion: no-preference){
  .draw{ stroke-dasharray:100; stroke-dashoffset:100;
         animation:draw .5s ease-out forwards; }
  @keyframes draw{ to{ stroke-dashoffset:0; } }
}
```
Give message *n* `style="animation-delay:{n*0.35}s"`. Under reduced motion the messages are simply all present (remove the offset in that branch, or let the class only exist inside the no-preference block and render them static otherwise).

## Idiom 4 — Focal pulse (emphasis, use rarely)

A slow breath on the single focal node. Never on more than one; never faster than ~2s.

```css
@media (prefers-reduced-motion: no-preference){
  .pulse{ animation:pulse 2.4s ease-in-out infinite; transform-box:fill-box; transform-origin:center; }
  @keyframes pulse{ 0%,100%{ opacity:1; } 50%{ opacity:.72; } }
}
```

## One file for static + animated

Prefer a single artifact that is *both* the static and the animated diagram over shipping two files. Two levels of control, chosen by how much the reader needs:

### A. CSS-only on/off toggle (no JavaScript)

Keep the base edges solid and put the comet/reveal overlays behind an in-page checkbox, switched with a pure-CSS `:has()` selector.

```html
<div id="stage"><label><input type="checkbox" id="anim" checked> Animate flow</label> <svg>…<path class="flow" pathLength="100" stroke-dasharray="9 91"/>…</svg></div>
```
```css
.flow{ display:none; }
@media (prefers-reduced-motion: no-preference){
  #stage:has(#anim:checked) .flow{ display:inline; animation:flow 1.9s linear infinite; }
}
@media (prefers-reduced-motion: reduce){ .flow{ display:none !important; } }
```
Zero script; needs a `:has()`-capable browser (Chrome/Edge/Safari 15.4+, Firefox 121+) — older browsers just stay on the static frame. Use this when a simple on/off is enough.

### B. Play / pause / step playback (minimal inline controller)

When the reader should *walk the flow one hop at a time*, add playback controls. This is the only feature that needs script — keep it a tiny, self-contained, **failure-safe** inline controller (no libraries, no fetches, no geometry math, no mutation of the diagram's semantic labels):

- The diagram is a **complete static figure by default.** The controller reveals the controls only by adding `.motion-ready` *after* it binds successfully, inside a `try/catch` — so any error, or JS disabled, leaves the full static diagram with no dead controls.
- **`prefers-reduced-motion: reduce`** → the controller returns immediately: no controls, static frame.
- Each animatable edge carries `data-step="N"`, plus a static **trail** overlay (accent highlight, shown once `step ≥ N`) and a **comet** overlay (`.pf`, animates only on the active step). A step counter and an `aria-live` status keep it accessible.
- Support `?step=N` / `?play=1` query params so a specific frame can be deep-linked or exported to PNG.

The controller is ~40 lines of vanilla JS: hold `cur`/`playing`, `render()` toggles `.active`/`.done` classes and the counter/status, and Play runs a `setInterval` that advances and loops. See the working implementation inline in `assets/example-architecture.html` and `assets/example-sequence.html`.

Pick **A** for a simple ambient on/off, **B** when stepping through the sequence is the point. Both keep a correct static frame for PNG/SVG export and honour reduced-motion.

## Taste additions for animated diagrams

On top of the SKILL.md §6 checklist:

- [ ] All motion is inside `@media (prefers-reduced-motion: no-preference)`; the reduced frame is complete and correct.
- [ ] At most **1–2 animated edges/nodes**; the rest is still.
- [ ] Loops are calm (≥1.5s) and linear/eased — nothing strobing or racing.
- [ ] The **static PNG still tells the whole story** (open it, or throttle to the reduced frame, and check).
- [ ] Motion direction matches the arrowheads.
