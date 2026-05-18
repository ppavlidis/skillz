---
name: architecture-figures
description: >
  Matplotlib primitives for hand-authored architecture / methods /
  pipeline / lifecycle figures in a flat, modern, publication-grade
  style. Ships `pavlab_arch.primitives` with reusable helpers:
  `stage_box` (LLM vs deterministic styling, auto-shrinking text),
  `dual_stage_box` (diagonally-split two-colour stage for hybrid
  AI+curator phases — each half carries the matching tint fill and
  border colour of a normal `stage_box`), `ensemble_proposer`
  (parallel mini-boxes for "union of two proposers"), `perf_gauge`
  (horizontal F1 bar with optional curator-corrected overlay;
  luminosity-balanced palette), `arrow` (thick arrows, not
  spindly), `box`, and `fit_text`. Plus
  `pavlab_arch.layout` with three canonical figure shapes
  (`slide` 16:9, `square` 1:1, `wide_half` 3:1 for full-page-width /
  half-height) and a `grid_columns` helper that lays out N columns
  without overlap regardless of label length, and
  `pavlab_arch.style.apply_rcparams()` for the canonical Helvetica +
  white-facecolor + editable-SVG defaults. Use this skill whenever
  building a figure that compares pipeline architectures, diagrams
  a workflow lifecycle with feedback loops, shows a per-stage
  primer, contrasts LLM vs deterministic components, or surfaces a
  quantitative metric (F1, accuracy) as a bar gauge instead of a
  number. The defaults bake in the hard-won lessons from iteration:
  tight box widths per column, right-aligned method labels flush
  against the first column, no redundant text duplicating what the
  diagram shows, thick arrows, gear glyphs for deterministic
  stages, soft tinted fills for LLM stages, approach-based legends
  (not model-name legends), `arc3` rad-sign discipline for loop-back
  arrows, and labels parked off short arcs.
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

## Quick start

```python
import sys
sys.path.insert(0, "skills/architecture-figures/python")
from pavlab_arch.style import apply_rcparams
from pavlab_arch.layout import figure
from pavlab_arch.palette import ACCENT, ACCENT_2, ACCENT_3, ACCENT_4, DET
from pavlab_arch.primitives import (
    stage_box, dual_stage_box, perf_gauge, ensemble_proposer, arrow, box,
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

### 1. `arc3` rad-sign rule for loop-back arrows

`connectionstyle="arc3,rad=R"` bows the arc to **the right of the
directed vector p1→p2** when `R > 0`. So for a loop-back arrow
going right-to-left (e.g. `Audit → Curate` recuration loop along
the top of the diagram):

- `rad > 0` → arc bows **upward** (over the boxes — almost always
  collides with the title strip or other stages)
- `rad < 0` → arc bows **downward** (clear of the row — what you
  want)

Mirror for left-to-right loops: `rad > 0` bows down, `rad < 0`
bows up. Pick the sign that puts the arc in **empty band**, not
over labeled content.

Magnitude: `|rad| ≈ 0.4–0.6` produces a visible arc without
needing extreme vertical space. For a one-column hop the arc is
necessarily short; see lesson 3.

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

**Style of the cross-lane edge.** Straight diagonals work
cleanly when the two lanes are ~15+ axis units apart and the
columns are adjacent — the diagonal slope is gentle and the
arrow doesn't cross any same-lane stages. Skip the
`connectionstyle` arc entirely. Use arcs only when the geometry
forces the diagonal through another box.

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
