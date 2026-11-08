# Design system

The single source of truth for color and type. Every diagram draws from these tokens — never inline a raw hex value in a type reference or in the SVG logic. Change a token here and every diagram inherits it.

The default skin is a warm, quiet editorial palette: bone-white paper, slate ink, and one pine-teal accent. It is meant to look finished out of the box. To match a brand, swap the token *values* below; leave the token *roles* and all type logic untouched.

---

## Color tokens

Refer to every color by its **role**, never its hex. Type references say `accent`, not `#0f766e`.

| Role | Purpose | Light | Dark |
|---|---|---|---|
| `paper` | Page background, default node fill | `#fbfaf8` | `#1a1d23` |
| `paper-2` | Container / zone fill, secondary surface | `#f1efea` | `#23272f` |
| `ink` | Primary text, primary stroke | `#23262d` | `#eceef1` |
| `muted` | Secondary text, default arrow stroke | `#5a616e` | `#aeb4bf` |
| `soft` | Sublabels, boundary labels, tertiary | `#8a919d` | `#7b828e` |
| `rule` | Hairline borders | `rgba(35,38,45,0.12)` | `rgba(236,238,241,0.12)` |
| `rule-solid` | Stronger borders, baselines | `#cfd2d6` | `rgba(236,238,241,0.22)` |
| `accent` | Focal element — 1–2 per diagram, max | `#0f766e` | `#2dd4bf` |
| `accent-tint` | Fill behind an accent-bordered box | `rgba(15,118,110,0.10)` | `rgba(45,212,191,0.12)` |
| `link` | API/HTTP calls, external or network arrows | `#2563eb` | `#6ea0f0` |
| `danger` | Error transitions, failure paths (use sparingly) | `#b4432f` | `#e07a63` |

**Dark-mode inversion rule.** Any `rgba(35,38,45,X)` in light becomes `rgba(236,238,241,X)` in dark at the same opacity — just flip the RGB. Emit both in CSS via `prefers-color-scheme` (below) so one file serves both themes.

**Series palette** — only for a type that genuinely must distinguish several overlapping entities (rare here). The 1-accent rule still holds: `accent` is the focal series, these cover the rest. Strokes at full color, fills at `0.16` opacity.

| Token | Light | Dark |
|---|---|---|
| `series-1` | `#6b8f71` (sage) | `#8fb095` |
| `series-2` | `#5a7a9b` (dusty blue) | `#85a4c4` |
| `series-3` | `#b08a4f` (ochre) | `#cfa873` |
| `series-4` | `#8a6a9c` (muted violet) | `#a98cbb` |

Don't introduce these in architecture, flowchart, etc. — those stay monochrome ink + one accent.

---

## Typography

| Role | Family | Size (doc) | Weight | Use |
|---|---|---|---|---|
| `title` | Fraunces (serif) | 28px | 400 | Page H1 above the diagram |
| `node` | Inter (sans) | 13px | 600 | Human-readable node / box labels |
| `sublabel` | JetBrains Mono | 10px | 400 | Port, protocol, type, field, URL |
| `eyebrow` | JetBrains Mono | 8px | 500, tracked `0.16em`, UPPERCASE | Zone tags, axis labels, type chips |
| `edge` | JetBrains Mono | 9px | 400, tracked `0.05em` | Arrow / transition labels |
| `body` | Inter | 13px | 400 | Summary caption below the diagram |

Scale the ramp up for `slide` size (title 40 / node 16 / sublabel 12) — see output-and-export.md. Resist letting labels shrink as the canvas grows; fewer nodes beats smaller type.

### Fonts

Load from Google Fonts in the HTML `<head>` so the file is still self-contained in spirit (one CDN request) and renders identically everywhere:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

Always give a real fallback stack so the diagram survives offline: `'Inter', system-ui, sans-serif`, `'JetBrains Mono', ui-monospace, monospace`, `'Fraunces', Georgia, serif`. For a fully offline PNG export, fonts are already baked into pixels — see output-and-export.md.

---

## CSS scaffold

Put tokens on `:root` as custom properties and redefine them under `prefers-color-scheme: dark`. The SVG then references `var(--ink)` etc., and one file serves both themes.

```html
<style>
  :root{
    --paper:#fbfaf8; --paper-2:#f1efea; --ink:#23262d; --muted:#5a616e;
    --soft:#8a919d; --rule:rgba(35,38,45,0.12); --rule-solid:#cfd2d6;
    --accent:#0f766e; --accent-tint:rgba(15,118,110,0.10);
    --link:#2563eb; --danger:#b4432f;
  }
  @media (prefers-color-scheme: dark){
    :root{
      --paper:#1a1d23; --paper-2:#23272f; --ink:#eceef1; --muted:#aeb4bf;
      --soft:#7b828e; --rule:rgba(236,238,241,0.12); --rule-solid:rgba(236,238,241,0.22);
      --accent:#2dd4bf; --accent-tint:rgba(45,212,191,0.12);
      --link:#6ea0f0; --danger:#e07a63;
    }
  }
  body{margin:0;background:var(--paper);color:var(--ink);
       font-family:'Inter',system-ui,sans-serif;}
  .wrap{max-width:1040px;margin:0 auto;padding:40px 24px;}
  h1{font-family:'Fraunces',Georgia,serif;font-weight:400;font-size:28px;margin:0 0 4px;}
  .eyebrow{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:8px;
           letter-spacing:.16em;text-transform:uppercase;color:var(--soft);}
  svg{width:100%;height:auto;display:block;}
  .caption{color:var(--muted);font-size:13px;margin-top:16px;max-width:62ch;}
</style>
```

Inside the SVG, set `fill`/`stroke` to `var(--ink)`, `var(--accent)`, etc. so both themes work from one markup.

---

## Page shell

Wrap the SVG in a small editorial frame — an eyebrow, a title, the diagram, and a one-line caption. Keep chrome minimal; the diagram is the content.

```html
<body>
  <div class="wrap">
    <div class="eyebrow">ARCHITECTURE</div>
    <h1>Payments service</h1>
    <svg viewBox="0 0 960 600" role="img" aria-label="Payments service architecture">…</svg>
    <p class="caption">One-sentence takeaway — what the reader should leave knowing.</p>
  </div>
</body>
```
