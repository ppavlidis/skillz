"""Methods-comparison figure — three competing pipelines side-by-side.

Rows are alternative approaches to the same task; columns are pipeline
stages; horizontal bar gauges on the right show per-method F1 broken
into two sub-metrics. One row uses an ensemble proposer (two parallel
mini-boxes instead of a single box) to demonstrate that primitive.

Demonstrates:
  - `stage_box` for both LLM and deterministic (⚙) stages
  - `ensemble_proposer` for the "two proposers in parallel" pattern
  - `perf_gauge` with the luminosity-balanced `BAR_FACTOR` /
    `BAR_TAG` palette + an optional curator-corrected overlay
  - Right-aligned method labels flush against the first column
  - Per-column stage widths (Proposer wider than Refine/Apply)

Outputs:
    methods_comparison_example.svg
    methods_comparison_example.png
"""
from __future__ import annotations
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

import matplotlib.pyplot as plt  # noqa: E402

from pavlab_arch.style import apply_rcparams  # noqa: E402
from pavlab_arch.layout import svg_safe  # noqa: E402
from pavlab_arch.palette import (  # noqa: E402
    ACCENT, ACCENT_3, ACCENT_4, DET,
    BAR_FACTOR, BAR_TAG, TEXT,
)
from pavlab_arch.primitives import (  # noqa: E402
    stage_box, perf_gauge, ensemble_proposer, arrow,
)


# Each row:
#   (name, [stage_or_None_per_column], primary_F1, secondary_F1,
#    primary_curator_F1_or_None, secondary_curator_F1_or_None)
# Each `stage` is either:
#   - None              (column unused for this row)
#   - (label, color, subtitle)   for a single stage_box
#   - ((label, color), (label, color))   for an ensemble_proposer
METHODS = [
    ("Baseline",
     [("one-shot", ACCENT, "single LLM"),
      ("Rules",    DET,    "+ resolver"),
      None,
      None,
      None],
     0.793, 0.300, None, None),
    ("Reviewed pipeline",
     [("one-shot", ACCENT,   "primary LLM"),
      ("Rules",    DET,      "+ resolver"),
      ("Reviewer", ACCENT_3, "second LLM"),
      ("Boss",     ACCENT_4, "+ context"),
      ("Apply",    DET,      None)],
     0.866, 0.696, None, None),
    ("Ensemble + review",
     [(("subagents + debate", ACCENT_3),
       ("one-shot",            ACCENT)),
      ("Rules",    DET,      "+ resolver"),
      ("Reviewer", ACCENT_3, "second LLM"),
      ("Boss",     ACCENT_4, "+ context"),
      ("Apply",    DET,      None)],
     0.933, 0.652, 0.818, 0.977),
]


def main() -> int:
    apply_rcparams()
    n = len(METHODS)
    row_h = 0.62
    row_gap = 0.10
    fig_h = 0.7 + n * (row_h + row_gap) + 0.7

    fig, ax = plt.subplots(figsize=(14, fig_h))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, fig_h)
    ax.set_xticks([])
    ax.set_yticks([])

    # Column geometry — widths tuned so each label fits without
    # overflow. (`stage_box` will also auto-shrink any stragglers.)
    col_xs   = [27, 38, 45, 52, 61]
    col_ws   = [10,  6,  6,  8,  6]
    col_kind = ["llm", "det", "llm", "llm", "det"]
    col_labels = ["Proposer", "Refine", "Reviewer", "Boss", "Apply"]
    GAUGE_X = 70
    gauge_w = 22
    gauge_h = 0.18

    header_y = fig_h - 0.32
    for x, w, lbl in zip(col_xs, col_ws, col_labels):
        ax.text(x + w / 2, header_y, lbl,
                ha="center", va="center", fontsize=10,
                color=TEXT, fontweight="bold")
    ax.text(GAUGE_X, header_y,        "primary F1",
            ha="left", va="center", fontsize=10.5, color=TEXT, fontweight="bold")
    ax.text(GAUGE_X, header_y - 0.18, "secondary F1",
            ha="left", va="center", fontsize=10.5, color=TEXT, fontweight="bold")

    for i, (name, stages, fF, tF, curF, curT) in enumerate(METHODS):
        y_top = fig_h - 0.7 - (i + 1) * (row_h + row_gap) + row_gap
        y_center = y_top + row_h / 2

        # Right-aligned method name flush against the first column
        ax.text(col_xs[0] - 1.0, y_center, name,
                ha="right", va="center", fontsize=12,
                color=TEXT, fontweight="bold")

        prev_right = None
        for col_i, stage in enumerate(stages):
            if stage is None:
                continue
            x = col_xs[col_i]
            w = col_ws[col_i]
            if (isinstance(stage, tuple) and len(stage) == 2
                    and isinstance(stage[0], tuple)):
                # ensemble proposer: (top, bot) each (label, color)
                ensemble_proposer(ax, x, y_top + 0.04, w, row_h - 0.08,
                                  top=stage[0], bot=stage[1])
            else:
                label, color, subtitle = stage
                is_det = col_kind[col_i] == "det"
                stage_box(ax, x, y_top + 0.04, w, row_h - 0.08,
                          label, color, is_det=is_det, subtitle=subtitle)
            if prev_right is not None:
                arrow(ax, prev_right + 0.12, y_center,
                      x - 0.12, y_center)
            prev_right = x + w

        # Two stacked gauges on the right
        perf_gauge(ax, GAUGE_X, y_center + 0.07, gauge_w, gauge_h,
                   fF, color=BAR_FACTOR, curator_value=curF)
        perf_gauge(ax, GAUGE_X, y_center - 0.22, gauge_w, gauge_h,
                   tF, color=BAR_TAG, curator_value=curT)

    svg_safe(ax)
    out = Path(__file__).resolve().parent / "methods_comparison_example.svg"
    fig.savefig(out, format="svg", bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), format="png", dpi=150,
                bbox_inches="tight")
    print(f"wrote {out} (+ .png)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
