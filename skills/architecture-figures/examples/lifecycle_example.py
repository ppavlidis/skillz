"""Lifecycle figure — generic experiment-lifecycle diagram.

Simplified, genericized version of the lifecycle figure that motivated
this skill: a left-to-right chain of states, with a parallel-tracks
fork-join (curate / process), a right-to-left recuration loop-back arc
between the last two states, a cross-cutting layer below for ad-hoc
work streams (tickets + evaluations) that target any state, and a
legend.

Demonstrates:
  - Linear progression + fork-join + feedback-loop arc in one figure
  - `arc3` rad-sign discipline (negative rad → loop bows downward)
  - Dashed up-arrows from a cross-cutting band into the main row
  - Auto-fitting label text via `stage_box` (default `fit=True`)
  - The `wide_half` canonical figure shape (15×7.4 here — slightly
    taller than the default 14×4.7 to fit the cross-cutting layer)

Outputs:
    lifecycle_example.svg
    lifecycle_example.png
"""
from __future__ import annotations
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch  # noqa: E402

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.layout import figure, svg_safe  # noqa: E402
from pavlab_arch.primitives import (  # noqa: E402
    arrow, lane_arrow, stage_box, legend_block,
)
from pavlab_arch.style import apply_rcparams  # noqa: E402


# Stage list — single source of truth.
# (key, label, subtitle, color, is_det, col, lane)
#   col:  0..N column index along the lifecycle axis
#   lane: 0 = top track, 1 = bottom track (parallel-tracks region only)
# Color encodes the actor / mode of work:
#   ACCENT   (blue) — agent-driven (proposer, auditor)
#   ACCENT_3 (amber) — human-in-the-loop decision
#   DET      (slate, gear glyph) — deterministic pipeline
STAGES = [
    ("discovery",  "Discovery",  "scrape + ID list",              P.DET,      True,  0, 0),
    ("candidate",  "Candidate",  "AI recommend · human triage",   P.ACCENT_3, False, 1, 0),
    ("skeleton",   "Skeleton",   "Investigation + proposal",      P.ACCENT,   False, 2, 0),
    ("loaded",     "Loaded",     "auto-load + autofill",          P.DET,      True,  3, 0),
    ("curate",     "Curate",     "Proposer + review",             P.ACCENT,   False, 4, 0),
    ("process",    "Process",    "QC · alignment · DEA",          P.DET,      True,  4, 1),
    ("audit",      "Audit",      "Auditor + dispositions",        P.ACCENT,   False, 5, 0),
    ("public",     "Public",     "release gate",                  P.ACCENT_3, False, 6, 0),
]
N_COLS = 7

FORWARD_EDGES = [
    ("discovery", "candidate"),
    ("candidate", "skeleton"),
    ("skeleton",  "loaded"),
    ("loaded",    "curate"),    # fork — top
    ("loaded",    "process"),   # fork — bottom
    ("curate",    "audit"),     # join — top
    ("process",   "audit"),     # join — bottom
    ("audit",     "public"),
]


def build_lifecycle_figure() -> tuple[Path, Path]:
    apply_rcparams()
    # wide_half-ish but a touch taller for the cross-cutting layer.
    fig, ax = figure(figsize=(15.0, 7.4))

    # ---- Title strip ----
    ax.text(0.5, 96,
            "Generic curation workflow — experiment lifecycle",
            ha="left", va="top", color=P.TEXT, fontsize=15.5, fontweight="bold")
    ax.text(0.5, 92,
            "From discovery to public release, with AI assistance at every state",
            ha="left", va="top", color=P.SUBTLE, fontsize=11.0)

    # ---- Inputs strip (top-left, feeds into Discovery) ----
    in_x, in_y = 1.5, 73
    for j, lbl in enumerate(["date-range scrape", "ID list"]):
        ax.add_patch(FancyBboxPatch(
            (in_x, in_y + (1 - j) * 4.5), 11, 3.6,
            boxstyle="round,pad=0,rounding_size=0.04",
            linewidth=1.2, edgecolor=P.SUBTLE, facecolor="white",
        ))
        ax.text(in_x + 5.5, in_y + (1 - j) * 4.5 + 1.8, lbl,
                ha="center", va="center", color=P.TEXT, fontsize=10.0)

    # ---- Main lifecycle — column-and-lane grid ----
    row_x0 = 14.0
    row_x1 = 99.0
    gap = 1.4
    stage_w = (row_x1 - row_x0 - gap * (N_COLS - 1)) / N_COLS
    stage_h = 10.0
    lane_y = {0: 75.0, 1: 56.5}

    centres: dict[str, tuple[float, float, float, float]] = {}
    for key, label, subtitle, color, is_det, col, lane in STAGES:
        x = row_x0 + col * (stage_w + gap)
        y = lane_y[lane]
        stage_box(ax, x, y, stage_w, stage_h, label, color,
                  is_det=is_det, subtitle=subtitle)
        centres[key] = (x, y, stage_w, stage_h)

    # Forward arrows — `lane_arrow` handles same-lane vs cross-lane
    # routing. Cross-lane edges (fork: loaded → process; join: process
    # → audit) render as smooth L-shapes via `angle3` rather than the
    # historical small-rad `arc3` that produced visibly-bent paths on
    # short chords.
    for src, dst in FORWARD_EDGES:
        lane_arrow(ax, centres[src], centres[dst],
                   color=P.SUBTLE, lw=2.0, mut=14)

    # Input arrows into Discovery (two short stubs)
    xd, yd, wd, hd = centres["discovery"]
    arrow(ax, in_x + 11 + 0.2, yd + hd / 2 + 2.0, xd - 0.05, yd + hd / 2 + 1.2,
          color=P.SUBTLE, lw=1.6, mut=12)
    arrow(ax, in_x + 11 + 0.2, yd + hd / 2 - 2.0, xd - 0.05, yd + hd / 2 - 1.2,
          color=P.SUBTLE, lw=1.6, mut=12)

    # ---- Recuration loop — Audit → Curate, routed BELOW the row.
    # arc3 rad-sign rule (see SKILL.md "Lifecycle state diagrams"):
    # for a right-to-left arrow, negative rad bows DOWN (clear of the
    # row); positive bows UP (over the title strip — bad).
    xa, ya, wa, ha = centres["audit"]
    xc, yc, wc, hc = centres["curate"]
    arrow(ax, xa + wa * 0.2, ya, xc + wc * 0.8, yc,
          color=P.ACCENT_4, lw=2.2, mut=16,
          connectionstyle="arc3,rad=-0.55")
    # Park the label OFF the arc (short chord, would collide with apex).
    ax.text(xa + wa * 0.9, ya - 3.5, "recuration loop",
            ha="left", va="top", color=P.ACCENT_4, fontsize=10.0,
            style="italic", fontweight="bold")

    # ---- Cross-cutting layer — task tickets + evaluations ----
    cross_y_top = 38.0
    cross_y_bot = 22.0
    cross_h = 11.0
    cross_x = 14.0
    cross_w = row_x1 - cross_x

    # Container card behind both rows for visual grouping
    ax.add_patch(FancyBboxPatch(
        (cross_x - 0.5, cross_y_bot - 1.5),
        cross_w + 1.0, (cross_y_top - cross_y_bot) + cross_h + 3.0,
        boxstyle="round,pad=0,rounding_size=0.04",
        linewidth=1.2, edgecolor=P.GRID, facecolor=P.SOFT_BG,
    ))
    ax.text(cross_x + 0.5, cross_y_top + cross_h + 0.4,
            "Cross-cutting work streams — target any lifecycle state",
            ha="left", va="bottom", color=P.SUBTLE, fontsize=10.5, style="italic")

    # Task tickets row
    ax.text(cross_x + 0.5, cross_y_top + cross_h / 2, "Task\ntickets",
            ha="left", va="center", color=P.TEXT, fontsize=11.0, fontweight="bold")
    ticket_labels = [
        "needs alignment\nto reference",
        "outlier review",
        "batch confound\nrevisit",
        "publication\nrelink",
        "tag drift\nsweep",
    ]
    t_x = cross_x + 8.5
    t_w = (cross_w - 9.0) / len(ticket_labels) - 1.0
    for i, lbl in enumerate(ticket_labels):
        bx = t_x + i * (t_w + 1.0)
        ax.add_patch(FancyBboxPatch(
            (bx, cross_y_top), t_w, cross_h,
            boxstyle="round,pad=0,rounding_size=0.10",
            linewidth=1.4, edgecolor=P.ACCENT_3, facecolor=P.tint(P.ACCENT_3),
        ))
        ax.text(bx + t_w / 2, cross_y_top + cross_h / 2, lbl,
                ha="center", va="center", color=P.TEXT, fontsize=9.5)

    # Evaluations row
    ax.text(cross_x + 0.5, cross_y_bot + cross_h / 2, "Evaluations",
            ha="left", va="center", color=P.TEXT, fontsize=11.0, fontweight="bold")
    eval_labels = [
        "holdout set\n(this work)",
        "calibration\npackage",
        "ablation\n(component on/off)",
        "inter-reviewer\nagreement",
        "regression\nguardrail",
    ]
    for i, lbl in enumerate(eval_labels):
        bx = t_x + i * (t_w + 1.0)
        ax.add_patch(FancyBboxPatch(
            (bx, cross_y_bot), t_w, cross_h,
            boxstyle="round,pad=0,rounding_size=0.10",
            linewidth=1.4, edgecolor=P.ACCENT_5, facecolor=P.tint(P.ACCENT_5),
        ))
        ax.text(bx + t_w / 2, cross_y_bot + cross_h / 2, lbl,
                ha="center", va="center", color=P.TEXT, fontsize=9.5)

    # Dashed up-arrows from the cross-cutting layer into the lifecycle.
    def _dashed_up(x_from, y_from, x_to, y_to, color):
        ax.add_patch(FancyArrowPatch(
            (x_from, y_from), (x_to, y_to),
            arrowstyle="-|>", color=color, linewidth=1.8,
            mutation_scale=14, linestyle=(0, (4, 2.5)),
            shrinkA=0, shrinkB=0,
        ))

    xp, yp, wp, hp = centres["process"]
    xau, yau, wau, hau = centres["audit"]
    xcu, ycu, wcu, hcu = centres["curate"]
    _dashed_up(xp + wp / 2, cross_y_top + cross_h, xp + wp / 2, yp - 0.5, P.ACCENT_3)
    _dashed_up(xau + wau / 2, cross_y_top + cross_h, xau + wau / 2, yau - 0.5, P.ACCENT_3)
    _dashed_up(xcu + wcu / 2, cross_y_bot + cross_h, xcu + wcu / 2, cross_y_top - 0.5, P.ACCENT_5)
    _dashed_up(xau + wau / 2, cross_y_bot + cross_h, xau + wau / 2, cross_y_top - 0.5, P.ACCENT_5)

    # ---- Legend block — compact vertical chip + text-to-the-right.
    # Placed in the bottom-left margin below the cross-cutting container.
    legend_specs = [
        (P.ACCENT,   False, "Agent (LLM)",   "proposer · auditor"),
        (P.DET,      True,  "Deterministic", "pipelines"),
        (P.ACCENT_3, False, "Human review",  "decision-in-the-loop"),
        (P.ACCENT_5, False, "Evaluation",    "benchmarks, ablations"),
        (P.ACCENT_4, False, "Recuration",    "loop-back from audit"),
    ]
    legend_block(ax, x=cross_x, y_top=18, specs=legend_specs,
                 title="Legend",
                 chip_w=3.5, chip_h=1.8, row_gap=0.5,
                 label_fontsize=10.0, title_fontsize=10.5)

    # Source caption (bottom-right)
    ax.text(99.5, 0.5, "source: examples/lifecycle_example.py",
            ha="right", va="bottom", color=P.SUBTLE, fontsize=9.0)

    # Strip <clipPath> wrappers before save — see SKILL.md SVG round-trip rules.
    svg_safe(ax)

    plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    out = Path(__file__).resolve().parent
    svg_path = out / "lifecycle_example.svg"
    png_path = out / "lifecycle_example.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return svg_path, png_path


def main() -> int:
    svg, png = build_lifecycle_figure()
    print(f"wrote {svg}")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
