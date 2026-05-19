"""IC vehicle assembly figure — internal-combustion car production architecture.

Real-world example that exercises every load-bearing primitive in the skill:
  - Fork-join: a single `design` stage forks into parallel body-line and
    powertrain-line lanes that run concurrently for three columns before
    rejoining at `marriage` (the iconic moment where the painted body is
    lowered onto the powertrain on a moving line).
  - `dual_stage_box` for a genuinely co-actor stage (marriage is a hybrid:
    robotic gantry does the lift, a human operator confirms alignment —
    neither colour alone captures it).
  - Three-actor colour grammar adapted from the lifecycle convention to
    physical manufacturing:
      ACCENT   (blue)  → skilled-labor assembly (engine, powertrain, final)
      DET      (slate) → robotic / automated processes (press, weld, paint, ship)
      ACCENT_3 (amber) → engineering decision / inspection (design, QC)
      ACCENT_4 (red)   → rework / recall loop
  - Rework loop from `qc` back to `final` — `arc3,rad<0` so the right→left
    arrow bows DOWN, clear of the assembly row.
  - Same lane-y geometry (top=70, bottom=48) as the lifecycle example so
    the two examples cross-train the eye.

Outputs:
    ic_car_assembly_example.svg
    ic_car_assembly_example.png
"""
from __future__ import annotations
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.layout import figure, svg_safe  # noqa: E402
from pavlab_arch.primitives import (  # noqa: E402
    arrow, stage_box, dual_stage_box, lane_arrow, legend_block,
)
from pavlab_arch.style import apply_rcparams  # noqa: E402


# Stage list — single source of truth.
# (key, label, subtitle, color, is_det, col, lane)
#   color : single hex (stage_box) OR (left, right) tuple (dual_stage_box).
#   col   : 0..N column index along the assembly line.
#   lane  : 0 = top / body line / single-lane states
#           1 = bottom / powertrain line (parallel region only)
STAGES = [
    ("design",   "Design",         "engineering + CAD",          P.ACCENT_3,        False, 0, 0),
    ("press",    "Press shop",     "stamping",                   P.DET,             True,  1, 0),
    ("block",    "Engine block",   "cast · machine",             P.DET,             True,  1, 1),
    ("weld",     "Body welding",   "robot weld to BIW",          P.DET,             True,  2, 0),
    ("engine",   "Engine asm",     "block · head · accessories", P.ACCENT,          False, 2, 1),
    ("paint",    "Paint shop",     "e-coat · primer · topcoat",  P.DET,             True,  3, 0),
    ("ptrain",   "Powertrain",     "transmission · drivetrain",  P.ACCENT,          False, 3, 1),
    ("marriage", "Marriage",       "body onto chassis",          (P.DET, P.ACCENT), False, 4, 0),
    ("final",    "Final assembly", "trim · wiring · fluids",     P.ACCENT,          False, 5, 0),
    ("qc",       "QC + test",      "dyno · road · audit",        P.ACCENT_3,        False, 6, 0),
    ("ship",     "Ship",           "logistics to dealer",        P.DET,             True,  7, 0),
]
N_COLS = 8

FORWARD_EDGES = [
    ("design",   "press"),     # fork — top lane
    ("design",   "block"),     # fork — bottom lane
    ("press",    "weld"),
    ("block",    "engine"),
    ("weld",     "paint"),
    ("engine",   "ptrain"),
    ("paint",    "marriage"),  # join from top
    ("ptrain",   "marriage"),  # join from bottom
    ("marriage", "final"),
    ("final",    "qc"),
    ("qc",       "ship"),
]


def build_car_figure() -> tuple[Path, Path]:
    apply_rcparams()
    fig, ax = figure(figsize=(15.5, 5.5))

    # ---- Title strip ----
    ax.text(0.5, 96,
            "Internal-combustion vehicle assembly — production architecture",
            ha="left", va="top", color=P.TEXT, fontsize=15.5, fontweight="bold")
    ax.text(0.5, 90.5,
            "Body and powertrain lines run in parallel, converging at the marriage point",
            ha="left", va="top", color=P.SUBTLE, fontsize=11.0)

    # ---- Main assembly row — column-and-lane grid ----
    row_x0 = 4.0
    row_x1 = 99.0
    gap = 1.4
    stage_w = (row_x1 - row_x0 - gap * (N_COLS - 1)) / N_COLS
    stage_h = 11.0
    lane_y = {0: 65.0, 1: 38.0}

    centres: dict[str, tuple[float, float, float, float]] = {}
    for key, label, subtitle, color, is_det, col, lane in STAGES:
        x = row_x0 + col * (stage_w + gap)
        y = lane_y[lane]
        if isinstance(color, tuple):
            dual_stage_box(ax, x, y, stage_w, stage_h, label,
                           color[0], color[1], subtitle=subtitle)
        else:
            stage_box(ax, x, y, stage_w, stage_h, label, color,
                      is_det=is_det, subtitle=subtitle)
        centres[key] = (x, y, stage_w, stage_h)

    # Forward arrows — `lane_arrow` handles same-lane vs cross-lane
    # routing. Cross-lane forks/joins use straight diagonals from the
    # source-facing edge to the target-facing edge (no arc3 — short
    # chords with small rad render as bent paths).
    for src, dst in FORWARD_EDGES:
        lane_arrow(ax, centres[src], centres[dst],
                   color=P.SUBTLE, lw=2.0, mut=14)

    # ---- Lane labels (left margin, italic, subtle) ----
    ax.text(row_x0 - 0.5, lane_y[0] + stage_h / 2 + 6.5, "body line",
            ha="left", va="bottom", color=P.SUBTLE, fontsize=8.5, style="italic")
    ax.text(row_x0 - 0.5, lane_y[1] - 2.0, "powertrain line",
            ha="left", va="top", color=P.SUBTLE, fontsize=8.5, style="italic")

    # ---- Rework loop — QC → Final assembly (right→left, short, solid).
    # In-shift defect correction. arc3 rad-sign rule: leftward arrow +
    # negative rad → bows DOWN (clear of the row). Solid red.
    xq, yq, wq, hq = centres["qc"]
    xf, yf, wf, hf = centres["final"]
    arrow(ax,
          xq + wq * 0.25, yq,
          xf + wf * 0.75, yf,
          color=P.ACCENT_4, lw=2.2, mut=16,
          connectionstyle="arc3,rad=-0.5")
    # Park the label OFF the arc apex — short chord, would collide.
    ax.text(xq + wq * 0.9, yq - 4.0, "rework loop",
            ha="left", va="top", color=P.ACCENT_4, fontsize=10.0,
            style="italic", fontweight="bold")

    # ---- Recall loop — Ship → Design (long-span, dashed U-shape).
    # Post-shipment feedback: field defects (warranty claims, NHTSA
    # filings, dealer service reports) re-enter engineering and inform
    # the next production batch. Dashed signals "out-of-band, not on
    # the production line." Routed as an explicit U (down → across →
    # up) rather than a deep arc — a long-span arc3 would either pass
    # through the bottom lane or collide with the legend. The U-shape
    # uses the empty band between bottom lane and legend, and reads
    # unambiguously as a long-range feedback path.
    xs, ys, ws, hs = centres["ship"]
    xd, yd, wd, hd = centres["design"]
    sx = xs + ws * 0.5
    dx = xd + wd * 0.5
    recall_y = 22.0
    dash = (0, (5, 3))
    # Segment 1: vertical down from ship bottom.
    ax.add_line(Line2D([sx, sx], [ys, recall_y],
                       color=P.ACCENT_4, linewidth=2.0, linestyle=dash))
    # Segment 2: horizontal across the bottom of the figure.
    ax.add_line(Line2D([sx, dx], [recall_y, recall_y],
                       color=P.ACCENT_4, linewidth=2.0, linestyle=dash))
    # Segment 3: vertical up to design bottom — arrowhead lives here.
    ax.add_patch(FancyArrowPatch(
        (dx, recall_y), (dx, yd),
        arrowstyle="-|>", color=P.ACCENT_4, linewidth=2.0,
        mutation_scale=16, linestyle=dash,
        shrinkA=0, shrinkB=0,
    ))
    # Label centered above the horizontal segment.
    ax.text((sx + dx) / 2, recall_y + 3.0,
            "recall feedback  ·  warranty · NHTSA · dealer reports",
            ha="center", va="center", color=P.ACCENT_4, fontsize=9,
            style="italic", fontweight="bold")

    # ---- Legend block — compact vertical group, position-parameterised.
    # `(x, y_top)` is the top-left of the block. To relocate the legend
    # elsewhere in this figure or another one, change only these two
    # numbers. The block grows DOWNWARD from y_top and to the RIGHT of
    # x; nothing else needs to move.
    legend_specs = [
        # (color, is_det, label, note) — color may be (left, right) tuple
        (P.ACCENT,            False, "Skilled labor",   "worker assembly"),
        (P.DET,               True,  "Automated",       "robotic / machined"),
        (P.ACCENT_3,          False, "Decision",        "design · inspection"),
        ((P.DET, P.ACCENT),   False, "Hybrid stage",    "robot + worker"),
        (P.ACCENT_4,          False, "Feedback paths",  "rework + recall"),
    ]
    legend_block(ax, x=row_x0, y_top=19.0, specs=legend_specs,
                 title="Actor encoding",
                 chip_w=4.0, chip_h=2.0, row_gap=0.8)

    # Source caption (bottom-right)
    ax.text(99.5, 1.0, "source: examples/ic_car_assembly_example.py",
            ha="right", va="bottom", color=P.SUBTLE, fontsize=9.0)

    # SVG round-trip: strip <clipPath> wrappers before save.
    svg_safe(ax)

    plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    out = Path(__file__).resolve().parent
    svg_path = out / "ic_car_assembly_example.svg"
    png_path = out / "ic_car_assembly_example.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return svg_path, png_path


def main() -> int:
    svg, png = build_car_figure()
    print(f"wrote {svg}")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
