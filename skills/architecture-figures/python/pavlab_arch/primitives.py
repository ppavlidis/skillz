"""Drawing primitives for architecture / methods comparison figures.

All helpers operate in fractional axes coordinates (set
`ax.set_xlim(0, 100)` and `ax.set_ylim(0, 100)` before calling).

The `stage_box` helper auto-shrinks text that would overflow its
box width so neighbour boxes don't get walked over. Override the
behaviour with `fit_text=False` if you want fixed sizing (and
will manually wrap labels yourself).
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Tuple

from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

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
    linestyle="solid",
    text_style: str = "normal",
) -> None:
    """Rounded rectangle with optional centered text. Use this when
    you need a one-line label only; for label+subtitle use
    `stage_box`.

    Style knobs that compose into the documented conventions:

    | convention            | params                                        |
    |-----------------------|-----------------------------------------------|
    | actor (current usage) | (use ``stage_box`` instead)                   |
    | passive intermediate  | ``fc=tint(DET)``, ``ec='none'``, ``lw=0``     |
    | catalyst / annotation | ``fc='white'``, ``ec=ACCENT``, ``lw=1.6``     |
    | spawned / transient   | + ``linestyle=(0,(3,2))`` for dashed border   |
    | emphasized input      | ``fc='white'``, ``ec=ACCENT_5``, solid        |

    ``linestyle`` accepts matplotlib's tuple form ``(0, (on, off))`` or
    a string like ``"dashed"``. ``text_style`` is the matplotlib font
    style (``"normal"`` or ``"italic"``).
    """
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.0,rounding_size={radius}",
        linewidth=lw, edgecolor=ec, facecolor=fc,
        linestyle=linestyle,
    ))
    if text:
        fs = fit_text(text, w, fontsize=fontsize) if fit else fontsize
        ax.text(
            x + w / 2, y + h / 2, text,
            ha="center", va="center", color=text_color,
            fontsize=fs, fontweight=fontweight, style=text_style, wrap=True,
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
    linestyle="solid",
    shrinkA: float = 0,
    shrinkB: float = 0,
) -> None:
    """Thick arrow — defaults match the Pavlab "not spindly" rule.
    ``mut`` (mutation_scale) controls arrow-head size; below 12 it
    starts to look skinny.

    Style knobs that compose into the documented conventions:

    | convention             | params                                       |
    |------------------------|----------------------------------------------|
    | primary flow (default) | ``style="-|>"``, ``lw=2.0``, solid           |
    | secondary / side flow  | ``style="->"`` (open head), ``lw=1.2``       |
    | feedback / out-of-band | ``linestyle=(0,(5,3))`` for dashed           |
    | no head (relationship) | ``style="-"``                                |

    Use ``shrinkA``/``shrinkB`` to pull the endpoints inside the bbox
    of a circular/star layout (e.g. cycle arrows that connect chip
    centres but should visually stop at the chip edge).
    """
    kw = dict(
        arrowstyle=style, color=color, linewidth=lw,
        mutation_scale=mut, linestyle=linestyle,
        shrinkA=shrinkA, shrinkB=shrinkB,
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
    scale: float = 1.0,
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
        main_fs = fit_text(main_text, w, fontsize=10.0 * scale) if fit else 10.0 * scale
        sub_fs = fit_text(subtitle, w, fontsize=7.5 * scale,
                          min_fontsize=6.0 * scale) if fit else 7.5 * scale
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
        main_fs = fit_text(main_text, w, fontsize=10.0 * scale) if fit else 10.0 * scale
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
    scale: float = 1.0,
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
        main_fs = fit_text(label, w, fontsize=10.0 * scale) if fit else 10.0 * scale
        sub_fs = fit_text(subtitle, w, fontsize=7.5 * scale,
                          min_fontsize=6.0 * scale) if fit else 7.5 * scale
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
        main_fs = fit_text(label, w, fontsize=10.0 * scale) if fit else 10.0 * scale
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


# ---------------------------------------------------------------------------
# Pill (oval) and circle — for non-rectangular nodes
# ---------------------------------------------------------------------------

def oval(
    ax,
    cx: float, cy: float, w: float, h: float,
    *,
    fc: str = "white",
    ec: str = _p.SUBTLE,
    lw: float = 1.6,
    linestyle="solid",
    rounding: float | None = None,
    text: str = "",
    text_color: str = _p.TEXT,
    fontsize: float = 9.5,
    fontweight: str = "normal",
    text_style: str = "normal",
) -> None:
    """Pill-shaped (fully-rounded rectangle) node centered at ``(cx, cy)``.

    Defaults to a pill (``rounding = min(w, h) / 2``, so the short axis
    is fully rounded into semicircular caps). Pass ``rounding`` to
    relax to an arbitrary corner radius — at ``rounding = h * 0.2`` it
    reads as a soft-rounded rectangle.

    Use for nodes that should read as "molecule-like" rather than
    "stage-like" — chemical species in a pathway, entities in an ER
    diagram, classes in a class-and-relationship diagram.
    """
    if rounding is None:
        rounding = min(w, h) / 2
    x, y = cx - w / 2, cy - h / 2
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.0,rounding_size={rounding}",
        linewidth=lw, edgecolor=ec, facecolor=fc, linestyle=linestyle,
    ))
    if text:
        ax.text(cx, cy, text,
                ha="center", va="center", color=text_color,
                fontsize=fontsize, fontweight=fontweight, style=text_style)


def circle(
    ax,
    cx: float, cy: float, r: float,
    *,
    fc: str = "white",
    ec: str = _p.SUBTLE,
    lw: float = 1.6,
    linestyle="solid",
    text: str = "",
    text_color: str = _p.TEXT,
    fontsize: float = 9.5,
    fontweight: str = "normal",
    text_style: str = "normal",
) -> None:
    """Circle of radius ``r`` centered at ``(cx, cy)``.

    Use for single-letter or single-digit nodes (state labels, network
    nodes, junction markers), or for the center of a radial diagram.
    Aspect-locked — always renders as a true circle regardless of
    figure aspect because matplotlib's ``Circle`` is data-coordinate
    aware.
    """
    ax.add_patch(Circle(
        (cx, cy), r,
        facecolor=fc, edgecolor=ec, linewidth=lw, linestyle=linestyle,
    ))
    if text:
        ax.text(cx, cy, text,
                ha="center", va="center", color=text_color,
                fontsize=fontsize, fontweight=fontweight, style=text_style)


# ---------------------------------------------------------------------------
# Lane-aware forward arrow — same-lane straight, cross-lane diagonal
# ---------------------------------------------------------------------------

def lane_arrow(
    ax,
    src: Tuple[float, float, float, float],
    dst: Tuple[float, float, float, float],
    *,
    color: str = _p.SUBTLE,
    lw: float = 2.0,
    mut: float = 14,
    style: str = "-|>",
    cross_mode: str = "smooth_l",
    corner_rad: float = 4.0,
    arc_rad: float = -0.3,
    src_frac: float = 0.7,
    dst_frac: float = 0.5,
) -> None:
    """Forward arrow between two stage boxes, with lane-aware routing.

    ``src`` and ``dst`` are ``(x, y, w, h)`` rects in axis coords (the
    same tuple a builder typically stores per stage).

    Routing:

    - **Same-lane** (``|ys - yd| < 0.5``): straight horizontal arrow
      from the right-middle of ``src`` to the left-middle of ``dst``.
      Always.

    - **Cross-lane** (different ``y``): controlled by ``cross_mode``:

      * ``"smooth_l"`` (default) — **L-path with rounded corner** via
        ``connectionstyle="angle,angleA=±90,angleB=0,rad=corner_rad"``.
        The arrow exits ``src`` through its top/bottom edge (whichever
        faces the destination lane) at horizontal fraction ``src_frac``,
        travels straight to a corner positioned at the intersection of
        the vertical-from-start and horizontal-from-end lines, rounds
        the corner with radius ``corner_rad``, then travels straight
        into the LEFT edge of ``dst`` at vertical fraction ``dst_frac``.
        The result is a clear "down-then-right" or "up-then-right" ell
        with explicit straight segments and a smooth corner —
        visually unambiguous and never overlaps with same-lane edges
        from the same source. (The older ``angle3`` Bezier variant
        produced a tight cusp when the horizontal arm was short.)

      * ``"diag"`` — straight diagonal. Source's bottom-or-top at
        ``src_frac``, target's top-or-bottom at ``dst_frac``. Cleaner
        than a small-rad arc, but for adjacent columns the line is
        steep and competes visually with the same-lane horizontal
        from the same source.

      * ``"arc"`` — ``arc3,rad=arc_rad``. Historical option. Avoid
        for short chords (adjacent columns) — small ``rad`` values
        render as bent / 90°-looking paths and read poorly. Use only
        when the geometry forces the diagonal through another box.

    Why ``smooth_l`` is the default: a long-standing issue with
    cross-lane edges in this skill was that ``arc3,rad=±0.15`` produced
    visibly-bent paths when chords were short (one-column hops). The
    smooth ell via ``angle3`` is well-behaved at every chord length
    and matches the visual grammar most readers expect from fork-join
    architecture diagrams.
    """
    xs, ys, ws, hs = src
    xd, yd, wd, hd = dst
    same_lane = abs(ys - yd) < 0.5
    cs: str | None = None

    if same_lane:
        p1 = (xs + ws + 0.05, ys + hs / 2)
        p2 = (xd - 0.05, yd + hd / 2)
    elif cross_mode == "smooth_l":
        # Routing rule: the vertical leg always stays close to the SOURCE
        # so it never crosses obstacles in the target's lane.
        #
        #   Going DOWN (fork pattern) → V-then-H "down then right":
        #     exit the source's BOTTOM at horizontal fraction src_frac,
        #     descend through the inter-lane band in the source's column
        #     (empty in a typical fork — the source is in the single-lane
        #     region before the parallel tracks), then horizontal into
        #     the target's LEFT edge.
        #
        #   Going UP (join pattern) → H-then-V "right then up":
        #     exit the source's RIGHT at vertical fraction src_frac,
        #     traverse horizontally through the inter-lane band into
        #     the target's column (empty on the source's lane in a
        #     typical join), then vertical up into the target's BOTTOM
        #     edge.
        #
        # Why the asymmetry: in a typical fork/join, the source's column
        # in the parallel-tracks region has a same-column stage on the
        # OPPOSITE lane. A naive V-H for the join would route the
        # vertical leg through that stage. The "vertical near source,
        # horizontal near target" rule sidesteps the obstacle in both
        # directions.
        if ys > yd:
            # Down-right ell: V-then-H. Corner at (p1.x, p2.y).
            p1 = (xs + ws * src_frac, ys)
            p2 = (xd, yd + hd * dst_frac)
            cs = f"angle,angleA=-90,angleB=0,rad={corner_rad}"
        else:
            # Up-right ell: H-then-V. Corner at (p2.x, p1.y).
            p1 = (xs + ws, ys + hs * src_frac)
            p2 = (xd + wd * dst_frac, yd)
            cs = f"angle,angleA=0,angleB=90,rad={corner_rad}"
    elif cross_mode == "diag":
        if ys > yd:
            p1 = (xs + ws * src_frac, ys)
            p2 = (xd + wd * (1 - src_frac), yd + hd)
        else:
            p1 = (xs + ws * src_frac, ys + hs)
            p2 = (xd + wd * (1 - src_frac), yd)
    elif cross_mode == "arc":
        p1 = (xs + ws + 0.05, ys + hs / 2)
        p2 = (xd - 0.05, yd + hd / 2)
        cs = f"arc3,rad={arc_rad}"
    else:
        raise ValueError(
            f"unknown cross_mode {cross_mode!r}; expected "
            f"'smooth_l', 'diag', or 'arc'"
        )

    kw = dict(arrowstyle=style, color=color, linewidth=lw,
              mutation_scale=mut, shrinkA=0, shrinkB=0)
    if cs is not None:
        kw["connectionstyle"] = cs
    ax.add_patch(FancyArrowPatch(p1, p2, **kw))


# ---------------------------------------------------------------------------
# Compact, position-parameterised legend block
# ---------------------------------------------------------------------------

def legend_block(
    ax,
    x: float, y_top: float,
    specs,
    *,
    title: str | None = "Legend",
    chip_w: float = 4.0,
    chip_h: float = 2.4,
    row_gap: float = 1.1,
    text_pad: float = 1.0,
    title_pad: float = 2.4,
    label_fontsize: float = 8.5,
    title_fontsize: float = 8.5,
    note_fontsize: float | None = None,
) -> tuple[float, float]:
    """Compact vertical legend block — chip on the LEFT of each row,
    text on the RIGHT, no overlap. Anchored at top-left ``(x, y_top)``.

    ``specs`` is an iterable of ``(color, is_det, label, note)``:

    - ``color`` — hex string, or a ``(left, right)`` tuple to render a
      ``dual_stage_box`` chip for a hybrid actor.
    - ``is_det`` — render the slate-tinted "automated" style.
    - ``label`` — main label, drawn in ``TEXT`` colour and bold.
    - ``note`` — optional secondary text, drawn in ``SUBTLE`` colour
      to the right of the label. Pass an empty string or ``""`` to
      skip.

    The block is fully position-parameterised so callers can drop it
    in any corner of the figure: ``legend_block(ax, x=72, y_top=20,
    specs=...)`` puts it bottom-right; ``legend_block(ax, x=4,
    y_top=88, specs=...)`` puts it in the top-left margin.

    Returns ``(width, height)`` of the rendered block in axis units
    so the caller can lay out adjacent content.

    Comparison with the older inline ``_legend_chip`` pattern: that
    helper stacked ``label`` (bold) and ``note`` (italic, smaller)
    *inside* a 2.6-tall chip, which at typical figsizes overlapped
    visibly. ``legend_block`` puts the chip and the text side-by-side
    so neither competes for vertical space.
    """
    if note_fontsize is None:
        note_fontsize = label_fontsize - 0.5

    cur_y = y_top
    if title:
        ax.text(x, cur_y, title,
                ha="left", va="top",
                color=_p.SUBTLE, fontsize=title_fontsize, style="italic")
        cur_y -= title_pad

    max_text_extent = 0.0
    # axis-units-per-character — derived from the actual figure width
    # so the heuristic stays correct across figsizes (a fixed multiplier
    # of 0.06 was calibrated for a 14" figure and under-estimated text
    # extent on smaller figures, causing label / note overlap).
    fig_width_in = ax.figure.get_size_inches()[0]
    char_w = label_fontsize * 0.6 / 72 * 100 / fig_width_in

    for spec in specs:
        color, is_det, label, note = spec[0], spec[1], spec[2], spec[3]
        chip_y = cur_y - chip_h

        if isinstance(color, tuple):
            dual_stage_box(ax, x, chip_y, chip_w, chip_h, "",
                           color[0], color[1])
        else:
            stage_box(ax, x, chip_y, chip_w, chip_h, "", color,
                      is_det=is_det, fit=False)

        text_y = chip_y + chip_h / 2
        text_x = x + chip_w + text_pad
        ax.text(text_x, text_y, label,
                ha="left", va="center",
                color=_p.TEXT, fontsize=label_fontsize, fontweight="bold")

        ext = len(label) * char_w
        if note:
            note_x = text_x + ext + 0.9
            ax.text(note_x, text_y, note,
                    ha="left", va="center",
                    color=_p.SUBTLE, fontsize=note_fontsize, style="italic")
            ext = (note_x - text_x) + len(note) * note_fontsize * 0.06

        max_text_extent = max(max_text_extent, ext)
        cur_y = chip_y - row_gap

    block_w = chip_w + text_pad + max_text_extent
    block_h = y_top - (cur_y + row_gap)
    return block_w, block_h


# ---------------------------------------------------------------------------
# Labeled arrow — the general "edge with a label" pattern
# ---------------------------------------------------------------------------

def labeled_arrow(
    ax,
    x1: float, y1: float, x2: float, y2: float,
    label: str,
    *,
    # arrow params
    color: str = _p.SUBTLE,
    lw: float = 2.0,
    mut: float = 14,
    style: str = "-|>",
    connectionstyle: str | None = None,
    linestyle="solid",
    shrinkA: float = 0,
    shrinkB: float = 0,
    # label params
    label_color: str | None = None,
    label_fontsize: float = 7.5,
    label_style: str = "italic",
    label_weight: str = "bold",
    label_along: float = 0.5,
    label_side: float = 2.0,
) -> None:
    """Arrow from ``(x1, y1)`` to ``(x2, y2)`` with a label positioned
    along the chord.

    This is the **labeled-edge** pattern — fundamental whenever a
    diagram has things connected by arrows AND the arrow itself
    carries information: state-machine transitions ("on_failure"),
    pathway catalysts ("aconitase"), network protocols ("TCP/443"),
    ER cardinalities ("1..*"), class associations ("uses"), Sankey
    edge labels, dependency reasons, etc.

    Convention: label sits OFF the arrow path (perpendicular to the
    chord) so the line and the text never compete for the same
    pixels. Default styling is italic, ``ACCENT``-coloured, bold, at
    7.5pt — quiet enough to not visually overpower the structural
    arrow but legible at typical figsizes.

    Positioning:
      - ``label_along`` ∈ ``[0, 1]`` — fraction along the chord
        (0 = at start, 1 = at end). Default 0.5 = midpoint.
      - ``label_side`` — perpendicular offset from the chord, in
        axis units. **Positive = LEFT of the arrow's direction of
        travel** (so for a clockwise cycle, positive offsets put
        labels on the OUTWARD side, which is usually where you want
        them). Zero = on the chord. Negative = right of direction.

    All other parameters mirror ``arrow``. Pass ``connectionstyle``
    (e.g. ``"arc3,rad=-0.13"``) for curved arrows; the label still
    anchors to the chord midpoint by default — adjust ``label_side``
    if the curve pulls the visible apex away from the chord and you
    want the label to follow.
    """
    # 1. Draw the arrow.
    kw = dict(
        arrowstyle=style, color=color, linewidth=lw,
        mutation_scale=mut, linestyle=linestyle,
        shrinkA=shrinkA, shrinkB=shrinkB,
    )
    if connectionstyle:
        kw["connectionstyle"] = connectionstyle
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), **kw))

    # 2. Position the label.
    cx = x1 + label_along * (x2 - x1)
    cy = y1 + label_along * (y2 - y1)
    if label_side:
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) or 1.0
        # Left perpendicular of the arrow direction:
        #   for arrow going RIGHT (dx>0), left = UP   → (-dy, dx) = (0, dx) ✓
        #   for arrow going UP    (dy>0), left = LEFT → (-dy, dx) = (-dy, 0) ✓
        perp_x = -dy / d
        perp_y = dx / d
        cx += perp_x * label_side
        cy += perp_y * label_side

    color_l = label_color if label_color is not None else _p.ACCENT
    ax.text(
        cx, cy, label,
        ha="center", va="center",
        color=color_l, fontsize=label_fontsize,
        style=label_style, fontweight=label_weight,
    )


# ---------------------------------------------------------------------------
# Gantt charts
# ---------------------------------------------------------------------------

@dataclass
class GanttTask:
    """One row in a Gantt chart.

    - ``plan_start`` / ``plan_end`` — the planned span in the time
      units of the x-axis (any numeric: dates encoded as floats,
      session numbers, weeks, sprints).
    - ``done_end`` — how far the "done" overlay fills, in the same
      units. Use ``done_end == plan_start`` for not-yet-started, and
      ``done_end == plan_end`` for fully complete.
    - ``status`` — one of ``"done"``, ``"inflight"``, ``"planned"``,
      ``"blocked"``, ``"deferred"``. Controls the colour / pattern
      of the remaining (unfilled) portion of the bar.
    - ``category`` — optional grouping key. Tasks sharing a category
      get rendered with a shared right-side category label and a
      light row-band shading (when ``show_categories=True``).
    - ``note`` — optional free-text annotation, not currently rendered
      but available for callers that want to surface it.
    """
    label: str
    plan_start: float
    plan_end: float
    done_end: float = 0.0
    status: str = "planned"
    category: str = ""
    note: str = ""


# Status -> (fill, edge, hatch, alpha) for the remaining (unfilled)
# overlay portion of a Gantt bar. Done portion is always emerald.
_GANTT_STATUS = {
    "inflight": dict(fc=_p.ACCENT_3, ec="none", hatch=None, alpha=0.55),
    "blocked":  dict(fc=_p.GRID,     ec=_p.ACCENT_4, hatch="//", alpha=1.0),
    "deferred": dict(fc=_p.GRID,     ec=_p.SUBTLE,   hatch="..", alpha=1.0),
    "planned":  dict(fc=None,        ec=None,        hatch=None, alpha=1.0),
    "done":     dict(fc=None,        ec=None,        hatch=None, alpha=1.0),
}


def gantt_bar(
    ax,
    y: float,
    plan_start: float,
    plan_end: float,
    done_end: float,
    status: str = "planned",
    *,
    height: float = 0.62,
    done_color: str = _p.ACCENT_2,
    planned_color: str = _p.GRID,
    alpha_scale: float = 1.0,
) -> None:
    """One Gantt row, layered: planned-bar background, status overlay
    on the remaining portion, done overlay on the completed portion.

    Convention:
      - planned bar (full span) drawn in ``GRID`` (gray-200), no edge
      - "done" overlay in ``ACCENT_2`` (emerald) from ``plan_start``
        to ``done_end``
      - "remaining" overlay (``done_end`` to ``plan_end``) styled by
        ``status``: amber semi-transparent for in-flight; red-hatched
        for blocked; dot-hatched for deferred; nothing extra for plain
        planned/done.

    ``y`` is the row centre. ``height`` is the bar height in y-units.
    The same row can be a single ``GanttTask``'s render.

    ``alpha_scale`` multiplies the alpha of every layer (planned
    background, status overlay, done overlay). Use values < 1.0 to
    render a "ghost" / paler version of the bar — this is what
    ``gantt_bar_two_tier`` uses for the T1 tier.
    """
    plan_w = plan_end - plan_start
    done_w = max(0.0, done_end - plan_start)
    remaining_start = plan_start + done_w
    remaining_w = plan_w - done_w

    # planned background
    ax.barh(
        y, plan_w, left=plan_start, height=height,
        color=planned_color, edgecolor="none", zorder=2,
        alpha=alpha_scale,
    )

    # remaining-portion overlay
    info = _GANTT_STATUS.get(status, _GANTT_STATUS["planned"])
    if remaining_w > 0 and info["fc"] is not None:
        ax.barh(
            y, remaining_w, left=remaining_start, height=height,
            color=info["fc"], edgecolor=info["ec"] or "none",
            linewidth=1.4 if info["ec"] else 0,
            hatch=info["hatch"], alpha=info["alpha"] * alpha_scale,
            zorder=2.5,
        )

    # done overlay
    if done_w > 0:
        ax.barh(
            y, done_w, left=plan_start, height=height,
            color=done_color, edgecolor="none", zorder=3,
            alpha=alpha_scale,
        )


# ---------------------------------------------------------------------------
# Gantt progress overlays — "plan vs reality"
# ---------------------------------------------------------------------------
#
# A Gantt is a plan, not reality. Two orthogonal ways to layer reality
# onto a plan-shaped chart:
#
#   A) Schedule variance vs "today": per-row overlay showing whether the
#      row is ahead/behind/overdue relative to a linear-progress
#      expectation at the current date. Use `gantt_variance`.
#   B) Snapshot diff between two dates (T1 -> T2): per-row two-tier bar
#      with the earlier state on the top half (paler) and the current
#      state on the bottom (full saturation). Use `gantt_bar_two_tier`
#      + `gantt_bold_changed_labels` for the y-axis-label emphasis.
#
# A and C compose: use `gantt_bar_two_tier` for the snapshot diff AND
# `gantt_variance(... today=T2)` for the current schedule variance.


# Rank used by the bold-changed-labels helper to detect promotions vs
# regressions. Higher rank = more progressed. Callers can pass their
# own dict to override.
_GANTT_STATUS_RANK = {
    "deferred": 0,
    "blocked":  0,
    "planned":  1,
    "inflight": 2,
    "done":     3,
}


def gantt_variance(
    ax,
    y: float,
    plan_start: float,
    plan_end: float,
    done_end: float,
    today: float,
    *,
    height: float = 0.62,
    behind_color: str = _p.ACCENT_4,
    behind_alpha: float = 0.32,
) -> str:
    """Decorate a Gantt row with a schedule-variance overlay relative
    to ``today``, and return the row's variance classification.

    Assumes linear progress: at ``today``, a row in its planned window
    is "on track" iff ``done_end == today``. ``done_end < today`` is
    behind; ``done_end > today`` is ahead.

    Returns one of:
      - ``"not_started"`` — ``today < plan_start`` (no overlay drawn)
      - ``"complete"`` — ``done_end >= plan_end`` (no overlay drawn)
      - ``"overdue"`` — ``today >= plan_end`` and the row isn't done;
        the gap ``[done_end, plan_end]`` is tinted red
      - ``"behind"`` — ``today in [plan_start, plan_end]`` and
        ``done_end < today``; gap ``[done_end, today]`` tinted red
      - ``"ahead"`` — ``done_end > today``; no overlay drawn (the
        emerald done bar already extends past the global today line,
        which self-documents the "going well" case)
      - ``"on_track"`` — ``done_end == today``; no overlay drawn

    Why no per-row marker for ``today``: the global ``today_line``
    already draws one vertical reference for the whole chart, so per-
    row markers would duplicate that signal. The overlay only fires
    for the cases that need attention (behind / overdue).

    Callers typically use the returned classification to decide whether
    to bold the y-tick label, emit a note, or compute summary counts.
    """
    if today < plan_start:
        return "not_started"
    # Clamp done_end into the plan window so the "not started" sentinel
    # (done_end == 0 or anything < plan_start) doesn't make the red gap
    # extend left of the plan bar.
    effective_done = max(plan_start, min(done_end, plan_end))
    if effective_done >= plan_end:
        return "complete"
    if today >= plan_end:
        gap_start, gap_end = effective_done, plan_end
        kind = "overdue"
    elif effective_done < today:
        gap_start, gap_end = effective_done, today
        kind = "behind"
    elif effective_done > today:
        return "ahead"
    else:
        return "on_track"

    gap_w = gap_end - gap_start
    if gap_w > 0:
        ax.barh(
            y, gap_w, left=gap_start, height=height,
            color=behind_color, edgecolor="none",
            alpha=behind_alpha, zorder=3.5,
        )
    return kind


def gantt_bar_two_tier(
    ax,
    y: float,
    plan_start: float,
    plan_end: float,
    done_end_then: float,
    status_then: str,
    done_end_now: float,
    status_now: str,
    *,
    height: float = 0.62,
    pale_alpha: float = 0.45,
    seam: float = 0.04,
) -> bool:
    """Two stacked half-height bars on row ``y``:

      - TOP half: the row's state at an earlier snapshot T1, rendered
        pale (alpha-scaled by ``pale_alpha``).
      - BOTTOM half: the row's state now (T2), full saturation.

    A small ``seam`` between the two halves lets the white facecolor
    show through, so the tiers read as stacked rather than blended.

    If the row's status and ``done_end`` are unchanged between T1 and
    T2, the two tiers render as the same shape at two saturations —
    visually quiet. If anything changed, the shapes differ and the
    row pops on a scan.

    Returns ``True`` if anything changed between T1 and T2 (status or
    ``done_end``). Use that to drive the bold-y-tick-label cue via
    ``gantt_bold_changed_labels`` so unchanged rows stay visually
    quiet AND labeled-quiet on the y axis.
    """
    h = height / 2.0
    offset = (h + seam) / 2.0
    gantt_bar(
        ax, y + offset,
        plan_start, plan_end, done_end_then, status_then,
        height=h - seam, alpha_scale=pale_alpha,
    )
    gantt_bar(
        ax, y - offset,
        plan_start, plan_end, done_end_now, status_now,
        height=h - seam, alpha_scale=1.0,
    )
    return (status_then != status_now) or (done_end_then != done_end_now)


def gantt_bold_changed_labels(
    ax,
    statuses_then,
    statuses_now,
    *,
    rank=None,
    color_regressions: bool = False,
    regression_color: str = _p.ACCENT_4,
) -> None:
    """Bold y-tick labels for rows whose status changed between T1 and
    T2. Optionally tint regressions (status rank decreased) red.

    ``statuses_then`` and ``statuses_now`` are parallel lists indexed
    in the SAME bottom-to-top order as ``ax.get_yticklabels()``. If
    you reversed your tasks list for top-down display (the standard
    Gantt convention — first task at TOP), you must reverse the two
    statuses lists to match.

    ``rank`` is an optional mapping from status string to integer rank
    (higher = more progressed). Defaults to the skill's standard
    ranking: ``deferred = blocked = 0 < planned = 1 < inflight = 2 <
    done = 3``. A change from a lower rank to a higher rank is a
    *promotion*; the reverse is a *regression*. Pass your own dict to
    override (e.g. if your status grammar differs).

    Without this helper, every row in a two-tier chart competes for
    the reader's attention equally — the encoding doesn't self-explain
    that unchanged rows are unchanged. The bold-label cue makes the
    "what moved" question answerable from the y axis alone.
    """
    if rank is None:
        rank = _GANTT_STATUS_RANK
    labels = list(ax.get_yticklabels())
    n = min(len(labels), len(statuses_then), len(statuses_now))
    for i in range(n):
        st_then = statuses_then[i]
        st_now = statuses_now[i]
        if st_then == st_now:
            continue
        labels[i].set_fontweight("bold")
        if color_regressions and rank.get(st_now, 0) < rank.get(st_then, 0):
            labels[i].set_color(regression_color)


def today_line(
    ax,
    x: float,
    *,
    label: str = "today",
    label_y: float | None = None,
    color: str = _p.SUBTLE,
    lw: float = 0.9,
    linestyle: str = "--",
) -> None:
    """Vertical reference line for "now" / "today" / cursor position
    on any horizontal-time chart (Gantt, timeline, etc.).

    ``label_y`` defaults to just below the top of the axes' y-range so
    the label sits above the highest row.
    """
    ax.axvline(x, color=color, linewidth=lw, linestyle=linestyle, zorder=4)
    if label:
        if label_y is None:
            y_lo, y_hi = ax.get_ylim()
            label_y = y_hi - 0.7
        ax.text(
            x + 0.08, label_y, label,
            fontsize=8, color=color, va="top", ha="left",
        )


# ---------------------------------------------------------------------------
# Cylinder — the conventional database / store symbol
# ---------------------------------------------------------------------------

def cylinder(
    ax,
    cx: float, cy: float, w: float, h: float,
    *,
    fc: str = "white",
    ec: str = _p.SUBTLE,
    lw: float = 1.4,
    linestyle="solid",
    cap_ratio: float = 0.20,
    text: str = "",
    text_color: str = _p.TEXT,
    fontsize: float = 9.5,
    fontweight: str = "bold",
    sub: str = "",
    sub_color: str | None = None,
) -> None:
    """Cylinder centered at ``(cx, cy)``, width ``w``, height ``h``.

    The conventional database / data-store symbol: an elliptical top
    cap, two vertical sides, and a half-elliptical bottom (only the
    front half of the bottom is drawn — the back half would be hidden
    behind the body in a real cylinder). Use for databases, queues,
    or anything that should read "persistent store" at a glance.

    ``cap_ratio`` is the height fraction taken by the top / bottom
    ellipses (default 0.20 → tall body + modest caps). With
    ``cap_ratio=0.3`` the cylinder looks shorter and squatter.
    """
    from matplotlib.patches import Ellipse, Rectangle, Arc
    from matplotlib.lines import Line2D

    cap_h = h * cap_ratio
    body_h = h - cap_h
    half_w = w / 2
    half_body = body_h / 2

    # Filled body rectangle (no border — sides drawn separately)
    ax.add_patch(Rectangle(
        (cx - half_w, cy - half_body), w, body_h,
        facecolor=fc, edgecolor="none", zorder=2,
    ))

    # Two vertical side lines
    for x in (cx - half_w, cx + half_w):
        ax.add_line(Line2D(
            [x, x], [cy - half_body, cy + half_body],
            color=ec, linewidth=lw, linestyle=linestyle, zorder=3,
        ))

    # Top: full ellipse, filled
    ax.add_patch(Ellipse(
        (cx, cy + half_body), w, cap_h,
        facecolor=fc, edgecolor=ec, linewidth=lw,
        linestyle=linestyle, zorder=4,
    ))

    # Bottom: only the front half of the ellipse curve (back half is
    # hidden in a real cylinder). Arc doesn't fill — it traces an arc.
    ax.add_patch(Arc(
        (cx, cy - half_body), w, cap_h,
        angle=0, theta1=180, theta2=360,
        edgecolor=ec, linewidth=lw, linestyle=linestyle, zorder=4,
    ))

    # Text (label centred; subtitle slightly below)
    if text:
        ax.text(cx, cy + (1.0 if sub else 0.0), text,
                ha="center", va="center",
                color=text_color, fontsize=fontsize, fontweight=fontweight)
    if sub:
        ax.text(cx, cy - 1.5, sub,
                ha="center", va="center",
                color=sub_color or _p.SUBTLE,
                fontsize=fontsize - 2.0, style="italic")


# ---------------------------------------------------------------------------
# Container — dashed grouping rectangle
# ---------------------------------------------------------------------------

def container(
    ax,
    x_lo: float, y_lo: float, x_hi: float, y_hi: float,
    label: str | None = None,
    *,
    fc: str = "none",
    ec: str = _p.SUBTLE,
    lw: float = 1.2,
    linestyle=(0, (5, 3)),
    radius: float = 0.04,
    label_color: str | None = None,
    label_fontsize: float = 10.0,
    label_fontweight: str = "bold",
    label_pad: float = 2.5,
) -> None:
    """Dashed (or solid) rounded container that groups related elements.

    Visually says "these belong together" without requiring an opaque
    background — distinct from ``tier_band``-style soft-filled
    containers because it has an explicit border instead of a fill.

    Defaults: no fill, dashed `SUBTLE` border, bold label at the
    top-left padded inward by ``label_pad``. Override ``fc`` to a
    very light tint (e.g. ``tint(ACCENT_2)``) for a "soft-fill +
    dashed border" combo, used by classical full-stack diagrams to
    mark the "Front End / Back End" mega-regions.

    Pass ``linestyle="solid"`` for a solid-border grouping (used when
    the group is permanent / load-bearing rather than tentative).
    """
    ax.add_patch(FancyBboxPatch(
        (x_lo, y_lo), x_hi - x_lo, y_hi - y_lo,
        boxstyle=f"round,pad=0.0,rounding_size={radius}",
        linewidth=lw, edgecolor=ec, facecolor=fc, linestyle=linestyle,
    ))
    if label:
        ax.text(
            x_lo + label_pad, y_hi - label_pad, label,
            ha="left", va="top",
            color=label_color or ec,
            fontsize=label_fontsize, fontweight=label_fontweight,
        )
