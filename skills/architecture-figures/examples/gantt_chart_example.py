"""Gantt chart example — flat / modern / lab-style schedule chart.

Demonstrates the skill's Gantt primitives:

  - ``GanttTask`` — dataclass holding one row's data (label, planned
    span, done span, status, category).
  - ``gantt_bar`` — three-layer bar: planned background (gray), done
    overlay (emerald), remaining overlay coloured/hatched by status
    (in-flight amber, blocked red hatch, deferred dotted).
  - ``today_line`` — vertical reference line for "now".

The figure itself shows a hypothetical Q3 product roadmap so the
chart reads as a generic schedule, not a specific project — but the
structure is exactly the same as the real-world version that
motivated the primitive (a per-session roadmap of code-modernization
tasks across categories).

Style conventions exercised:
  - Tasks are grouped by ``category``; categories alternate with a
    light row-band shading so the eye can find category boundaries
    without explicit lines.
  - Category labels sit at the right margin, vertically centred on
    each category's row band.
  - X-axis labels are sessions / sprints (any monotonic numeric
    axis works — pass dates encoded as floats if you want a real
    timeline).
  - Y-axis grid is OFF; only the vertical (X-axis) grid is on, in
    ``GRID`` colour — per the user-global figure rules.
  - Today line is dashed ``SUBTLE`` with a small "today" annotation.
  - Legend at the bottom shows the four status patches.

Outputs:
    gantt_chart_example.svg
    gantt_chart_example.png
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.primitives import GanttTask, gantt_bar, today_line  # noqa: E402
from pavlab_arch.style import apply_rcparams  # noqa: E402


# ---------------------------------------------------------------- data
TODAY_X = 3.5

TASKS: list[GanttTask] = [
    # Discovery
    GanttTask("User interviews",        0.0, 1.5, 1.5, "done",     "Discovery"),
    GanttTask("Competitive analysis",   0.5, 2.0, 2.0, "done",     "Discovery"),
    GanttTask("Persona refresh",        1.0, 2.5, 2.5, "done",     "Discovery"),

    # Design
    GanttTask("Wireframes",             2.0, 3.5, 3.5, "done",     "Design"),
    GanttTask("Visual design",          3.0, 4.5, 3.5, "inflight", "Design"),
    GanttTask("Usability testing",      4.0, 5.5, 0.0, "planned",  "Design"),

    # Engineering
    GanttTask("API contracts",          2.5, 4.0, 3.5, "inflight", "Engineering"),
    GanttTask("Backend services",       3.5, 6.5, 3.5, "inflight", "Engineering"),
    GanttTask("Frontend",               4.0, 7.0, 0.0, "planned",  "Engineering"),
    GanttTask("Auth migration",         3.5, 5.0, 0.0, "blocked",  "Engineering",
              note="Blocked on infra"),

    # QA & polish
    GanttTask("Integration tests",      5.0, 7.0, 0.0, "planned",  "QA & polish"),
    GanttTask("Perf hardening",         6.0, 7.5, 0.0, "deferred", "QA & polish"),
    GanttTask("Accessibility audit",    6.0, 7.5, 0.0, "planned",  "QA & polish"),

    # Release
    GanttTask("Launch comms",           7.0, 8.0, 0.0, "planned",  "Release"),
    GanttTask("Public release",         8.0, 8.5, 0.0, "planned",  "Release"),
]

X_TICKS = [0, 1, 2, 3, 4, 5, 6, 7, 8]
X_LABELS = ["W0", "W1", "W2", "W3\n(today)", "W4", "W5", "W6", "W7", "W8"]
X_MAX = 9.0


def render() -> tuple[Path, Path]:
    apply_rcparams()

    n = len(TASKS)
    fig_h = max(5.5, 0.30 * n + 1.8)
    fig, ax = plt.subplots(figsize=(9.0, fig_h))

    # Bars bottom-up so the FIRST task in the list ends up at the TOP.
    rev = list(reversed(TASKS))
    for i, t in enumerate(rev):
        gantt_bar(ax, i,
                  plan_start=t.plan_start, plan_end=t.plan_end,
                  done_end=t.done_end, status=t.status)

    # Y-axis labels
    ax.set_yticks(list(range(n)))
    ax.set_yticklabels([t.label for t in rev], fontsize=10.0, color=P.TEXT)
    ax.tick_params(axis="y", length=0, pad=4)

    # Category bands + right-margin category labels
    cat_ranges: list[tuple[str, int, int]] = []
    cur_cat = rev[0].category
    cur_lo = 0
    for i in range(1, len(rev)):
        if rev[i].category != cur_cat:
            cat_ranges.append((cur_cat, cur_lo, i - 1))
            cur_cat = rev[i].category
            cur_lo = i
    cat_ranges.append((cur_cat, cur_lo, len(rev) - 1))

    for idx, (cat, lo, hi) in enumerate(cat_ranges):
        if idx % 2 == 0:
            ax.axhspan(lo - 0.5, hi + 0.5, color=P.SOFT_BG, zorder=1)
        ax.text(X_MAX + 0.05, (lo + hi) / 2.0, cat,
                fontsize=10.5, color=P.SUBTLE,
                va="center", ha="left")

    # X-axis ticks
    ax.set_xlim(0, X_MAX)
    ax.set_ylim(-0.5, n - 0.5)
    ax.set_xticks(X_TICKS)
    ax.set_xticklabels(X_LABELS, fontsize=11.0, color=P.SUBTLE)
    ax.tick_params(axis="x", length=0, pad=3)

    # Y-grid off, X-grid on (per lab style)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=P.GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Today reference line
    today_line(ax, TODAY_X, label="today")

    # Title + subtitle
    fig.suptitle("Q3 product roadmap — plan vs. progress",
                 x=0.02, y=0.985,
                 ha="left", fontsize=17, fontweight="normal", color=P.TEXT)
    ax.set_title(
        "Horizontal bars are the planned span; green is shipped, amber is in flight, "
        "red hatch is blocked, dotted is deferred.",
        fontsize=10.5, color=P.SUBTLE, loc="left", pad=10,
    )

    # Legend at the bottom
    legend_handles = [
        mpatches.Patch(facecolor=P.ACCENT_2,                        label="Done"),
        mpatches.Patch(facecolor=P.ACCENT_3, alpha=0.55,            label="In flight"),
        mpatches.Patch(facecolor=P.GRID,                            label="Planned"),
        mpatches.Patch(facecolor=P.GRID, edgecolor=P.ACCENT_4,
                       hatch="//", linewidth=1.2,                   label="Blocked"),
        mpatches.Patch(facecolor=P.GRID, edgecolor=P.SUBTLE,
                       hatch="..", linewidth=0.6,                   label="Deferred"),
    ]
    leg = ax.legend(handles=legend_handles, loc="lower right",
                    bbox_to_anchor=(1.0, -0.16),
                    ncol=5, frameon=False, fontsize=10,
                    handlelength=1.4, handleheight=1.0,
                    columnspacing=1.2)
    for txt in leg.get_texts():
        txt.set_color(P.TEXT)

    # Source caption
    fig.text(0.02, 0.005,
             "source: examples/gantt_chart_example.py",
             fontsize=9.0, color=P.SUBTLE, ha="left", va="bottom")

    fig.subplots_adjust(left=0.30, right=0.85, top=0.92, bottom=0.10)

    # Strip clipPath wrappers for clean Illustrator round-trip.
    ax.set_clip_on(False)
    for a in (list(ax.patches) + list(ax.lines) + list(ax.texts)
              + list(ax.collections) + list(ax.images)):
        a.set_clip_on(False)

    out = Path(__file__).resolve().parent
    svg_path = out / "gantt_chart_example.svg"
    png_path = out / "gantt_chart_example.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Post-process: matplotlib's SVG backend emits <clipPath> wrappers
    # for legend / colorbar / inset-axes artists regardless of
    # set_clip_on(False) at the main-axes level. Strip them with a
    # regex pass so the SVG round-trips cleanly through Illustrator's
    # Tiny SVG import (which would otherwise drop the clipping and
    # warn).
    text = svg_path.read_text(encoding="utf-8")
    text = re.sub(r' clip-path="url\(#[^"]+\)"', "", text)
    text = re.sub(r"<clipPath[^>]*>.*?</clipPath>", "", text, flags=re.S)
    svg_path.write_text(text, encoding="utf-8")

    return svg_path, png_path


def main() -> int:
    svg, png = render()
    print(f"wrote {svg}")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
