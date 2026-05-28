"""Lifecycle figure — *graphviz-driven layout* version.

Same stages and edges as `lifecycle_example.py`, but the geometry is
computed by `dot` (via `pavlab_arch.autolayout`) rather than by hand.
The visual style — `stage_box`, palette, fonts, ⚙ glyph — is unchanged;
graphviz is used purely as a layout engine.

Graphviz parameters (driven by the prompt — "left-to-right pipeline,
boxes ≈ 1.5" wide, generous spacing"):

    rankdir = "LR"        # left-to-right pipeline
    splines = "spline"    # smooth curved edges, dot routes around boxes
    nodesep = 0.5         # tight vertical gap between fork lanes
    ranksep = 0.7         # column spacing
    engine  = "dot"       # the right engine for DAG / pipeline shapes

The fork (`loaded → {curate, process}`) and join (`{curate, process} →
audit`) emerge automatically — dot puts curate and process at the same
rank because they have the same predecessor and the same successor.
The recuration loop-back (`audit → curate`) is drawn with
`constraint=false` so it doesn't force `audit` to be drawn before
`curate`.

Outputs:
    lifecycle_autolayout_example.svg
    lifecycle_autolayout_example.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.autolayout import (  # noqa: E402
    GraphSpec, bezier_polyline, layout_graph,
)
from pavlab_arch.layout import svg_safe  # noqa: E402
from pavlab_arch.primitives import stage_box  # noqa: E402
from pavlab_arch.style import apply_rcparams  # noqa: E402


# (key, label, subtitle, color, is_det)
STAGES = [
    ("discovery", "Discovery", "scrape + ID list",            P.DET,      True),
    ("candidate", "Candidate", "AI recommend · human triage", P.ACCENT_3, False),
    ("skeleton",  "Skeleton",  "Investigation + proposal",    P.ACCENT,   False),
    ("loaded",    "Loaded",    "auto-load + autofill",        P.DET,      True),
    ("curate",    "Curate",    "Proposer + review",           P.ACCENT,   False),
    ("process",   "Process",   "QC · alignment · DEA",        P.DET,      True),
    ("audit",     "Audit",     "Auditor + dispositions",      P.ACCENT,   False),
    ("public",    "Public",    "release gate",                P.ACCENT_3, False),
]
STAGE_INFO = {k: (label, subtitle, color, is_det)
              for k, label, subtitle, color, is_det in STAGES}

FORWARD_EDGES = [
    ("discovery", "candidate"),
    ("candidate", "skeleton"),
    ("skeleton",  "loaded"),
    ("loaded",    "curate"),
    ("loaded",    "process"),
    ("curate",    "audit"),
    ("process",   "audit"),
    ("audit",     "public"),
]
LOOPBACK = ("audit", "curate")


# Box dimensions in inches — these go straight to graphviz, then we render
# stage_box at exactly the size dot reserved.
BOX_W = 1.55
BOX_H = 0.95


def build_lifecycle_figure() -> tuple[Path, Path]:
    apply_rcparams()

    # ---- 1. Hand the graph to dot. ------------------------------------
    g = GraphSpec(rankdir="LR", splines="spline", nodesep=0.5, ranksep=0.7)
    for key, *_ in STAGES:
        g.add_node(key, width=BOX_W, height=BOX_H)
    for src, dst in FORWARD_EDGES:
        g.add_edge(src, dst)
    # The loop-back goes "backwards" in the rank order; tell dot it must
    # not influence layout, so audit still ends up to the right of curate.
    g.add_edge(LOOPBACK[0], LOOPBACK[1], constraint="false")

    laid = layout_graph(g)
    bbox_w, bbox_h = laid.bbox

    # ---- 2. Figure sized to the laid-out bounding box. ----------------
    margin = 0.4
    title_h = 0.9
    bottom_pad = 0.25  # source line only — labels now sit on the arcs
    fig_w = bbox_w + 2 * margin
    fig_h = bbox_h + 2 * margin + title_h + bottom_pad
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")

    # ---- 3. Title strip. ----------------------------------------------
    ax.text(margin, fig_h - 0.2,
            "Generic curation workflow — experiment lifecycle",
            ha="left", va="top", color=P.TEXT,
            fontsize=14.0, fontweight="bold")
    ax.text(margin, fig_h - 0.55,
            "Layout via graphviz (dot, rankdir=LR, splines=spline)",
            ha="left", va="top", color=P.SUBTLE, fontsize=10.0)

    # Offset that translates dot's data coordinates into our axes.
    # Dot's origin is bottom-left of its bbox.
    ox = margin
    oy = margin + bottom_pad

    # ---- 4. Draw the edges first (so boxes overdraw the joins). -------
    loopback_poly: list[tuple[float, float]] | None = None
    for src, dst, pts in laid.edge_paths():
        poly = bezier_polyline(pts, samples_per_segment=18)
        if not poly:
            continue
        verts = [(x + ox, y + oy) for x, y in poly]
        is_loopback = (src, dst) == LOOPBACK
        color = P.ACCENT_4 if is_loopback else P.SUBTLE
        lw = 2.0
        if len(verts) >= 2:
            codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(verts) - 1)
            ax.add_patch(PathPatch(
                MplPath(verts, codes),
                facecolor="none", edgecolor=color, linewidth=lw,
                capstyle="round", joinstyle="round",
            ))
            x_pen, y_pen = verts[-2]
            x_end, y_end = verts[-1]
            ax.add_patch(FancyArrowPatch(
                (x_pen, y_pen), (x_end, y_end),
                arrowstyle="-|>", color=color, mutation_scale=14,
                linewidth=lw, shrinkA=0, shrinkB=0,
            ))
        if is_loopback:
            loopback_poly = verts

    # ---- 5. Draw the boxes on top. ------------------------------------
    # The dot output gives us node centre + width/height in inches; we
    # convert to stage_box's (lower-left x, lower-left y, w, h).
    for key in STAGE_INFO:
        cx, cy, w, h = laid.nodes[key]
        x = cx - w / 2 + ox
        y = cy - h / 2 + oy
        label, subtitle, color, is_det = STAGE_INFO[key]
        stage_box(ax, x, y, w, h, label, color,
                  is_det=is_det, subtitle=subtitle)

    # ---- 6. Recuration-loop label — anchored at the loop endpoints'
    # local box top, not the figure-wide row top.
    if loopback_poly:
        src, dst = LOOPBACK
        local_top = max(laid.nodes[k][1] + laid.nodes[k][3] / 2
                        for k in (src, dst)) + oy
        mx, _ = loopback_poly[len(loopback_poly) // 2]
        ax.text(mx, local_top + 0.08, "recuration loop",
                ha="center", va="bottom", color=P.ACCENT_4,
                fontsize=9.5, style="italic", fontweight="bold")

    # Source caption (bottom-right).
    ax.text(fig_w - margin, 0.1,
            "source: examples/lifecycle_autolayout_example.py",
            ha="right", va="bottom", color=P.SUBTLE, fontsize=8.0)

    svg_safe(ax)
    plt.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)

    out = Path(__file__).resolve().parent
    svg_path = out / "lifecycle_autolayout_example.svg"
    png_path = out / "lifecycle_autolayout_example.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    return svg_path, png_path


def main() -> int:
    svg, png = build_lifecycle_figure()
    print(f"wrote {svg}")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
