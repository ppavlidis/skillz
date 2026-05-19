"""Gantt with progress overlays — "plan vs reality" in two modes.

A Gantt chart is a *plan*, not reality. The base ``gantt_bar`` already
encodes plan-vs-done within a single snapshot (gray planned span,
emerald done overlay, status-coloured remaining portion). This example
adds the two progress-over-time overlays:

  A. **Schedule variance vs today** — ``gantt_variance(...)`` draws a
     red overlay on rows whose ``done_end`` is left of ``today``
     (behind schedule) or whose planned window has elapsed without
     completion (overdue). Returns a classification string per row so
     the caller can compose with other cues (here, used to annotate
     the rightmost margin).
  B. **Snapshot diff between two dates (T1 -> T2)** —
     ``gantt_bar_two_tier(...)`` draws each row as two stacked
     half-height bars: top half = state at T1 (pale, 45% alpha);
     bottom half = state now (T2, full saturation). A row whose
     status didn't change reads as the same shape at two saturations
     (visually quiet); a row that moved reads as two different shapes
     stacked.
     ``gantt_bold_changed_labels(...)`` then bolds the y-axis label
     for any row whose status changed, so the "what moved between T1
     and T2" question is answerable from the y axis alone.

The figure stacks two panels:
  - TOP panel: today is mid-project; some rows are behind (red
    overlay) and the in-flight amber + overdue red coexist on the
    same row when a task is both in flight AND behind plan.
  - BOTTOM panel: same project, two time-snapshots (T1 = earlier
    review, T2 = now). The two-tier bars + bold-changed labels
    surface which rows moved.

Outputs:
    gantt_progress_overlay_example.svg
    gantt_progress_overlay_example.png
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
from pavlab_arch.primitives import (  # noqa: E402
    GanttTask, gantt_bar, today_line,
    gantt_variance, gantt_bar_two_tier, gantt_bold_changed_labels,
)
from pavlab_arch.style import apply_rcparams  # noqa: E402


# ----- data ----------------------------------------------------------
# Same 10-row roadmap, observed at TWO snapshots: T1 (week 3.0) and
# T2 (week 4.5). The bottom panel uses both states; the top panel
# uses only the T2 state (the "current snapshot") and overlays
# schedule variance against today = T2.
T1 = 3.0
T2 = 4.5

# Each entry is (label, plan_start, plan_end,
#                done_end_at_T1, status_at_T1,
#                done_end_at_T2, status_at_T2,
#                category).
ROWS = [
    # Discovery — all done by T1; no movement in T2 snapshot.
    ("User interviews",     0.0, 1.5,  1.5, "done",     1.5, "done",     "Discovery"),
    ("Persona refresh",     1.0, 2.5,  2.5, "done",     2.5, "done",     "Discovery"),

    # Design — wireframes done at T1; visual design moved from
    # in-flight to done; usability still in flight but BEHIND today.
    ("Wireframes",          2.0, 3.5,  3.5, "done",     3.5, "done",     "Design"),
    ("Visual design",       3.0, 4.5,  3.5, "inflight", 4.5, "done",     "Design"),
    ("Usability testing",   4.0, 5.5,  0.0, "planned",  4.2, "inflight", "Design"),

    # Engineering — API contracts on track; backend in flight;
    # frontend still planned (behind today at T2 since its window
    # started); auth migration was blocked at T1, still blocked at T2.
    ("API contracts",       2.5, 4.0,  3.0, "inflight", 4.0, "done",     "Engineering"),
    ("Backend services",    3.5, 6.5,  3.5, "inflight", 4.2, "inflight", "Engineering"),
    ("Frontend",            4.0, 7.0,  0.0, "planned",  0.0, "planned",  "Engineering"),
    ("Auth migration",      3.5, 5.0,  0.0, "blocked",  0.0, "blocked",  "Engineering"),

    # QA — perf hardening regressed (was planned at T1, deferred at T2).
    ("Perf hardening",      5.0, 6.5,  0.0, "planned",  0.0, "deferred", "QA"),
]

X_TICKS = [0, 1, 2, 3, 4, 5, 6, 7]
X_LABELS = ["W0", "W1", "W2", "W3", "W4", "W5", "W6", "W7"]
X_MAX = 7.8


# ----- helpers -------------------------------------------------------
def _style_axes(ax, n: int) -> None:
    """Lab-style spines / grid for a Gantt panel."""
    ax.set_xlim(0, X_MAX)
    ax.set_ylim(-0.5, n - 0.5)
    ax.set_xticks(X_TICKS)
    ax.set_xticklabels(X_LABELS, fontsize=10.0, color=P.SUBTLE)
    ax.tick_params(axis="x", length=0, pad=3)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=P.GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _draw_category_bands(ax, rows_reversed):
    """Alternating SOFT_BG bands behind category groups."""
    cur = rows_reversed[0][7]
    lo = 0
    bands = []
    for i in range(1, len(rows_reversed)):
        if rows_reversed[i][7] != cur:
            bands.append((cur, lo, i - 1))
            cur = rows_reversed[i][7]
            lo = i
    bands.append((cur, lo, len(rows_reversed) - 1))
    for idx, (cat, a, b) in enumerate(bands):
        if idx % 2 == 0:
            ax.axhspan(a - 0.5, b + 0.5, color=P.SOFT_BG, zorder=1)
        ax.text(X_MAX + 0.05, (a + b) / 2.0, cat,
                fontsize=10.0, color=P.SUBTLE, va="center", ha="left")


# ----- rendering -----------------------------------------------------
def render() -> tuple[Path, Path]:
    apply_rcparams()

    n = len(ROWS)
    rev = list(reversed(ROWS))   # first row in ROWS -> top of chart

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(10.0, 0.42 * n * 2 + 2.4),
        gridspec_kw={"hspace": 0.55},
    )

    # ===== TOP PANEL: today-variance overlay (mode A) =================
    for i, row in enumerate(rev):
        label, ps, pe, _de1, _s1, de2, s2, _cat = row
        gantt_bar(ax_top, i, plan_start=ps, plan_end=pe,
                  done_end=de2, status=s2)
        gantt_variance(ax_top, i, plan_start=ps, plan_end=pe,
                       done_end=de2, today=T2)

    ax_top.set_yticks(list(range(n)))
    ax_top.set_yticklabels([r[0] for r in rev], fontsize=10.0, color=P.TEXT)
    _draw_category_bands(ax_top, rev)
    _style_axes(ax_top, n)
    today_line(ax_top, T2, label="today")

    ax_top.set_title(
        f"Schedule variance vs. today (W{T2:g})  —  red overlay marks "
        "rows behind plan",
        loc="left", fontsize=11.0, color=P.SUBTLE, pad=8,
    )

    # ===== BOTTOM PANEL: T1 -> T2 snapshot diff (mode C) ==============
    statuses_then_rev = []
    statuses_now_rev = []
    for i, row in enumerate(rev):
        label, ps, pe, de1, s1, de2, s2, _cat = row
        gantt_bar_two_tier(
            ax_bot, i, plan_start=ps, plan_end=pe,
            done_end_then=de1, status_then=s1,
            done_end_now=de2,  status_now=s2,
        )
        statuses_then_rev.append(s1)
        statuses_now_rev.append(s2)

    ax_bot.set_yticks(list(range(n)))
    ax_bot.set_yticklabels([r[0] for r in rev], fontsize=10.0, color=P.TEXT)
    _draw_category_bands(ax_bot, rev)
    _style_axes(ax_bot, n)
    today_line(ax_bot, T2, label="now")
    # Also annotate the T1 snapshot location so the diff is anchored.
    ax_bot.axvline(T1, color=P.SUBTLE, linewidth=0.8,
                   linestyle=(0, (2, 2)), zorder=3.6)
    ax_bot.text(T1 + 0.05, n - 0.7, f"T1 (W{T1:g})",
                fontsize=8, color=P.SUBTLE, va="top", ha="left")

    # Bold y-tick labels for rows whose status changed.
    gantt_bold_changed_labels(
        ax_bot,
        statuses_then=statuses_then_rev,
        statuses_now=statuses_now_rev,
        color_regressions=True,
    )

    ax_bot.set_title(
        f"Snapshot diff (W{T1:g} -> W{T2:g})  —  pale top tier = state at T1; "
        "full bottom tier = state now; bold labels = changed rows; "
        "red labels = regressions",
        loc="left", fontsize=11.0, color=P.SUBTLE, pad=8,
    )

    # ===== Figure-level title + legend + caption ======================
    fig.suptitle("Roadmap — plan vs. reality, two views",
                 x=0.02, y=0.985, ha="left",
                 fontsize=16, fontweight="normal", color=P.TEXT)

    legend_handles = [
        mpatches.Patch(facecolor=P.ACCENT_2,                       label="Done"),
        mpatches.Patch(facecolor=P.ACCENT_3, alpha=0.55,           label="In flight"),
        mpatches.Patch(facecolor=P.GRID,                           label="Planned"),
        mpatches.Patch(facecolor=P.GRID, edgecolor=P.ACCENT_4,
                       hatch="//", linewidth=1.2,                  label="Blocked"),
        mpatches.Patch(facecolor=P.GRID, edgecolor=P.SUBTLE,
                       hatch="..", linewidth=0.6,                  label="Deferred"),
        mpatches.Patch(facecolor=P.ACCENT_4, alpha=0.32,           label="Behind / overdue"),
    ]
    leg = fig.legend(handles=legend_handles, loc="lower center",
                     bbox_to_anchor=(0.5, 0.035),
                     ncol=6, frameon=False, fontsize=9.5,
                     handlelength=1.4, handleheight=1.0,
                     columnspacing=1.4)
    for txt in leg.get_texts():
        txt.set_color(P.TEXT)

    fig.text(0.02, 0.005,
             "source: examples/gantt_progress_overlay_example.py",
             fontsize=8.5, color=P.SUBTLE, ha="left", va="bottom")

    fig.subplots_adjust(left=0.20, right=0.86, top=0.93, bottom=0.13)

    # ===== SVG round-trip hygiene (per CLAUDE.md global rules) =======
    for ax in (ax_top, ax_bot):
        ax.set_clip_on(False)
        for a in (list(ax.patches) + list(ax.lines) + list(ax.texts)
                  + list(ax.collections) + list(ax.images)):
            a.set_clip_on(False)

    out = Path(__file__).resolve().parent
    svg_path = out / "gantt_progress_overlay_example.svg"
    png_path = out / "gantt_progress_overlay_example.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)

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
