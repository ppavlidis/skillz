"""Drawing primitives for architecture / methods comparison figures.

All helpers operate in fractional axes coordinates (set
`ax.set_xlim(0, 100)` and `ax.set_ylim(0, 100)` before calling).

The `stage_box` helper auto-shrinks text that would overflow its
box width so neighbour boxes don't get walked over. Override the
behaviour with `fit_text=False` if you want fixed sizing (and
will manually wrap labels yourself).
"""
from __future__ import annotations
from typing import Tuple

from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

from . import palette as _p


# ---------------------------------------------------------------------------
# Text fitting
# ---------------------------------------------------------------------------

def fit_text(
    text: str,
    box_w: float,
    *,
    fontsize: float = 10.0,
    min_fontsize: float = 6.5,
    char_width_per_pt: float = 0.55,
    padding: float = 1.0,
    fig_width_in: float = 14.0,
) -> float:
    """Return a fontsize that lets `text` fit horizontally in a
    box of width `box_w` axis units, shrinking from `fontsize`
    toward `min_fontsize` if needed.

    Heuristic only — matplotlib doesn't expose text-extent in axis
    coords cheaply. The default constants are calibrated for a
    14"-wide figure on a 0..100 axis. Slightly conservative.

    For multi-line text, pass the longest single line.
    """
    longest = max((s for s in text.split("\n")), key=len, default="")
    n = max(len(longest), 1)
    # axis-units per pt on a fig_width_in canvas at 0..100
    units_per_pt = 100.0 / (fig_width_in * 72.0)
    needed_axis = n * fontsize * char_width_per_pt * units_per_pt + padding
    if needed_axis <= box_w:
        return fontsize
    # Shrink proportionally to fit, clamp to min_fontsize.
    scale = (box_w - padding) / max(needed_axis - padding, 1e-6)
    return max(min_fontsize, fontsize * scale)


# ---------------------------------------------------------------------------
# Low-level
# ---------------------------------------------------------------------------

def box(
    ax,
    x: float, y: float, w: float, h: float,
    *,
    fc: str = "white",
    ec: str = _p.SUBTLE,
    text: str = "",
    fontsize: float = 9.5,
    lw: float = 1.6,
    text_color: str = _p.TEXT,
    fontweight: str = "normal",
    radius: float = 0.05,
    fit: bool = True,
) -> None:
    """Rounded rectangle with optional centered text. Use this when
    you need a one-line label only; for label+subtitle use
    `stage_box`."""
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.0,rounding_size={radius}",
        linewidth=lw, edgecolor=ec, facecolor=fc,
    ))
    if text:
        fs = fit_text(text, w, fontsize=fontsize) if fit else fontsize
        ax.text(
            x + w / 2, y + h / 2, text,
            ha="center", va="center", color=text_color,
            fontsize=fs, fontweight=fontweight, wrap=True,
        )


def arrow(
    ax,
    x1: float, y1: float, x2: float, y2: float,
    *,
    color: str = _p.SUBTLE,
    lw: float = 2.0,
    mut: float = 14,
    style: str = "-|>",
    connectionstyle: str | None = None,
) -> None:
    """Thick arrow — defaults match the Pavlab "not spindly" rule.
    `mut` (mutation_scale) controls arrow-head size; below 12 it
    starts to look skinny."""
    kw = dict(
        arrowstyle=style, color=color, linewidth=lw,
        mutation_scale=mut, shrinkA=0, shrinkB=0,
    )
    if connectionstyle:
        kw["connectionstyle"] = connectionstyle
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), **kw))


# ---------------------------------------------------------------------------
# Stage boxes (LLM vs deterministic)
# ---------------------------------------------------------------------------

def stage_box(
    ax,
    x: float, y: float, w: float, h: float,
    label: str,
    color: str,
    *,
    is_det: bool = False,
    subtitle: str | None = None,
    fit: bool = True,
) -> None:
    """One stage in a pipeline-comparison diagram.

    Visual encoding:
      - **LLM stages** (`is_det=False`): smooth rounded border at
        `color`, soft tinted fill via `palette.tint(color)`, no
        gear glyph.
      - **Deterministic stages** (`is_det=True`): sharper corners,
        slate-tinted fill, `⚙` glyph prepended to the label so the
        machinery vs LLM distinction reads at a glance.

    `subtitle` reads smaller + italic below the main label — use
    for the *model* name on an LLM stage (`subtitle="Opus"`) or
    the *helper module* on a deterministic stage
    (`subtitle="+ ontology resolver"`).

    With `fit=True` (default) the label and subtitle auto-shrink
    if they'd overflow the box; this is the simplest way to avoid
    overlapping text in grids with uneven label lengths.
    """
    if is_det:
        fc = _p.tint(_p.DET)
        ec = _p.SUBTLE
        radius = 0.02
        lw = 1.8
        # No glyph prefix. The earlier ⚙ (U+2699) gear glyph required
        # a font containing that codepoint (DejaVu Sans / Symbola),
        # which Illustrator + a stock macOS install don't always have
        # — it rendered as a missing-glyph tofu in SVG round-trips.
        # Slate-tinted fill + sharper corners + thinner border already
        # encode 'deterministic' distinctly enough; legend chip carries
        # the textual label.
        prefix = ""
    else:
        fc = _p.tint(color)
        ec = color
        radius = 0.10
        lw = 2.2
        prefix = ""

    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.0,rounding_size={radius}",
        linewidth=lw, edgecolor=ec, facecolor=fc,
    ))
    main_text = prefix + label
    if subtitle:
        main_fs = fit_text(main_text, w, fontsize=10.0) if fit else 10.0
        sub_fs = fit_text(subtitle, w, fontsize=7.5, min_fontsize=6.0) if fit else 7.5
        ax.text(
            x + w / 2, y + h * 0.62, main_text,
            ha="center", va="center", color=_p.TEXT,
            fontsize=main_fs, fontweight="bold",
        )
        ax.text(
            x + w / 2, y + h * 0.30, subtitle,
            ha="center", va="center", color=_p.SUBTLE,
            fontsize=sub_fs, style="italic",
        )
    elif label:
        main_fs = fit_text(main_text, w, fontsize=10.0) if fit else 10.0
        ax.text(
            x + w / 2, y + h / 2, main_text,
            ha="center", va="center", color=_p.TEXT,
            fontsize=main_fs, fontweight="bold",
        )


def dual_stage_box(
    ax,
    x: float, y: float, w: float, h: float,
    label: str,
    color_left: str,
    color_right: str,
    *,
    subtitle: str | None = None,
    slope: float = 0.4,
    fit: bool = True,
) -> None:
    """One stage box split diagonally to encode a hybrid stage —
    e.g. AI-recommends-and-curator-decides ("Candidate"), where
    neither colour alone captures what's happening.

    The diagonal runs from the TOP edge at ``x + w * (0.5 + slope/2)``
    to the BOTTOM edge at ``x + w * (0.5 - slope/2)`` — a
    near-vertical seam that runs *down* the box rather than across
    it. ``slope`` controls the lean; ``slope=0`` is a vertical
    line, ``slope=1`` reaches the corners. The default (``0.4``)
    keeps endpoints clearly on the top/bottom edges, never at the
    corners, so the diagonal reads as "split through the middle"
    rather than a decorative corner-to-corner divider.

    The LEFT region (everything to the left of the diagonal) gets
    ``color_left``; the RIGHT region gets ``color_right``. Each
    region carries the **full styling** of a ``stage_box`` painted
    in its colour: the matching tint fill *and* the matching
    border colour on its outer perimeter — so a half-blue,
    half-amber Candidate reads as a Curate-shaped left half + a
    Public-shaped right half, sharing a diagonal seam.

    Convention:
      - ``color_left = ACCENT`` (LLM/agent) + ``color_right = ACCENT_3``
        (curator) for "AI recommends, curator decides" stages.
      - Swap to encode the opposite causality.

    Label + subtitle layout matches ``stage_box``; with ``fit=True``
    (default) text auto-shrinks to box width via ``fit_text``.
    """
    from matplotlib.patches import Polygon

    x_top = x + w * (0.5 + slope / 2)
    x_bot = x + w * (0.5 - slope / 2)

    left_poly = Polygon(
        [(x, y), (x, y + h), (x_top, y + h), (x_bot, y)],
        closed=True,
        facecolor=_p.tint(color_left),
        edgecolor=color_left,
        linewidth=2.2,
        joinstyle="round",
    )
    right_poly = Polygon(
        [(x_bot, y), (x_top, y + h), (x + w, y + h), (x + w, y)],
        closed=True,
        facecolor=_p.tint(color_right),
        edgecolor=color_right,
        linewidth=2.2,
        joinstyle="round",
    )
    ax.add_patch(left_poly)
    ax.add_patch(right_poly)

    # Each half's polygon edge traces the diagonal; the overlap is a
    # single visible seam in whichever colour is drawn last. No
    # explicit divider line — adding one would force a third colour
    # and undo the "each half looks like a stage_box" effect.

    if subtitle:
        main_fs = fit_text(label, w, fontsize=10.0) if fit else 10.0
        sub_fs = fit_text(subtitle, w, fontsize=7.5, min_fontsize=6.0) if fit else 7.5
        ax.text(
            x + w / 2, y + h * 0.62, label,
            ha="center", va="center", color=_p.TEXT,
            fontsize=main_fs, fontweight="bold",
        )
        ax.text(
            x + w / 2, y + h * 0.30, subtitle,
            ha="center", va="center", color=_p.SUBTLE,
            fontsize=sub_fs, style="italic",
        )
    elif label:
        main_fs = fit_text(label, w, fontsize=10.0) if fit else 10.0
        ax.text(
            x + w / 2, y + h / 2, label,
            ha="center", va="center", color=_p.TEXT,
            fontsize=main_fs, fontweight="bold",
        )


def stack_box(
    ax,
    x: float, y: float, w: float, h: float,
    *,
    label: str,
    task: str,
    color: str,
    n_cards: int = 3,
    card_offset: float = 0.55,
) -> None:
    """Render an item as a 'pile of experiments with a ticket on top.'

    The pile is ``n_cards`` offset rectangles in ``color``'s tinted
    fill — generic experiments, no per-card labels. A ticket sits on
    the pile: a smaller white rectangle with coloured border carrying
    the set name (``label``) and the task to do on the set (``task``).
    Visually reads as 'index card clipped onto a stack of papers'.

    Use whenever an item in your figure represents *a collection
    plus a job to do* — e.g. a workstream of experiments that all
    need realignment, an evaluation batch that needs benchmarking,
    a triage queue of audits awaiting curator review. The pile
    encodes the set-ness; the ticket encodes the task.

    Do **not** use this to label a single experiment or a single
    decision point — use ``box`` or ``stage_box`` for those. The
    pile metaphor is wasted ink (and visually misleading) when
    there's no actual set.

    ``color`` follows the usual actor convention:
        - ``ACCENT`` (blue) when an agent owns the task
        - ``ACCENT_3`` (amber) when a curator decides
        - ``DET`` (slate) when a deterministic pipeline runs
        - ``ACCENT_5`` (violet) for evaluation runs
    """
    fill = _p.tint(color)

    # Back cards of the pile, faded so the front card reads cleanly.
    for k in range(n_cards - 1, 0, -1):
        dx, dy = card_offset * k, card_offset * k
        ax.add_patch(FancyBboxPatch(
            (x + dx, y + dy), w, h,
            boxstyle="round,pad=0,rounding_size=0.05",
            linewidth=0.9, edgecolor=color, facecolor=fill, alpha=0.75,
        ))
    # Front card.
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.05",
        linewidth=1.3, edgecolor=color, facecolor=fill,
    ))

    # Ticket on top: white card with coloured border, inset so the
    # pile's coloured border peeks out around it.
    inset_x = max(0.6, w * 0.08)
    inset_v = 0.5
    tx = x + inset_x
    ty = y + inset_v
    tw = w - 2 * inset_x
    th = h - 2 * inset_v
    ax.add_patch(FancyBboxPatch(
        (tx, ty), tw, th,
        boxstyle="round,pad=0,rounding_size=0.10",
        linewidth=1.4, edgecolor=color, facecolor="white",
    ))
    label_fs = fit_text(label, tw, fontsize=7.8, min_fontsize=6.0)
    task_fs = fit_text(task, tw, fontsize=6.5, min_fontsize=5.5)
    ax.text(
        tx + tw / 2, ty + th * 0.66, label,
        ha="center", va="center", color=_p.TEXT,
        fontsize=label_fs, fontweight="bold",
    )
    ax.text(
        tx + tw / 2, ty + th * 0.24, task,
        ha="center", va="center", color=_p.SUBTLE,
        fontsize=task_fs, style="italic",
    )


def ensemble_proposer(
    ax,
    x: float, y: float, w: float, h: float,
    *,
    top: Tuple[str, str],
    bot: Tuple[str, str],
    gap: float = 0.04,
    fit: bool = True,
) -> None:
    """Two parallel mini-boxes stacked vertically — for an
    'ensemble of proposers' where the visual itself reads as
    'two things in parallel.' No overhead label.

    `top` and `bot` are each `(label, border_color)`. Each mini-box
    gets the tint-and-border treatment.
    """
    half = (h - gap) / 2
    for (label, color), yi in [(top, y + half + gap), (bot, y)]:
        ax.add_patch(FancyBboxPatch(
            (x, yi), w, half,
            boxstyle="round,pad=0.0,rounding_size=0.04",
            linewidth=1.4, edgecolor=color, facecolor=_p.tint(color),
        ))
        fs = fit_text(label, w, fontsize=8.0, min_fontsize=6.0) if fit else 8.0
        ax.text(
            x + w / 2, yi + half / 2, label,
            ha="center", va="center", color=_p.TEXT,
            fontsize=fs, fontweight="bold",
        )


# ---------------------------------------------------------------------------
# Performance gauges
# ---------------------------------------------------------------------------

def perf_gauge(
    ax,
    x: float, y: float, w: float, h: float,
    value: float,
    *,
    label: str = "",
    color: str = _p.BAR_TAG,
    bg: str = _p.GRID,
    curator_value: float | None = None,
    show_value: bool = True,
) -> None:
    """Horizontal bar gauge: `value` in [0, 1] → fraction of `w`.

    The bar reads against a grey background scale (always 0..1) so
    rows align visually across the figure.

    When `curator_value` is supplied, a translucent lighter overlay
    of `color` is drawn from x to `x + w * curator_value`. This
    encodes 'value as the system measured, vs value as the curator
    corrected' — when curator > value the overlay extends past the
    raw bar (boost); when curator < value it ends earlier
    (correction down).

    Use `palette.BAR_FACTOR` for blue / proposer-themed gauges and
    `palette.BAR_TAG` (= ACCENT_2) for green / output-themed
    gauges. Both have L*≈65-67 so a row showing both reads with
    equal visual weight (don't use ACCENT directly — too dark).
    """
    # Background scale
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.04",
        linewidth=0, edgecolor="none", facecolor=bg,
    ))
    # Raw value bar
    if value > 0:
        fw = max(0.4, w * value)
        ax.add_patch(FancyBboxPatch(
            (x, y), fw, h,
            boxstyle="round,pad=0,rounding_size=0.04",
            linewidth=0, edgecolor="none", facecolor=color,
        ))
    # Curator-corrected overlay
    if curator_value is not None:
        overlay = _p.CURATOR_OVERLAY.get(color, color)
        cw = max(0.4, w * curator_value)
        ax.add_patch(FancyBboxPatch(
            (x, y + h * 0.18), cw, h * 0.64,
            boxstyle="round,pad=0,rounding_size=0.04",
            linewidth=1.4, edgecolor=overlay,
            facecolor=overlay, alpha=0.85,
        ))
        ax.text(
            x + cw + 0.3, y + h / 2, f"{curator_value:.2f}",
            ha="left", va="center", fontsize=7,
            color=overlay, fontweight="bold", style="italic",
        )
    # Numeric value on the right, label on the left
    if show_value:
        ax.text(
            x + w + 0.4, y + h / 2, f"{value:.2f}",
            ha="left", va="center", fontsize=8.5,
            color=_p.TEXT, fontweight="bold",
        )
    if label:
        ax.text(
            x - 0.4, y + h / 2, label,
            ha="right", va="center", fontsize=8,
            color=_p.SUBTLE,
        )
