---
name: architecture-figures
description: >
  Matplotlib primitives for hand-authored architecture, methods, pipeline,
  and lifecycle figures in a flat publication-grade style. Ships
  `pavlab_arch.primitives` — boxes (stage_box for LLM vs deterministic
  styling, dual_stage_box, stack_box, oval, circle, cylinder, container,
  and card — a modern rounded card with a soft drop shadow), arrows
  (lane_arrow, labeled_arrow, arrow), perf_gauge, Gantt primitives
  (gantt_bar, today_line, variance overlays, two-tier diff), legend_block,
  ensemble_proposer, and fit_text — plus two palettes (the flat ACCENT
  default and the modern CARD_* card palette), canonical 16:9 / 1:1 / 3:1
  layouts, grid_columns helper, and apply_rcparams() for Helvetica +
  editable-SVG defaults. Use when diagramming pipeline architectures,
  workflow lifecycles, LLM vs deterministic stages, or surfacing a metric
  (F1, accuracy) as a bar gauge.
---

# architecture-figures

Matplotlib helpers for hand-authored architecture / methods /
pipeline / lifecycle figures. Every default in here corresponds
to a correction or hard-won lesson from real figure iterations.

## When to use

When asked to make a figure that:

- compares pipeline architectures side-by-side (rows = methods,
  columns = stages)
- shows what each building block of a pipeline does (per-stage
  primer / "lego blocks" view)
- contrasts LLM stages with deterministic / rule-based stages
- reports a quantitative metric (F1, accuracy, recall) across
  rows where the reader needs to compare values at a glance
- diagrams a workflow lifecycle / state machine with feedback
  loops and parallel tracks (see `Lifecycle state diagrams`
  below)
- diagrams a network / pathway / state-machine with **labeled
  arrows** (`labeled_arrow` — see the labeled-edges section)
- shows a **schedule / roadmap** as a Gantt chart with status-
  encoded bars (`gantt_bar`, `today_line`, `GanttTask` — see the
  Gantt charts section)
- shows a **software / hardware stack** as horizontal tier bands
  (Client / Frontend / Services / Storage) with components in each
  tier connected by labeled wire-protocol arrows (see Software stack
  diagrams below)

Read this SKILL.md and `python/pavlab_arch/primitives.py` before
writing any matplotlib code for these tasks. Reuse the helpers —
don't re-invent `_box`, `_arrow`, `_perf_gauge`, etc.

## Why this skill exists

Hand-authored architecture figures are visually fragile. Repeated
iteration cycles hit the same issues:

- boxes too loose around their text → tighter padding via
  per-column widths (and now `fit_text()` auto-shrinks overflowing
  labels)
- redundant text labels duplicating what the diagram shows →
  drop them
- thin spindly arrows → thick `mut=14+` arrows
- blue dominating green at equal F1 → luminosity-balanced palette
  (`BAR_FACTOR` + `BAR_TAG`)
- model names as legend labels → reframe around approaches
- ensemble shown as one merged box → render as parallel mini-boxes
- gear icons distinguish "machinery" (deterministic) from "mushy"
  (LLM) at a glance
- ad-hoc figure sizes drift → use the three canonical shapes
  in `pavlab_arch.layout.FIGSIZES`

The skill encodes these as defaults so the next figure starts
in the right place.

## Setup

```bash
cd skills/architecture-figures
# Standard library + matplotlib only. No special install.
```

The package imports as `pavlab_arch.primitives` /
`pavlab_arch.style` / `pavlab_arch.palette` / `pavlab_arch.layout`
from any script that adds the skill's `python/` to `sys.path`.

## Figure shapes — what "figure-shaped" usually means

Three canonical shapes cover almost every use case (these live in
`pavlab_arch.layout.FIGSIZES`):

| key          | size (in) | aspect | use |
|---           |---        |---     |---  |
| `slide`      | 13.33×7.5 | 16:9   | talk slides, slide decks |
| `square`     | 8×8       | 1:1    | poster panels, web embeds |
| `wide_half`  | 14×4.7    | 3:1    | full page width, half height — one row of stages |

Use `pavlab_arch.layout.figure(shape="wide_half")` to get a
pre-sized figure with `xlim=(0, 100)`, `ylim=(0, 100)` and ticks
already stripped.

## Avoiding overlapping text

Two complementary mechanisms:

1. **Auto-shrink** — `stage_box` calls `fit_text()` by default,
   which scales the label fontsize down (to a floor of ~6.5pt) if
   it would overflow the box. Pass `fit=False` to opt out (e.g.
   when you've already wrapped the label with `\n` and want the
   sizes consistent across the row).
2. **Auto-layout** — `pavlab_arch.layout.grid_columns(widths)`
   places N columns left-to-right with a minimum gap between
   them, scaling widths down proportionally if the total would
   overflow. Combine with `autosize_columns([labels])` to derive
   widths from label lengths.

Both are heuristics — for a final draft, eyeball the rendered
SVG. But they save the first 80% of overlap whack-a-mole.

## Visual encoding rules (general, not lifecycle-specific)

These came out of repeated review cycles. Internalise them before
laying out any figure with more than ~4 boxes.

### Colour is by *actor*, not by *layer*

The palette is an actor encoding that applies everywhere in the
figure: blue = agent/LLM, slate-with-gear = deterministic
pipeline, amber = curator decision, violet = evaluation, red =
recuration / loop-back. If a row contains heterogeneous items
(some agent-driven, some deterministic, some curator), each item
takes its own actor colour. Do NOT paint a whole row one colour
because "this row is the X layer" — that conflates ownership.

The legend chips work consistently at every level: the same
amber chip identifies curator-driven lifecycle stages AND
curator-flavoured tickets in a cross-cutting layer. If a viewer
has to learn two meanings for the same colour, you've broken the
encoding.

### Hybrid stages get `dual_stage_box`

A stage genuinely co-owned by two actors (agent recommends, then
curator decides) gets the diagonal split — left half AI/blue,
right half curator/amber. Picking one colour undersells the
other and lies about who's doing the work. See lifecycle
lesson #5 for the parameter conventions.

### Set + task → `stack_box` (pile with a ticket on top)

When an item represents a *collection of experiments with a job
to do on them* — a ticket queue, an evaluation batch, an audit
pile — draw it as a pile of offset cards (the set) with a
separate ticket overlay (the job). Don't pack both into a
single labeled box; the ticket-on-pile metaphor reads instantly
and the labeled-box doesn't.

The pile encodes set-ness even at a glance; the ticket isolates
*what to do* from *what to do it on*. Use `stack_box` from
`pavlab_arch.primitives`.

### Containers wrap *logical groups*, not visual rows

A rounded-corner outer box implies "these are facets of one
thing." Use containers only when the items inside genuinely ARE
one thing. Two distinct work streams stacked vertically (e.g.
task tickets and evaluations) want row labels + alignment, not a
shared container — otherwise the container reads as a
relationship that isn't there.

If you need to mark a region without implying group identity:
use a section header (small italic text in `SUBTLE`) above the
region; skip the box.

### Box dimensions track content, not aesthetic blocks

Width AND height should hug the content. A two-line label-plus-
subtitle fits in roughly `h = 7–8` axis units (on a 100-unit
canvas); going to `h = 10` or `h = 11` floats text in empty
bands. Same rule horizontally: per-column widths
(`layout.grid_columns`) sized to the longest label, not "make
all columns equal".

If a row of mixed-length labels keeps colliding with
`fit_text`'s lower bound, the box is too narrow — widen that
column, don't shrink the font past readability.

### Long-span dependency arrows route through empty bands

A dependency arrow that crosses 2+ intervening items needs to
either (a) arc through an empty band above/below the row, or
(b) be omitted as illustrative noise. Straight diagonals through
3 columns are unreadable; thin curves through 3 columns are
worse. Use lesson #1's rad-sign rule to put the arc where
there's room.

If the band you'd route through doesn't exist, consider whether
the dependency is real — sometimes the answer is "drop the
arrow; the order is implicit in the layout."

### Labeled edges — the general "arrow with a label" pattern

Whenever a diagram has things connected by arrows AND the arrow
itself carries information, use `labeled_arrow`. This is the
**labeled-edge** pattern, and it shows up in every diagram family
that isn't a pure pipeline:

- state-machine transitions (`"on_failure"`, `"timeout"`)
- pathway diagrams (enzyme names on metabolic arrows)
- network topology (protocol or bandwidth on links)
- ER diagrams (cardinality: `1..*`, `0..1`)
- class associations (`"uses"`, `"depends on"`, `"contains"`)
- Sankey edge labels, dependency reasons, control-flow conditions

```python
from pavlab_arch.primitives import labeled_arrow
from pavlab_arch import palette as P

labeled_arrow(ax, x1, y1, x2, y2, "on_failure",
              connectionstyle="arc3,rad=-0.13",
              shrinkA=6, shrinkB=6,
              label_color=P.ACCENT, label_side=5.0)
```

**Conventions:**

- The label sits **off the arrow path** (perpendicular offset from
  the chord midpoint via `label_side`). Putting the label ON the
  arrow forces the line and the text to compete for the same pixels;
  putting it off keeps both legible.
- Default label style is **italic + ACCENT-colored + bold + 7.5pt**
  — quiet enough not to compete with the structural arrow at typical
  figsizes, but legible.
- `label_side > 0` puts the label to the **left of the arrow's
  direction of travel** (for a clockwise cycle, "left" = outward;
  for left-to-right arrows, "left" = up). Pass a negative value to
  put the label on the right.
- `label_along ∈ [0, 1]` slides the label along the chord (`0.5` =
  midpoint, default; `0.2` near the start, `0.8` near the end). Use
  to disambiguate when multiple labeled arrows fan out from one
  node.
- All `arrow` kwargs pass through (`connectionstyle`, `shrinkA`,
  `linestyle`, `style="-|>"` vs `"->"`, etc.), so the same primitive
  handles curved, dashed, open-head, etc.

The Krebs cycle example uses one `labeled_arrow` call per cycle
edge to draw the curved arrow AND the italic enzyme name in a single
gesture — that's the canonical use of this helper.

### Box and arrow style conventions (composable knobs)

`box`, `oval`, `circle`, and `arrow` take low-level style knobs that
compose into a small grammar of visual conventions. Pick from this
grammar instead of inventing new patterns ad-hoc — the eye learns the
encoding once and reads every figure in the skill the same way.

**Box styles** (apply to `box`, `oval`, `circle`):

| convention                  | params                                                 | use for |
|-----------------------------|--------------------------------------------------------|---------|
| **actor**                   | `stage_box(...)` (current helper)                      | pipeline stages, lifecycle states |
| **passive intermediate**    | `fc=GRID` or `fc=tint(DET)`, `ec=DET`, `lw=1.0`        | metabolites in a pathway, substrates flowing through |
| **catalyst / annotation**   | `fc='white'`, `ec=ACCENT`, `lw=1.3`, italic text       | enzymes, helper notes — usually italic |
| **transient / spawned**     | + `linestyle=(0, (3, 2))` for dashed border            | byproducts that leave the cycle, side-effects |
| **emphasized input**        | `fc='white'`, `ec=ACCENT_5`, solid border              | named inputs that drive the flow (distinguished from byproducts by solid border) |

`oval(cx, cy, w, h)` is a pill (fully rounded rectangle, default
`rounding=min(w,h)/2`). Use for "molecule-like" nodes — chemical
species, ER entities, anything that should read as "a thing flowing
through" rather than "a stage of work."

`circle(cx, cy, r)` is a true circle. Use for single-letter / single-
digit nodes or for the centre of a radial diagram (cycle marker,
hub).

**Arrow styles** (apply to `arrow`):

| convention                  | params                                                 | use for |
|-----------------------------|--------------------------------------------------------|---------|
| **primary flow** (default)  | `style="-|>"`, `lw=2.0`, solid                         | main pipeline arrows, cycle direction |
| **secondary / side flow**   | `style="->"`, `lw=1.0`, open arrowhead                 | byproduct release, input uptake — anything off the main spine |
| **feedback / out-of-band**  | + `linestyle=(0, (5, 3))` dashed                       | rework loops, recall loops, post-shipment feedback |
| **relationship (no head)**  | `style="-"`                                            | "X is related to Y" without directionality |

`shrinkA` / `shrinkB` pull endpoints inside the chord — essential when
the arrow connects shape centres but should visually terminate at the
shape boundary (cycle arrows that connect pill centres but should look
like they touch pill edges).

### Two palettes: the flat ACCENT default, and the modern `CARD_*` option

There are **two palettes** — pick per figure, don't mix:

1. **Flat ACCENT palette** (default) — `palette.ACCENT` / `ACCENT_2…5` /
   `DET`, single hex colours, used by `stage_box` / `box` (border colour +
   `tint()` fill). Publication-restrained; the right default for most
   methods/pipeline figures.
2. **Modern `CARD_*` palette** (opt-in) — soft-fill + crisp-border + dark-text
   **triples** for a contemporary rounded-**card + drop-shadow** look. Use with
   `primitives.card(...)`:

```python
from pavlab_arch.primitives import card, arrow
from pavlab_arch import palette as P

r = card(ax, x, y, w, h, "Design proposer", subtitle="sonnet",
         palette=P.CARD_LLM)                 # indigo LLM card + soft shadow
card(ax, x2, y, w, h, "Pre-assignment checks", palette=P.CARD_DET)  # slate
card(ax, x3, y, w, h, "Opus escalation", palette=P.CARD_JUDGE, dashed=True)
arrow(ax, r[0]+r[2], y+h/2, x2, y+h/2, color=P.CARD_ARROW)          # connect
```

`CARD_*` roles mirror the actor convention: `CARD_LLM` (indigo) LLM/agent ·
`CARD_DET` (slate) deterministic · `CARD_IO` (teal) I/O surface · `CARD_JUDGE`
(violet) strong-tier judge · `CARD_WARN` (amber) load-bearing · `CARD_BAD`
(red) failure/loop-back. `card()` returns `(x,y,w,h)` for arrow anchoring;
`shadow=True` by default (offset in points, resolution-independent);
`dashed=True` for conditional/planned stages. Prefer `card()` + `CARD_*` when
the ask is a "modern / card / drop-shadow" figure; keep `stage_box` + ACCENT
for the restrained default. The shadow is a real path effect — it survives PNG
export and rasterises fine; in SVG it becomes a filter (fine for slides; for a
clean Illustrator round-trip set `shadow=False`).

### Legends: use `legend_block`, never inline label+note stacked inside a chip

A legend chip is too small to vertically stack a bold label and a
muted note inside it — at any reasonable figsize the two texts
collide. Put the chip on the LEFT and the text on the RIGHT,
single line per chip, with the note in `SUBTLE` colour to the
right of the bold label. `legend_block` does this and stacks the
rows vertically into a compact rectangle:

```python
from pavlab_arch.primitives import legend_block
from pavlab_arch import palette as P

legend_block(ax, x=4, y_top=19, specs=[
    # (color, is_det, label, note)
    (P.ACCENT,          False, "Skilled labor", "worker assembly"),
    (P.DET,             True,  "Automated",     "robotic / machined"),
    (P.ACCENT_3,        False, "Decision",      "design · inspection"),
    ((P.DET, P.ACCENT), False, "Hybrid stage",  "robot + worker"),  # tuple = dual chip
    (P.ACCENT_4,        False, "Feedback paths","rework + recall"),
], title="Actor encoding", chip_h=2.0, row_gap=0.8)
```

The block is fully position-parameterised — to move the legend
to another corner of the figure, change only `x` and `y_top`. It
grows DOWN from `y_top` and RIGHT of `x`; the function returns
`(width, height)` so a caller can lay out adjacent content.

A tuple `(left_color, right_color)` in the colour slot renders a
miniature `dual_stage_box` chip — useful for legending a hybrid
actor.

## SVG round-trip / Illustrator compatibility

Figures get opened in Illustrator (or Inkscape) for the last
mile — captioning, alignment tweaks, vector polish. The SVG
must survive that round-trip cleanly. Four gotchas, all caught
in real review cycles:

### 1. Fonts: only reference what the editor has installed

```python
plt.rcParams["font.family"] = ["Helvetica", "Arial", "sans-serif"]
```

Do NOT include `DejaVu Sans` (matplotlib-bundled, absent from a
stock macOS / Illustrator install — triggers Illustrator's "Font
Problems" dialog on every open). Generic `"sans-serif"` is a
safe final fallback because CSS resolves it to whatever the
editor considers default.

`style.apply_rcparams()` already does this; if you're adding
your own rcParams, mirror the rule.

### 2. Glyphs: ASCII / common Latin only

Symbols like ⚙ (U+2699 gear), ⚒, ↺, ★ require a font containing
that codepoint (DejaVu Sans / Symbola / Font Awesome). On a
stock Mac Illustrator install they render as missing-glyph
tofu. Encode the meaning via **colour + shape**, OR draw the
icon as a path:

```python
# YES — drawn shape, font-independent
from matplotlib.patches import RegularPolygon
ax.add_patch(RegularPolygon((cx, cy), numVertices=8, radius=r,
                            facecolor=SUBTLE, edgecolor='none'))

# NO — depends on the editor having Symbola installed
ax.text(cx, cy, "⚙", ...)
```

The `stage_box` helper used to prefix det stages with ⚙ and
was rewritten to drop the glyph — the slate-tinted fill +
sharper corners encode "deterministic" cleanly without needing
a symbol font.

### 3. Strip clipPath wrappers before save — `svg_safe(ax)`

matplotlib's SVG backend wraps each axes' artists in
`<clipPath>` so drawing stays inside the axes bbox. Illustrator's
Tiny SVG import warns "Clipping will be lost on roundtrip to
Tiny" and silently drops the clipping; subtle distortions can
follow. For architecture/diagram figures the clip serves no
purpose (everything is inside 0..100), so kill it before save:

```python
from pavlab_arch.layout import svg_safe

# ... build the figure ...
svg_safe(ax)                          # disables clipping on all artists
fig.savefig("fig.svg", format="svg")  # clean SVG, no <clipPath>
```

`svg_safe` is a one-liner that calls `set_clip_on(False)` on
every patch / line / text / collection in the axes. Free to
call multiple times; safe before save.

### 4. `svg.fonttype="none"` is correct

Keeps text as `<text>` elements (editable in Illustrator) rather
than vector paths. `apply_rcparams()` sets this. The
alternative — `svg.fonttype="path"` — converts every glyph to a
path, which sidesteps glyph-missing problems but loses
editability (every label becomes a non-editable shape). Prefer
`none` + ASCII-safe glyphs over `path` conversion.

## Quick start

```python
import sys
sys.path.insert(0, "skills/architecture-figures/python")
from pavlab_arch.style import apply_rcparams
from pavlab_arch.layout import figure
from pavlab_arch.palette import ACCENT, ACCENT_2, ACCENT_3, ACCENT_4, DET
from pavlab_arch.primitives import (
    stage_box, dual_stage_box, stack_box,
    perf_gauge, ensemble_proposer,
    lane_arrow, legend_block,
    arrow, box,
)

apply_rcparams()
fig, ax = figure(shape="wide_half")          # 14×4.7", 0..100 axis coords

# Mix of LLM and deterministic stages:
stage_box(ax,  5, 40, 10, 20, "one-shot", ACCENT, subtitle="model A")
stage_box(ax, 20, 40, 10, 20, "Rules",    DET,    is_det=True,
          subtitle="+ resolver")
stage_box(ax, 35, 40, 10, 20, "Reviewer", ACCENT_3, subtitle="model B")

arrow(ax, 15, 50, 20, 50)
arrow(ax, 30, 50, 35, 50)

# Ensemble (parallel mini-boxes):
ensemble_proposer(ax, 55, 40, 10, 20,
                  top=("subagents + debate", ACCENT_3),
                  bot=("one-shot",            ACCENT))

# Performance gauge with optional overlay:
perf_gauge(ax, 70, 50, 25, 6, value=0.93, curator_value=0.82,
           color="#60a5fa")  # luminosity-balanced blue
```

## Composes with

- The user-global figure conventions in `~/.claude/CLAUDE.md`
  (Helvetica, Tailwind palette, white facecolor, source caption).
  This skill's `style.apply_rcparams()` is consistent with those.

## Lifecycle state diagrams

Hard-won lessons from building lifecycle / state-machine figures
with feedback loops and parallel tracks:

### 1. `arc3` rad-sign rule — by arrow direction, not figure direction

`connectionstyle="arc3,rad=R"` bows the arc to **the right of the
directed vector p1→p2** when `R > 0`. The sign is relative to the
ARROW's direction of travel, *not* the figure's orientation —
this trips people (and Claude) up repeatedly. Cheat sheet:

| Arrow direction | `rad > 0` bows | `rad < 0` bows | To bow DOWN |
|---|---|---|---|
| → (rightward) | DOWN | UP | use `+` |
| ← (leftward)  | UP   | DOWN | use `−` |
| ↑ (upward)    | RIGHT | LEFT | n/a |
| ↓ (downward)  | LEFT  | RIGHT | n/a |

Practical version: a feedback / loop-back arrow goes one way
and you want it routed through empty space (almost always
"below the lifecycle row"). Pick the sign that puts the arc
where there's room. If the figure has both directions of arrows
(e.g. recuration goes left, a long-span forward dep goes
right), they need OPPOSITE signs to both route downward:

```python
sign = 1 if x2 > x1 else -1
rad  = 0.35 * sign            # both bow DOWN
```

Magnitude: `|rad| ≈ 0.3–0.6` is the readable range. For a
one-column hop the arc is necessarily short; see lesson 3.

### 2. Parallel-tracks (fork-join) pattern

When two pipelines run concurrently between two states (e.g.
analysis-track QC/DEA vs. curation-track design/tags between
`Loaded` and `Audit`), put them on two lanes sharing the same
column.

**Edge selection — easy to get inverted.** Matplotlib y is
positive-UP, so `ys > yd` means the source box is HIGHER on the
canvas than the destination → the arrow goes DOWN. The source
should exit through the edge *facing* the destination lane;
the destination enters at the opposite edge:

```python
if ys > yd:           # going DOWN
    src = (xs + ws*0.7, ys)            # bottom of upper box
    dst = (xd + wd*0.3, yd + hd)       # top of lower box
else:                 # going UP
    src = (xs + ws*0.7, ys + hs)       # top of lower box
    dst = (xd + wd*0.3, yd)            # bottom of upper box
```

Getting this inverted produces a comical arrow that exits the
top of the source, loops sideways through empty space, and
arrives at the bottom of the destination — visually obvious in
review but easy to ship if you forgot which way matplotlib's y
points.

**Style of the cross-lane edge — use `lane_arrow` with the default
`cross_mode="smooth_l"`.** Cross-lane forks/joins render as
L-paths with rounded corners (pipe-elbow style) via
`connectionstyle="angle,...,rad=corner_rad"`.

**Routing rule — vertical near source, horizontal near target.**
This asymmetric rule sidesteps an obstacle that bites the naive
version: in a typical fork/join, the source's column in the
parallel-tracks region has a same-column stage on the OPPOSITE
lane (e.g. paint shop on lane 0 and powertrain on lane 1, same
column 3). A naive V-then-H routing for the join would put the
vertical leg in the source's column at the *target's* lane height
— right through that same-column stage. The asymmetric rule keeps
the vertical leg on the source's side, where the inter-lane band
is empty.

- **Going DOWN (fork)** — V-then-H "down then right". Exit the
  source's BOTTOM at `src_frac` across its width, descend through
  the inter-lane band (empty in source's column, which is in the
  single-lane region before the parallel tracks), turn right at
  a smooth corner of radius `corner_rad`, horizontal into the
  target's LEFT at `dst_frac` of its height. Arrowhead points
  RIGHT.

- **Going UP (join)** — H-then-V "right then up". Exit the source's
  RIGHT at `src_frac` up its height, traverse horizontally through
  the inter-lane band into the target's column (empty on source's
  lane, since the target's column has the destination on the other
  lane), turn up at a smooth corner of radius `corner_rad`, vertical
  into the target's BOTTOM at `dst_frac` across its width.
  Arrowhead points UP.

The arrowhead direction differs between fork (→) and join (↑),
but this matches the semantics: fork is forward progression on the
target's lane, join is the source rising up to merge into the
target.

Why not the old `arc3,rad=±0.15` cross-lane arc: on short chords
(adjacent columns), small-rad `arc3` renders as a bent / cusp-like
path. Why not `angle3`: it's a Bezier with control at the corner
intersection, and on tight geometry the curve collapses into a
near-cusp. The `angle,rad=N` style draws explicit straight segments
joined by a circular arc of radius N — a true pipe elbow. Why not
a straight diagonal: it competes with the same-source same-lane
edge and reads ambiguously.

```python
from pavlab_arch.primitives import lane_arrow
# Same-lane and cross-lane both handled — no per-edge branching:
for src, dst in FORWARD_EDGES:
    lane_arrow(ax, centres[src], centres[dst],
               color=P.SUBTLE, lw=2.0, mut=14)
# Override defaults if the geometry forces it:
lane_arrow(ax, src, dst, cross_mode="diag")       # straight diagonal
lane_arrow(ax, src, dst, cross_mode="arc", arc_rad=-0.3)  # arc3
```

The skeleton:

```python
STAGES = [
    # (key, label, subtitle, color, is_det, col, lane)
    ("loaded", "Loaded", "EE + autofill", DET,      True,  3, 0),
    ("curate", "Curate", "Proposer",      ACCENT,   False, 4, 0),  # top
    ("process","Process","QC · DEA",      DET,      True,  4, 1),  # bottom
    ("audit",  "Audit",  "Auditor",       ACCENT,   False, 5, 0),
]
FORWARD_EDGES = [
    ("loaded", "curate"),    # fork: top
    ("loaded", "process"),   # fork: bottom
    ("curate", "audit"),     # join: top
    ("process","audit"),     # join: bottom
]
```

Cross-lane edges want a small bend so they don't read as straight
diagonals through other content:

```python
arrow(ax, xs+ws, ys+hs/2, xd, yd+hd/2,
      connectionstyle="arc3,rad=-0.15" if ys > yd else "arc3,rad=0.15")
```

Lane spacing: with `stage_h = 10`, the two lane centers want
~15–18 axis-coord units apart to give arrows + labels room.
Top lane around `y=75`, bottom around `y=56` works for a 100-unit
figure.

### 3. Don't center-label short arcs

When the chord between two stages is short (one column), the
arc's apex sits exactly where a centered label would go — they
overlap. Park the label OFF the arc:

```python
# Recuration label under the source stage, not on the arc apex
ax.text(xa + wa * 0.9, ya - 3.5, "recuration loop",
        ha="left", va="top", color=ACCENT_4, fontsize=8.5,
        style="italic", fontweight="bold")
```

Long-chord arcs (3+ columns apart) tolerate center labels fine.

### 4. Dashed cross-cutting arrows must be thicker than you think

For dashed arrows from a cross-cutting layer (e.g. task tickets /
evaluations) pointing UP into the lifecycle row:

```python
FancyArrowPatch(..., arrowstyle="-|>", linewidth=1.8,
                mutation_scale=14, linestyle=(0, (4, 2.5)))
```

`linewidth=1.2` disappears against a tinted-background container;
`linewidth=1.8` and `mutation_scale=14` is the minimum that
reads. Dash pattern `(4, 2.5)` is enough whitespace to look
intentional but not so much it dissolves.

### 5. Hybrid (AI + curator) stages get `dual_stage_box`

When a stage is genuinely co-owned by an agent AND a curator —
e.g. "Candidate" (AI recommends, curator triages), or any future
"AI proposes, human accepts" gate — encode it with the
near-vertical two-colour split rather than picking one colour and
underselling the other. Convention: AI/agent colour (typically
`ACCENT`, blue) on the LEFT half; curator colour (typically
`ACCENT_3`, amber) on the RIGHT half. Each half carries the full
`stage_box` treatment — matching tint fill *and* matching border
colour on its outer perimeter — so the box reads as "Curate-shaped
left half + Public-shaped right half sharing a seam":

```python
from pavlab_arch.primitives import dual_stage_box
from pavlab_arch.palette import ACCENT, ACCENT_3

dual_stage_box(ax, x, y, w, h, "Candidate",
               ACCENT,           # left: AI recommend
               ACCENT_3,         # right: curator triage
               subtitle="AI recommend · curator triage")
```

The diagonal endpoints sit on the TOP and BOTTOM edges, not at
the corners, so the seam reads as "through the middle" rather
than decorative. `slope` controls the lean (default 0.4 keeps
the seam clearly diagonal but mostly vertical).

In a STAGES tuple list driving a lifecycle figure, encode a
hybrid by making the colour field a `(left, right)` tuple; the
figure builder can switch to `dual_stage_box` automatically when
it sees a tuple, and `stage_box` otherwise.

### 6. Vertical budget for a 7+ stage lifecycle figure

For a 15"×7.4" figure on 0..100 axis coords with two lanes + a
two-row cross-cutting layer + legend strip:

```
  y=88-96   Title strip
  y=70-80   Top lane (linear states + parallel-tracks top)
  y=50-66   Bottom lane (parallel-tracks bottom) + recuration band
  y=33-49   Cross-cutting tickets row (inside SOFT_BG container)
  y=21-32   Cross-cutting evaluations row
  y=4-7     Legend strip
  y=0       Source caption (small, gray)
```

Squeezing more than 8 stages or adding a third cross-cutting row
pushes you to `figsize=(16, 8.5)` and bumps row heights up.

## Gantt charts

For schedule / roadmap views — anywhere you need to show tasks with
planned spans, progress, and status — use the Gantt primitives. They
share the same clean / flat / modern aesthetic as the rest of the
skill (matching palette, lab-style spines off, y-axis grid off,
left-aligned title), so a Gantt chart in a deck reads as part of
the same visual family as the architecture diagrams.

```python
from pavlab_arch.primitives import GanttTask, gantt_bar, today_line

tasks = [
    GanttTask("Wireframes",       2.0, 3.5, 3.5, "done",     "Design"),
    GanttTask("Visual design",    3.0, 4.5, 3.5, "inflight", "Design"),
    GanttTask("Auth migration",   3.5, 5.0, 0.0, "blocked",  "Engineering",
              note="Blocked on infra"),
    GanttTask("Perf hardening",   6.0, 7.5, 0.0, "deferred", "QA"),
    # ...
]

for i, t in enumerate(reversed(tasks)):
    gantt_bar(ax, i,
              plan_start=t.plan_start, plan_end=t.plan_end,
              done_end=t.done_end, status=t.status)

today_line(ax, x=3.5, label="today")
```

### Status grammar

Each task's *remaining* (unfilled) portion is painted by status; the
*done* portion is always emerald. The five statuses cover every
schedule state I've found in practice:

| status      | remaining overlay style                              |
|-------------|------------------------------------------------------|
| `"done"`    | nothing (the whole bar is the emerald done overlay)  |
| `"inflight"`| amber semi-transparent fill (ACCENT_3, alpha 0.55)   |
| `"planned"` | nothing (planned-bar gray-200 shows through)         |
| `"blocked"` | red hatched fill (ACCENT_4 edge, `hatch="//"`)       |
| `"deferred"`| dotted hatched fill (SUBTLE edge, `hatch=".."`)      |

### Conventions for Gantt layouts

- **Rows reversed for display**: iterate `reversed(tasks)` when
  placing bars so the FIRST task in your `tasks` list sits at the
  TOP of the chart. Matplotlib's `barh` increases y upward; people
  read top-to-bottom.
- **Category bands**: group tasks by `task.category`; render
  alternating categories with a `SOFT_BG` `axhspan` and put the
  category name at the right margin, vertically centered on the
  group. This replaces explicit category divider lines, which add
  noise.
- **X-axis ticks** can be any monotonic numeric scale — encode dates
  as floats (`(date - epoch).days / 7` for weeks), session counters,
  sprint numbers. The primitive doesn't care; the tick labels are
  yours to set.
- **Y-grid off, X-grid on**: lab style. `ax.yaxis.grid(False)`,
  `ax.xaxis.grid(True, color=GRID, linewidth=0.6)`. Spines off for
  the flat look.
- **Today line** via `today_line(ax, x)` — dashed SUBTLE vertical
  with a small "today" annotation positioned just below the top of
  the chart.
- **Legend at the bottom**: use matplotlib `Patch`es for the status
  swatches (the gantt_bar primitive doesn't auto-build a legend —
  it's a low-level brick). See the example file for the patch
  recipes.

See `examples/gantt_chart_example.py` for a complete render.

### Progress overlays — "plan vs. reality"

A Gantt is a plan, not reality. The base `gantt_bar` encodes plan-
vs-done within a single snapshot (gray planned span + emerald done
overlay + status-coloured remaining portion), but says nothing about
**whether the row is on schedule today** or **what moved between two
review dates**. Two orthogonal helpers add those:

#### Schedule variance vs. today — `gantt_variance`

For each row, compares `done_end` against today (assuming linear
progress, so the expected position at `today` is just `today` itself,
clamped to the plan window) and tints the gap red if the row is
behind plan:

```python
from pavlab_arch.primitives import gantt_bar, gantt_variance, today_line

for i, t in enumerate(reversed(tasks)):
    gantt_bar(ax, i, t.plan_start, t.plan_end, t.done_end, t.status)
    cls = gantt_variance(ax, i, t.plan_start, t.plan_end,
                         t.done_end, today=TODAY_X)
    # cls in {"not_started", "complete", "overdue", "behind",
    #         "ahead", "on_track"} — use for caller-side annotation
today_line(ax, TODAY_X, label="today")
```

The function only draws an overlay for the cases that need
attention: `"behind"` (gap `[done_end, today]`) and `"overdue"`
(gap `[done_end, plan_end]` after the planned window has elapsed).
`"ahead"` and `"on_track"` draw nothing — the emerald done bar
already extends past the global today line, which self-documents
the "going well" case. Per-row markers would duplicate the global
`today_line`, so the helper omits them on purpose.

#### Snapshot diff (T1 -> T2) — `gantt_bar_two_tier` + `gantt_bold_changed_labels`

For "what moved between two review dates", replace `gantt_bar` with
the two-tier version: top half = state at T1 (pale, 45% alpha),
bottom half = state now (full saturation), with a tiny white seam
between them so they read as stacked rather than blended.

```python
from pavlab_arch.primitives import (
    gantt_bar_two_tier, gantt_bold_changed_labels,
)

statuses_then = []
statuses_now = []
for i, row in enumerate(reversed(rows)):
    gantt_bar_two_tier(
        ax, i, row.plan_start, row.plan_end,
        done_end_then=row.de_t1, status_then=row.st_t1,
        done_end_now=row.de_t2,  status_now=row.st_t2,
    )
    statuses_then.append(row.st_t1)
    statuses_now.append(row.st_t2)

# bottom-to-top order — match ax.get_yticklabels()
gantt_bold_changed_labels(ax, statuses_then, statuses_now,
                          color_regressions=True)
```

A row whose status didn't change reads as the same shape at two
saturations (visually quiet). A row that moved reads as two
different shapes stacked. The bold-label pass is **necessary for
the encoding to self-explain**: without it, every row competes for
the reader's attention equally and unchanged rows feel like noise.
With it, the "what moved between T1 and T2" question is answerable
from the y axis alone.

`color_regressions=True` additionally tints the y-label red on rows
that *regressed* (status rank decreased: `done -> blocked`,
`inflight -> planned`, etc.). The default status ranking is
`deferred = blocked = 0 < planned = 1 < inflight = 2 < done = 3`;
pass `rank=...` to override.

#### Composing A + C

The two are orthogonal — the same chart can carry both. The
combined panel pattern is "two stacked Gantts": top panel shows the
current snapshot with variance overlay (mode A), bottom panel shows
T1 -> T2 diff (mode C). See `examples/gantt_progress_overlay_example.py`
for the canonical recipe.

#### Convention: stamp the snapshot date in the filename

Always include the snapshot date in the filename when emitting a
Gantt: `roadmap_2026-05-18.svg`. Same for the regenerator script
and any captions entry. Otherwise diffing v1 vs v2 of the same chart
across time means digging through git history for the right
regenerator.

## Software stack diagrams

For onboarding docs, architecture decision records, system overviews
— anywhere you need to show what runs where and how the pieces talk
to each other. The canonical layout is **horizontal tier bands
stacked vertically**, with components in each tier and labeled
arrows between tiers.

### Layout

A typical stack figure has four or five tiers, each rendered as a
soft `SOFT_BG` rounded-rectangle band with the tier name in italic
`SUBTLE` text in the left margin:

```
  Client     ┌─────────────────────────────────────────────────┐
             │                  [Browser]                      │
             └─────────────────────────────────────────────────┘
  Frontend   ┌─────────────────────────────────────────────────┐
             │    [Curation UI]            [Browser UI]        │
             └─────────────────────────────────────────────────┘
  Services   ┌─────────────────────────────────────────────────┐
             │  [Agent svc]   [REST]   [External · dashed]     │
             └─────────────────────────────────────────────────┘
  Storage    ┌─────────────────────────────────────────────────┐
             │  ( SQLite )  ( FAISS )  ( MySQL )  ( H2 )       │
             └─────────────────────────────────────────────────┘
```

The pattern is reusable for any stack diagram — swap the tier names,
swap the components, keep the band-and-component structure.

### Shape conventions

- **Services / UI / clients are rectangles** (`box` or the inline
  `tech_box` helper in the example). The rectangle is "a thing
  running" — a process, an app, a service.
- **Aux data stores are pills** (`oval`). The pill is "a thing
  sitting" — a cache, a vector index, a file-based store, a
  test-only DB. Shape difference tells the reader "service vs
  storage" without reading any text.
- **Primary / production databases are cylinders** (`cylinder`) —
  the conventional database symbol with an elliptical top, vertical
  sides, and a half-elliptical bottom. Use this for the system-of-
  record (the durable, business-critical store). The cylinder vs
  pill split lets a reader pick out "the real DB" from "the
  indexes / caches / scratch stores" at a glance, even within the
  storage tier.
- **External / third-party services use a dashed border**
  (`box(..., linestyle=(0, (3, 2)))`). Signals "we call this, we
  don't own it."
- **Logical groupings use `container`** — a dashed rounded
  rectangle around related elements, with a bold label at the top-
  left. Use to mark "Front End / Back End" mega-regions, "DMZ vs
  internal", "pre-prod vs prod", etc. Distinct from `tier_band`
  (soft-filled background, no border) because the container has an
  explicit border — "these belong together as a unit," vs the band
  which says "these are the same layer."

### Colour conventions

- ACCENT (blue) — frontend / UI tier
- ACCENT_3 (amber) — backend services tier
- ACCENT_2 (green) — durable / production data stores
- ACCENT_5 (violet) — vector / ML-adjacent stores OR external services
- DET (slate) — neutral / client / browser

Pick consistently across the figure. The eye learns "blue = JS, amber
= backend, green = DB" within the first few seconds, then reads
faster.

### Arrows

Use `labeled_arrow` for every inter-tier connection. The label is the
**wire protocol or contract** (`HTTPS`, `JSON`, `JDBC`, `mmap`,
`file`, `gRPC`, `Kafka`, etc.). Default label styling — italic
ACCENT 7.5pt — is intentionally quiet; override `label_color` to
`SUBTLE` for an even quieter feel when the structural arrow is doing
the load-bearing work.

**Bidirectional flow is the common case**, not one-way. A frontend
calling a backend is request-AND-response; a service reading-AND-
writing a database is bidirectional too. Encode this with
`style="<|-|>"` (filled arrowheads at both ends). Reserve one-way
arrows (`style="-|>"`) for genuinely-one-way relationships: emit-
only sinks, fire-and-forget queues, append-only logs. The two-way
arrow is the default for any "X talks to Y" wire.

### Layout-first, arc-around-as-last-resort

If a connection would have to **arc over another box** to reach its
target, prefer rearranging the layout so the target sits adjacent to
the source — eliminating the need for the arc entirely. A labeled
arrow drawn as a clean short segment reads better than the same
arrow looping over a same-tier obstacle, no matter how nicely the
arc is tuned.

In the software-stack example the external LLM API was originally
placed at the far right of the services tier, which forced its
arrow from Curation agents to arc up over Gemma REST. The fix
wasn't a nicer arc — it was placing the LLM API immediately
adjacent to Curation agents (with `tech_box(..., dashed=True)` for
the external styling). The same rule applies in any diagram family:
**move boxes before you route arrows around them.**

Arcs over obstacles (`connectionstyle="arc3,rad=-N"`) are still
appropriate when the layout is locked by other constraints — long-
span feedback loops (e.g. the recall U-shape in the IC-car figure),
or cross-cutting layer arrows where the box arrangement is
load-bearing. But for inter-tier flows in a stack diagram, you
almost always have enough layout freedom to skip them.

### Inline `tech_box` pattern

Each service / app box typically has a bold component name on top
and a muted multi-line tech-stack list below — "Curation UI" /
"React 18 · TypeScript · Vite / TanStack Query · Tailwind". The
example file ships an inline `tech_box(ax, x, y, w, h, title,
tech_lines, color)` helper for this; copy it if you want the same
layout in your own stack figure.

See `examples/software_stack_example.py` for a complete render.

## Examples

`examples/lifecycle_example.py` (wide_half, 15×7.4)
— canonical lifecycle figure with linear progression, parallel-
tracks fork/join, a recuration loop-back arc, a cross-cutting
layer (tickets + evaluations), and a legend strip. Reduced
genericized version of the figure shipped on 2026-05-18; use as
the reference for the fork-join + feedback-loop pattern.

`examples/methods_comparison_example.py` (wide_half, 14×variable)
— a multi-row pipeline comparison: rows are competing methods,
columns are pipeline stages, gauges on the right show
per-method F1. Demonstrates `ensemble_proposer` (one row uses
two parallel proposers), `perf_gauge` with a curator-corrected
overlay, and the right-aligned method-name convention.

`examples/software_stack_example.py` (slide, 13.33×7.5)
— layered software stack diagram modelled on the gemma-curation-ui
ecosystem (two React apps over a Python agents service + a Java
Spring REST service, all backed by SQLite / FAISS / MySQL / H2,
plus an external LLM API). Demonstrates the **tier-band** layout
(Client / Frontend / Services / Storage) with `SOFT_BG` background
containers + left-margin italic tier labels, the
**rectangle / pill / cylinder** shape grammar (services / aux
stores / system-of-record DB), the **dashed-border** convention
for external services, **bidirectional `style="<|-|>"` arrows**
for every inter-tier wire (request + response), and `labeled_arrow`
for protocol labels. Demonstrates the **layout-first principle**:
the external API sits adjacent to its caller (Curation agents)
instead of across the row, so no arc-over-obstacle routing is
needed. The inline `tech_box` helper (component name + multi-line
tech-stack list) is reusable for any stack figure.

`examples/gantt_chart_example.py` (~9×variable)
— flat / modern Gantt chart showing 15 tasks across 5 categories
(Discovery, Design, Engineering, QA & polish, Release) with all
five status states (done, in flight, planned, blocked, deferred)
visible. Demonstrates the `GanttTask` + `gantt_bar` + `today_line`
primitives plus the conventions for category bands, today reference
line, x-axis tick labels, and bottom-row legend. Adapt by swapping
the `TASKS` list and adjusting `X_TICKS` / `X_LABELS` for your
time encoding (sessions, weeks, sprints, calendar dates).

`examples/gantt_progress_overlay_example.py` (10×variable)
— two stacked Gantt panels demonstrating the **plan-vs-reality**
overlays. Top panel uses `gantt_variance` to tint behind-schedule
and overdue rows red relative to today; bottom panel uses
`gantt_bar_two_tier` for a T1 -> T2 snapshot diff (pale upper tier
= state at the earlier checkpoint, full lower tier = state now),
plus `gantt_bold_changed_labels` to bold y-tick labels of rows
whose status changed and red-tint labels of rows that regressed
(e.g. `planned -> deferred`). Shows how the two modes compose on a
single figure — schedule variance answers "are we on track today",
snapshot diff answers "what moved since last review". Use as the
reference whenever the chart needs to communicate progress over
time, not just a static plan.

`examples/krebs_cycle_example.py` (9.5×9.5)
— real-world non-LLM example demonstrating the extended box / arrow
style conventions in a domain where the visual grammar is naturally
non-pipeline: the Krebs cycle (citric acid cycle). Eight metabolite
pills (`oval(... ec=DET, lw=1.0)`, passive intermediates) arranged in
a circle, eight curved cycle arrows (`-|>` filled), enzymes as italic
ACCENT-colored text on the arcs (no box, the standard biochem
convention), eight byproduct/input chips as dashed-or-solid-border
pills outside the cycle (`oval(... linestyle=(0,(3,2)))` for dashed
transients vs solid for the emphasized Acetyl-CoA input), and thin
open-arrowhead side arrows (`style="->", lw=1.0`) for byproduct
release and input uptake. A central `circle(... text="TCA")` marks
the cycle topology. Use as the reference when establishing a
multi-style convention diagram outside the typical software-pipeline
domain.

`examples/ic_car_assembly_example.py` (15.5×5.5)
— real-world (non-bio, non-LLM) architecture: internal-combustion
vehicle production from design through ship. Demonstrates that
the colour grammar adapts cleanly to physical manufacturing
(blue = skilled labor, slate = robotic/automated, amber =
decision/inspection, red = feedback). The fork at `design` runs
parallel body and powertrain lines through three columns before
converging at `marriage` — the canonical use case for
`dual_stage_box` since a real marriage stage is genuinely
co-actor (robotic gantry lift + human alignment). Includes two
feedback channels at different time scales: an in-shift rework
loop (short solid red arc, QC → Final) and a post-shipment
recall loop (long dashed red U-shape, Ship → Design). The
recall is routed as an explicit U (down → across → up) instead
of a deep `arc3` arc because a long-chord arc would either pass
through the parallel lane stages or collide with the legend —
the U-shape uses the empty band between the bottom lane and the
legend, and reads unambiguously as a long-range out-of-band
channel. Use as the reference when you need two feedback paths
at different scales in the same figure.
