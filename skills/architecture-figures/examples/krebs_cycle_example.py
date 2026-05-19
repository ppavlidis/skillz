"""Krebs cycle figure — exercising extended box / arrow style conventions.

Real-world (non-LLM, non-CS) test of the skill's primitives in a domain
where the visual grammar is naturally different from a stage pipeline:
chemical pathway diagrams. Demonstrates conventions beyond the standard
``stage_box`` + ``arrow``:

  - **Pill-shaped passive intermediates** with thin slate border
    (``oval(... fc=tint(DET), ec=DET, lw=1.0)``): metabolites read as
    soft passive nodes — present in the diagram, but not "actors". The
    thin border gives definition against a white background without
    looking stage-like.

  - **Italic colored text catalysts** (no box): enzyme names sit
    just OUTSIDE the cycle at the arc midpoint, rendered as italic
    ``ACCENT``-colored text. This is the standard biochemistry
    convention and removes the box / pill overlap that an extra
    enzyme rectangle would force.

  - **Dashed-border transient byproducts** (``oval(... linestyle=(0,
    (3, 2)))``): spawned products (NADH, FADH2, GTP, CO2, CoA-SH)
    are pill chips with dashed colored borders — visually marked as
    "transient, exits the cycle."

  - **Solid-border emphasized input** (``oval(... linestyle='solid')``):
    Acetyl-CoA is the carbon-input — solid border distinguishes it
    from spawn-and-leave byproducts.

  - **Open-arrowhead secondary arrows** (``arrowstyle="->", lw=1.0``):
    side connections from cycle to byproducts (and inputs to cycle)
    use thin open arrowheads, easily distinguished from the thick
    filled-arrowhead primary cycle flow.

  - **Curved cycle arrows** (``connectionstyle="arc3,rad=-0.13"``):
    eight forward arrows bow OUTWARD from cycle centre (negative
    ``rad`` because the cycle runs clockwise). ``shrinkA/shrinkB``
    pull the endpoints inside the pill edges.

  - **A central circle** (``circle(...)``) labels the diagram as
    "TCA cycle" — demonstrates the circle primitive in a context
    where the topology genuinely is circular.

Color encoding:

  - DET (slate)      — passive intermediates (metabolites)
  - ACCENT (blue)    — catalysts (enzymes, italic text)
  - ACCENT_2 (green) — energy carriers (NADH, FADH2, GTP)
  - ACCENT_3 (amber) — CO2 released as waste
  - ACCENT_5 (violet)— Acetyl-CoA carbon input
  - SUBTLE (gray)    — CoA-SH (recycled, neutral)

Outputs:
    krebs_cycle_example.svg
    krebs_cycle_example.png
"""
from __future__ import annotations
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.layout import figure, svg_safe, pill_edge  # noqa: E402
from pavlab_arch.primitives import (  # noqa: E402
    oval, circle, legend_block, labeled_arrow,
)
from pavlab_arch.style import apply_rcparams  # noqa: E402


# ---------------------------------------------------------------------------
# Cycle geometry
# ---------------------------------------------------------------------------

CENTER = (50.0, 50.0)
RADIUS = 30.0
N = 8

PILL_W, PILL_H = 15.0, 6.5
ENZYME_OFFSET = 5.5      # outward from arc midpoint (italic text)
BYP_OFFSET = 14.0        # outward from arc midpoint (chip)
BYP_TANGENT = 5.0        # tangential splay between sibling byproducts
CHIP_W, CHIP_H = 9.5, 3.8
CYCLE_SHRINK = 6.0
CYCLE_RAD = -0.13
ENZYME_FONTSIZE = 9.0


# (key, name, formula-tag)
MOLECULES = [
    ("citrate",      "Citrate",         "C6"),
    ("isocitrate",   "Isocitrate",      "C6"),
    ("akg",          "alpha-Ketoglutarate", "C5"),
    ("succinyl_coa", "Succinyl-CoA",    "C4"),
    ("succinate",    "Succinate",       "C4"),
    ("fumarate",     "Fumarate",        "C4"),
    ("malate",       "L-Malate",        "C4"),
    ("oaa",          "Oxaloacetate",    "C4"),
]

# Enzyme name + line-break-friendly form (renders as italic text)
ENZYMES = [
    "aconitase",
    "isocitrate DH",
    "alpha-KG DH",
    "succinyl-CoA\nsynthetase",
    "succinate DH",
    "fumarase",
    "malate DH",
    "citrate synthase",
]

# Byproducts spawned at step i -> (i+1). Each entry: (label, color).
BYPRODUCTS = [
    [],
    [("CO2", P.ACCENT_3), ("NADH", P.ACCENT_2)],
    [("CO2", P.ACCENT_3), ("NADH", P.ACCENT_2)],
    [("GTP", P.ACCENT_2)],
    [("FADH2", P.ACCENT_2)],
    [],
    [("NADH", P.ACCENT_2)],
    [],
]

# Inputs consumed BEFORE step i -> (i+1).
INPUTS = [
    [], [], [], [], [], [], [],
    [("Acetyl-CoA", P.ACCENT_5)],
]


def angle_for(idx: int) -> float:
    return math.radians(90 - idx * (360 / N))


def position_on_cycle(idx: int) -> tuple[float, float]:
    a = angle_for(idx)
    return (CENTER[0] + RADIUS * math.cos(a),
            CENTER[1] + RADIUS * math.sin(a))


def arc_midpoint(idx_from: int, idx_to: int) -> tuple[float, float, float, float]:
    p1 = position_on_cycle(idx_from)
    p2 = position_on_cycle(idx_to)
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    dx, dy = mx - CENTER[0], my - CENTER[1]
    d = math.hypot(dx, dy) or 1.0
    return mx, my, dx / d, dy / d


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw_molecule(ax, idx: int, name: str, formula: str) -> None:
    """Pill-shaped passive intermediate: thin slate border + light fill.

    The pill is the SUBSTRATE — content flowing through the cycle, not
    an actor. The thin slate border gives definition against the white
    background without reading as stage-like.
    """
    cx, cy = position_on_cycle(idx)
    oval(ax, cx, cy, PILL_W, PILL_H,
         fc=P.GRID, ec=P.DET, lw=1.2)
    ax.text(cx, cy + 1.1, name,
            ha="center", va="center",
            color=P.TEXT, fontsize=10.5, fontweight="bold")
    ax.text(cx, cy - 1.9, formula,
            ha="center", va="center",
            color=P.SUBTLE, fontsize=8.0, style="italic")


def draw_labeled_cycle_arrow(ax, idx_from: int, idx_to: int,
                              enzyme_name: str) -> None:
    """Curved cycle arrow + enzyme label, in one call via
    ``labeled_arrow``. The label sits on the OUTWARD side (positive
    ``label_side`` because we picked left-perpendicular = outward for
    clockwise cycles).

    Critical: the arrow endpoints are at the SOURCE and TARGET pills'
    EDGES (with a 1.5-unit margin for breathing room) — not at the
    pill centres. This is what makes the arrowhead visible. With
    endpoints at centres + ``shrinkB`` in points, the arrowhead got
    rendered inside the pill and covered by the pill's fill — the
    cycle then looked like plain lines, not arrows.
    """
    p1c = position_on_cycle(idx_from)
    p2c = position_on_cycle(idx_to)
    p1 = pill_edge(p1c[0], p1c[1], PILL_W, PILL_H, p2c[0], p2c[1], margin=1.5)
    p2 = pill_edge(p2c[0], p2c[1], PILL_W, PILL_H, p1c[0], p1c[1], margin=1.5)
    labeled_arrow(
        ax,
        p1[0], p1[1], p2[0], p2[1],
        enzyme_name,
        color=P.SUBTLE, lw=2.0, mut=14,
        connectionstyle=f"arc3,rad={CYCLE_RAD}",
        label_color=P.ACCENT, label_fontsize=ENZYME_FONTSIZE,
        label_style="italic", label_weight="bold",
        label_side=-ENZYME_OFFSET,   # negative = right-of-arrow = INWARD for CW cycle.
    )


def draw_side_chip(ax, x: float, y: float,
                   label: str, color: str, *, dashed: bool = True) -> None:
    """Small pill chip for byproducts / inputs.

    ``dashed=True``  → spawned byproduct (leaves the cycle).
    ``dashed=False`` → emphasized input (Acetyl-CoA), solid border.
    """
    linestyle = (0, (3, 2)) if dashed else "solid"
    oval(ax, x, y, CHIP_W, CHIP_H,
         fc="white", ec=color, lw=1.4, linestyle=linestyle,
         text=label, text_color=color, fontsize=9.0,
         fontweight="bold")


def draw_side_arrow(ax, x1, y1, x2, y2, color) -> None:
    """Filled-arrowhead arrow between cycle anchor and side chip.

    Sized so the byproduct arrows read as secondary-to-the-cycle but
    don't become spindly. ``shrinkA``/``shrinkB`` are ZERO here — the
    breathing room comes from ``pill_edge(... margin=...)`` at the
    chip end, computed in axis units (the right units for our 0..100
    coordinate space). Mixing shrink-in-points with margin-in-units
    pulled the tip back inside the chip and erased the arrowhead.

    The direction is meaningful — byproduct arrows point FROM cycle
    TO chip (output: spawned), input arrows point FROM chip TO cycle
    (input: consumed). Always draw with an asymmetric arrowhead
    (``-|>``) so the direction is obvious.
    """
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>",
        color=color,
        linewidth=1.8,
        mutation_scale=14,
        shrinkA=0, shrinkB=0,
    ))


# (cycle arrows are now drawn by ``draw_labeled_cycle_arrow`` above —
#  the standalone arrow / standalone enzyme pair is collapsed into one
#  ``labeled_arrow`` call.)


def build_krebs_figure() -> tuple[Path, Path]:
    apply_rcparams()
    fig, ax = figure(figsize=(9.5, 9.5))

    # ---- Title in the CENTER of the cycle (textbook convention; frees
    # up the outer ring for chips + arrows without competing for the
    # top of the figure). The cycle's empty interior is the natural
    # place for the diagram's name.
    ax.text(CENTER[0], CENTER[1] + 3.2, "Krebs cycle",
            ha="center", va="center",
            color=P.TEXT, fontsize=18, fontweight="bold")
    ax.text(CENTER[0], CENTER[1] - 1.5, "TCA / citric acid cycle",
            ha="center", va="center",
            color=P.SUBTLE, fontsize=11.0)
    ax.text(CENTER[0], CENTER[1] - 5.0, "central pathway of aerobic respiration",
            ha="center", va="center",
            color=P.SUBTLE, fontsize=9.0, style="italic")

    # ---- Cycle arrows + enzyme labels in one pass (labeled_arrow).
    # Drawn BEFORE molecules so pills overlay the arrow endpoints.
    for i in range(N):
        draw_labeled_cycle_arrow(ax, i, (i + 1) % N, ENZYMES[i])

    # ---- Molecules ----
    for i, (key, name, formula) in enumerate(MOLECULES):
        draw_molecule(ax, i, name, formula)

    # ---- Byproducts and inputs ----
    # For multi-byproduct steps, each arrow gets its OWN anchor at the
    # same tangent offset as its chip. The arrows then run PARALLEL
    # outward — they don't fan from a single shared anchor point,
    # which used to make the arrows visually merge / overlap near the
    # cycle before diverging at the chips.
    for i in range(N):
        mx, my, nx, ny = arc_midpoint(i, (i + 1) % N)
        tx, ty = -ny, nx  # tangent (perpendicular to outward)

        bp_list = BYPRODUCTS[i]
        for j, (label, color) in enumerate(bp_list):
            tangent_d = (j - (len(bp_list) - 1) / 2) * BYP_TANGENT
            cx = mx + nx * BYP_OFFSET + tx * tangent_d
            cy = my + ny * BYP_OFFSET + ty * tangent_d
            anchor_x = mx + nx * 4.0 + tx * tangent_d
            anchor_y = my + ny * 4.0 + ty * tangent_d
            draw_side_chip(ax, cx, cy, label, color, dashed=True)
            # Arrow terminates JUST OUTSIDE the chip's perimeter (margin
            # 1.0 axis units of breathing room) — the arrowhead then
            # reads cleanly as "produced by the cycle, lands at the
            # chip's doorstep" without touching or overlapping the chip.
            end_x, end_y = pill_edge(cx, cy, CHIP_W, CHIP_H,
                                     anchor_x, anchor_y, margin=1.0)
            draw_side_arrow(ax, anchor_x, anchor_y, end_x, end_y, color)

        in_list = INPUTS[i]
        for j, (label, color) in enumerate(in_list):
            tangent_d = (j - (len(in_list) - 1) / 2) * BYP_TANGENT
            cx = mx + nx * BYP_OFFSET + tx * tangent_d
            cy = my + ny * BYP_OFFSET + ty * tangent_d
            anchor_x = mx + nx * 4.0 + tx * tangent_d
            anchor_y = my + ny * 4.0 + ty * tangent_d
            draw_side_chip(ax, cx, cy, label, color, dashed=False)
            # Input arrow STARTS just outside the chip's edge (same
            # breathing room as byproducts), and the arrowhead points
            # INTO the cycle — the asymmetric direction encodes
            # "consumed by the reaction" vs the byproduct's "produced".
            start_x, start_y = pill_edge(cx, cy, CHIP_W, CHIP_H,
                                         anchor_x, anchor_y, margin=1.0)
            draw_side_arrow(ax, start_x, start_y, anchor_x, anchor_y, color)

    # ---- Legend block (top-left corner) ----
    legend_specs = [
        (P.DET,       False, "Intermediate",  "metabolite (passive)"),
        (P.ACCENT,    False, "Catalyst",      "enzyme (italic)"),
        (P.ACCENT_2,  False, "Energy carrier","NADH / FADH2 / GTP"),
        (P.ACCENT_3,  False, "Waste",         "CO2"),
        (P.ACCENT_5,  False, "Input",         "acetyl-CoA"),
    ]
    # Legend in the BOTTOM-LEFT empty quadrant. The fumarate→malate
    # step has no byproducts (it's just hydration), so the outer arc
    # there is clear — and there's no upper-quadrant byproduct chip
    # in the way (malate DH's NADH is upper-LEFT, would have collided
    # with a top-left legend).
    legend_block(ax, x=1.5, y_top=18, specs=legend_specs,
                 title="Style key",
                 chip_w=3.8, chip_h=2.0, row_gap=0.7,
                 label_fontsize=9.0, title_fontsize=10.0)

    # ---- Source caption ----
    ax.text(99, 1, "source: examples/krebs_cycle_example.py",
            ha="right", va="bottom",
            color=P.SUBTLE, fontsize=7)

    svg_safe(ax)

    plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    out = Path(__file__).resolve().parent
    svg_path = out / "krebs_cycle_example.svg"
    png_path = out / "krebs_cycle_example.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return svg_path, png_path


def main() -> int:
    svg, png = build_krebs_figure()
    print(f"wrote {svg}")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
