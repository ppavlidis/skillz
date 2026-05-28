"""IC vehicle assembly figure — graphviz-driven layout version.

Same stages and edges as `ic_car_assembly_example.py`, but the geometry
is computed by `dot` via `pavlab_arch.autolayout`. The hand-laid
version is kept in the repo for side-by-side comparison.

Graphviz parameters (from the prompt — "left-to-right assembly line,
body line on top, powertrain on bottom, wide tight columns"):

    rankdir = "LR"
    splines = "spline"
    nodesep = 0.45        # tight gap between body/powertrain lanes
    ranksep = 0.65        # column spacing
    engine  = "dot"

Two long feedback edges are marked `constraint=false` so they don't
distort the assembly-line layout:

    qc   → final   (rework loop, in-shift)
    ship → design  (recall loop, post-shipment)

Outputs:
    ic_car_assembly_autolayout_example.svg
    ic_car_assembly_autolayout_example.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.autolayout import (  # noqa: E402
    GraphSpec, bezier_polyline, layout_graph,
)
from pavlab_arch.layout import svg_safe  # noqa: E402
from pavlab_arch.primitives import dual_stage_box, stage_box  # noqa: E402
from pavlab_arch.style import apply_rcparams  # noqa: E402


# (key, label, subtitle, color_or_tuple, is_det)
STAGES = [
    ("design",   "Design",         "engineering + CAD",          P.ACCENT_3,        False),
    ("press",    "Press shop",     "stamping",                   P.DET,             True),
    ("block",    "Engine block",   "cast · machine",             P.DET,             True),
    ("weld",     "Body welding",   "robot weld to BIW",          P.DET,             True),
    ("engine",   "Engine asm",     "block · head · accessories", P.ACCENT,          False),
    ("paint",    "Paint shop",     "e-coat · primer · topcoat",  P.DET,             True),
    ("ptrain",   "Powertrain",     "transmission · drivetrain",  P.ACCENT,          False),
    ("marriage", "Marriage",       "body onto chassis",          (P.DET, P.ACCENT), False),
    ("final",    "Final assembly", "trim · wiring · fluids",     P.ACCENT,          False),
    ("qc",       "QC + test",      "dyno · road · audit",        P.ACCENT_3,        False),
    ("ship",     "Ship",           "logistics to dealer",        P.DET,             True),
]
STAGE_INFO = {k: (label, subtitle, color, is_det)
              for k, label, subtitle, color, is_det in STAGES}

FORWARD_EDGES = [
    ("design",   "press"),
    ("design",   "block"),
    ("press",    "weld"),
    ("block",    "engine"),
    ("weld",     "paint"),
    ("engine",   "ptrain"),
    ("paint",    "marriage"),
    ("ptrain",   "marriage"),
    ("marriage", "final"),
    ("final",    "qc"),
    ("qc",       "ship"),
]
REWORK = ("qc", "final")
RECALL = ("ship", "design")


BOX_W = 1.65
BOX_H = 1.05


def build_car_figure() -> tuple[Path, Path]:
    apply_rcparams()

    # ---- 1. Layout via dot. -------------------------------------------
    g = GraphSpec(rankdir="LR", splines="spline", nodesep=0.45, ranksep=0.65)
    for key, *_ in STAGES:
        g.add_node(key, width=BOX_W, height=BOX_H)
    for src, dst in FORWARD_EDGES:
        g.add_edge(src, dst)
    # Feedback edges: don't pull on layout.
    g.add_edge(REWORK[0], REWORK[1], constraint="false")
    g.add_edge(RECALL[0], RECALL[1], constraint="false")

    laid = layout_graph(g)
    bbox_w, bbox_h = laid.bbox

    # ---- 2. Figure sized to the laid-out bounding box. ----------------
    margin = 0.4
    title_h = 0.95
    bottom_pad = 0.25  # just enough for the source line
    fig_w = bbox_w + 2 * margin
    fig_h = bbox_h + 2 * margin + title_h + bottom_pad
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")

    ax.text(margin, fig_h - 0.18,
            "Internal-combustion vehicle assembly — production architecture",
            ha="left", va="top", color=P.TEXT,
            fontsize=14.0, fontweight="bold")
    ax.text(margin, fig_h - 0.52,
            "Layout via graphviz (dot, rankdir=LR, splines=spline) — "
            "body + powertrain emerge from the edge graph",
            ha="left", va="top", color=P.SUBTLE, fontsize=10.0)

    ox = margin
    oy = margin + bottom_pad

    # ---- 3. Edges. ----------------------------------------------------
    # Stash each loop edge's polyline so we can drop the label on the
    # actual path (avoiding the "stranded in dead space" problem).
    loop_polylines: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for src, dst, pts in laid.edge_paths():
        poly = bezier_polyline(pts, samples_per_segment=18)
        if not poly:
            continue
        verts = [(x + ox, y + oy) for x, y in poly]
        is_rework = (src, dst) == REWORK
        is_recall = (src, dst) == RECALL
        color = P.ACCENT_4 if (is_rework or is_recall) else P.SUBTLE
        linestyle = (0, (5, 3)) if is_recall else "-"
        lw = 2.0
        if len(verts) >= 2:
            codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(verts) - 1)
            ax.add_patch(PathPatch(
                MplPath(verts, codes),
                facecolor="none", edgecolor=color, linewidth=lw,
                linestyle=linestyle,
                capstyle="round", joinstyle="round",
            ))
            x_pen, y_pen = verts[-2]
            x_end, y_end = verts[-1]
            ax.add_patch(FancyArrowPatch(
                (x_pen, y_pen), (x_end, y_end),
                arrowstyle="-|>", color=color, mutation_scale=14,
                linewidth=lw, linestyle=linestyle,
                shrinkA=0, shrinkB=0,
            ))
        if is_rework or is_recall:
            loop_polylines[(src, dst)] = verts

    # ---- 4. Boxes. ----------------------------------------------------
    for key, (label, subtitle, color, is_det) in STAGE_INFO.items():
        cx, cy, w, h = laid.nodes[key]
        x = cx - w / 2 + ox
        y = cy - h / 2 + oy
        if isinstance(color, tuple):
            dual_stage_box(ax, x, y, w, h, label,
                           color[0], color[1], subtitle=subtitle)
        else:
            stage_box(ax, x, y, w, h, label, color,
                      is_det=is_det, subtitle=subtitle)

    # ---- 5. Loop labels — anchored to the edge polylines + the
    # *local* box tops of the loop's endpoints (not the figure-wide
    # row top, which can be far above the endpoints when the figure
    # has a parallel-lane region above them).
    def _local_box_top(*keys: str) -> float:
        return max(laid.nodes[k][1] + laid.nodes[k][3] / 2 for k in keys) + oy

    def _mid_point(poly):
        return poly[len(poly) // 2] if poly else None

    rework_poly = loop_polylines.get(REWORK)
    if rework_poly:
        mx, _ = _mid_point(rework_poly)
        y = _local_box_top("qc", "final") + 0.08
        ax.text(mx, y, "rework loop",
                ha="center", va="bottom", color=P.ACCENT_4,
                fontsize=9.5, style="italic", fontweight="bold")

    recall_poly = loop_polylines.get(RECALL)
    if recall_poly:
        # Long sweeping arc below the row — the polyline min-y is a
        # real apex; label sits just below it.
        apex = min(recall_poly, key=lambda p: p[1])
        ax.text(apex[0], apex[1] - 0.12, "recall feedback",
                ha="center", va="top", color=P.ACCENT_4,
                fontsize=9.0, style="italic", fontweight="bold")

    ax.text(fig_w - margin, 0.12,
            "source: examples/ic_car_assembly_autolayout_example.py",
            ha="right", va="bottom", color=P.SUBTLE, fontsize=8.0)

    svg_safe(ax)
    plt.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)

    out = Path(__file__).resolve().parent
    svg_path = out / "ic_car_assembly_autolayout_example.svg"
    png_path = out / "ic_car_assembly_autolayout_example.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    return svg_path, png_path


def main() -> int:
    svg, png = build_car_figure()
    print(f"wrote {svg}")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
