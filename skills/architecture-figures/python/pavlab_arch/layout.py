"""Figure-size presets and a grid helper for non-overlapping
stage layouts.

`figure(shape, ...)` returns `(fig, ax)` with `ax.set_xlim(0, 100)`
and `ax.set_ylim(0, 100)` already applied — so every drawing
primitive in `pavlab_arch.primitives` operates in a uniform
0..100 coordinate space regardless of the physical figure size.

Three canonical shapes ("figure-shaped"):

  - **slide**       16:9, ~13.33×7.5". For talks, slide decks.
  - **square**      1:1, ~8×8". For posters or balanced web embeds.
  - **wide_half**   3:1, ~14×4.7". Full page width, half height —
                    one row of stages with gauges to the right.

`grid_columns(...)` lays out N columns left-to-right with explicit
inter-column gaps; the returned `(xs, ws)` arrays guarantee no
overlap regardless of label length so long as you pass realistic
widths. Use it instead of hand-eyeballed `col_xs = [27, 38, 45, ...]`
literals.
"""
from __future__ import annotations
from typing import Iterable, Sequence

import matplotlib.pyplot as plt


# (width_in, height_in) — physical figure size in inches.
FIGSIZES = {
    "slide":     (13.33, 7.5),    # 16:9 talk slide
    "square":    (8.0,   8.0),    # 1:1 poster / web
    "wide_half": (14.0,  4.7),    # 3:1 page-width / half-height
}


def figure(
    shape: str = "wide_half",
    *,
    figsize: tuple[float, float] | None = None,
):
    """Create a figure with the canonical 0..100 axis coordinates.

    Parameters
    ----------
    shape : one of "slide", "square", "wide_half".  Ignored when
        `figsize` is provided.
    figsize : explicit override.

    Returns
    -------
    (fig, ax) — `ax` has xlim/ylim 0..100 and ticks stripped.
    """
    if figsize is None:
        if shape not in FIGSIZES:
            raise ValueError(
                f"unknown shape {shape!r}; expected one of "
                f"{sorted(FIGSIZES)} or pass figsize=(w,h)"
            )
        figsize = FIGSIZES[shape]
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xticks([])
    ax.set_yticks([])
    return fig, ax


def grid_columns(
    widths: Sequence[float],
    *,
    x_start: float = 5.0,
    x_end: float = 95.0,
    gap: float | None = None,
    min_gap: float = 1.5,
) -> tuple[list[float], list[float]]:
    """Lay out N columns horizontally within `[x_start, x_end]`.

    `widths` are the *relative* widths (any units — they get
    rescaled to fit the available span). If you want exact widths,
    pass `gap=None` and ensure `sum(widths) + (n-1) * min_gap` fits
    within `x_end - x_start` (raises if not).

    Returns `(xs, ws)` — x-positions and widths in axis coords.

    Guarantees no overlap as long as widths are positive and the
    caller doesn't subsequently draw outside the returned (x, w)
    range.
    """
    n = len(widths)
    if n == 0:
        return [], []
    if any(w <= 0 for w in widths):
        raise ValueError("column widths must be positive")

    span = x_end - x_start
    if gap is None:
        # Auto-pick the gap that uses available width, minimum `min_gap`.
        total_w_request = sum(widths)
        if total_w_request + (n - 1) * min_gap > span:
            # Scale widths down so everything fits with min_gap.
            scale = (span - (n - 1) * min_gap) / total_w_request
            if scale <= 0:
                raise ValueError(
                    f"can't fit {n} columns of widths {list(widths)} "
                    f"with min_gap={min_gap} in span={span:.1f}"
                )
            ws = [w * scale for w in widths]
            g = min_gap
        else:
            # Distribute leftover space evenly into gaps.
            leftover = span - total_w_request
            g = leftover / max(n - 1, 1) if n > 1 else 0
            ws = list(widths)
    else:
        total_w_request = sum(widths)
        if total_w_request + (n - 1) * gap > span + 1e-9:
            raise ValueError(
                f"columns of widths {list(widths)} with gap={gap} "
                f"exceed span {span:.1f}"
            )
        ws = list(widths)
        g = gap

    xs = []
    cur = x_start
    for w in ws:
        xs.append(cur)
        cur += w + g
    return xs, ws


def estimate_label_width(
    label: str,
    *,
    fontsize: float = 10.0,
    char_width_per_pt: float = 0.55,
    padding: float = 2.0,
) -> float:
    """Estimate the axis-coord width needed for a text label.

    Heuristic only — assumes the axis is 0..100 over a ~14"
    physical figure. For other sizes the result scales reasonably
    in *relative* terms (use it for picking column widths
    proportionally), but not absolutely.

    For a fixed figure use this to derive column widths from labels
    so boxes always wrap their content. Add headroom via `padding`.
    """
    # ~6.7pt ≈ 1 axis unit on a 14" wide canvas.
    n = max(len(label), 1)
    return n * fontsize * char_width_per_pt / 6.7 + padding


def svg_safe_figure(fig) -> None:
    """Iterate every axes in `fig` and disable clipping on every
    artist within. Convenience wrapper for figures with subplots —
    call once just before `fig.savefig(...)`.

    See `svg_safe` (single-axes version) for the why.
    """
    for ax in fig.axes:
        svg_safe(ax)


def svg_safe(ax) -> None:
    """Disable clipping on every artist in `ax` so the saved SVG has
    no `clipPath` elements.

    Matplotlib's SVG backend wraps each axes' artists in a
    `<clipPath>` that limits drawing to the axes bbox. Round-tripping
    an SVG with `<clipPath>` elements through Illustrator's Tiny SVG
    import drops the clipping ("Clipping will be lost on roundtrip to
    Tiny") and can subtly distort the result. For architecture
    figures the clip serves no purpose — everything we draw is
    already inside the 0..100 box — so disabling it is free.

    Call this once **after** drawing everything, **before**
    `fig.savefig(...)`.
    """
    ax.set_clip_on(False)
    for artist in (
        list(ax.patches) + list(ax.lines) + list(ax.texts)
        + list(ax.collections) + list(ax.images)
    ):
        artist.set_clip_on(False)


def autosize_columns(
    labels: Iterable[str],
    *,
    fontsize: float = 10.0,
    min_w: float = 6.0,
    max_w: float = 18.0,
    padding: float = 3.0,
) -> list[float]:
    """Derive per-column widths from the longest label in each
    column. Clamped to [min_w, max_w] so a single huge label
    doesn't blow the layout.

    Pass the result to `grid_columns(widths=...)`.
    """
    out = []
    for lab in labels:
        w = estimate_label_width(lab, fontsize=fontsize, padding=padding)
        out.append(max(min_w, min(max_w, w)))
    return out


# ---------------------------------------------------------------------------
# Shape-edge intersection — arrows should land at edges, not centres
# ---------------------------------------------------------------------------

import math as _math


def pill_edge(cx: float, cy: float, w: float, h: float,
              sx: float, sy: float, *, margin: float = 0.0
              ) -> tuple[float, float]:
    """Where does a ray from ``(sx, sy)`` toward ``(cx, cy)`` cross the
    perimeter of a pill / ellipse at ``(cx, cy)`` with width ``w`` and
    height ``h``?

    Pills with full rounding are well-approximated as ellipses for
    edge-intersection — close enough that the visual result is
    indistinguishable from a true rounded-rectangle calculation, and
    the math stays simple.

    ``margin`` shifts the returned point *outward* along the ray by
    that many axis units. Use a small positive margin (~0.5) when you
    want the arrow's tip to land just outside the chip's border
    rather than touching it.

    Use this to terminate arrows at chip edges instead of chip
    centres — a common mistake that puts the arrowhead on top of the
    chip's text.
    """
    dx, dy = cx - sx, cy - sy
    d = _math.hypot(dx, dy)
    if d == 0:
        return (cx, cy)
    udx, udy = dx / d, dy / d
    a, b = w / 2.0, h / 2.0
    t = 1.0 / _math.sqrt((udx / a) ** 2 + (udy / b) ** 2)
    return (cx - (t + margin) * udx, cy - (t + margin) * udy)


def rect_edge(cx: float, cy: float, w: float, h: float,
              sx: float, sy: float, *, margin: float = 0.0
              ) -> tuple[float, float]:
    """Where does a ray from ``(sx, sy)`` toward ``(cx, cy)`` cross
    the perimeter of an axis-aligned rectangle at ``(cx, cy)`` with
    width ``w`` and height ``h``?

    Same convention as ``pill_edge`` — returns the boundary point
    (with optional ``margin`` axis units outward) so an arrow can
    terminate at the rectangle's edge instead of its centre.
    """
    dx, dy = cx - sx, cy - sy
    d = _math.hypot(dx, dy)
    if d == 0:
        return (cx, cy)
    hw, hh = w / 2.0, h / 2.0
    if abs(dx) * hh >= abs(dy) * hw:
        t = hw / abs(dx)
    else:
        t = hh / abs(dy)
    udx, udy = dx / d, dy / d
    return (cx - t * dx - margin * udx, cy - t * dy - margin * udy)
