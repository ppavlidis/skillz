"""pavlab bar-plot helpers — single + paired bars with publication-grade
defaults baked in.

Wraps ``ax.bar()`` with the lab pattern:
- Wilson 95 % CI error bars by default (or caller-supplied yerr).
- ``ERR_KW`` / ``ERR_CAPSIZE`` from pavlab_style applied automatically.
- Optional darker edge outline for highlighted bars (e.g. "this is an
  LLM method" vs lexical baselines).
- ``paired_bars()`` for the very common "two values per category"
  pattern (exact vs cross-walk match, strict vs lenient quote
  verification, before vs after a prompt patch) — the lighter bar
  uses :func:`pavlab_style.lighten` instead of ``alpha=``, so the
  pair survives EPS export to Adobe Illustrator.

Public API
----------
``pavlab_barplot(ax, x, values, colors=…, …)``
``paired_bars(ax, x, values_left, values_right, colors=…, …)``
``wilson_err(k, n, z=1.96)``  — per-bar (lower, upper) tuple suitable
                                for matplotlib ``yerr``.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

import matplotlib as mpl

from .pavlab_style import (
    ERR_KW,
    ERR_CAPSIZE,
    lighten,
)

__all__ = ["pavlab_barplot", "paired_bars", "wilson_err"]


# ---------------------------------------------------------------------------
def wilson_err(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95 % score interval, returned as the (lower_half_width,
    upper_half_width) tuple matplotlib's ``yerr`` expects.

    Lower / upper extents are clipped to [0, 1] — if ``k == n``, the
    upper half-width is 0 (no upper extension, the bar already sits
    at 1.0)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom  = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half   = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return (p - lo, hi - p)


# ---------------------------------------------------------------------------
def _edge_seq(highlight: Optional[Sequence[bool]], n: int,
              edge_color: str) -> list[str]:
    """Resolve the per-bar edge colour from a ``highlight`` mask: True →
    edge_color, False → 'none'. ``None`` means "no edges anywhere"."""
    if highlight is None:
        return ["none"] * n
    if len(highlight) != n:
        raise ValueError(f"highlight length {len(highlight)} ≠ #bars {n}")
    return [edge_color if h else "none" for h in highlight]


def pavlab_barplot(
    ax,
    x: Sequence[float],
    values: Sequence[float],
    *,
    colors: Sequence[str],
    width: float = 0.65,
    yerr: Optional[Sequence] = None,
    highlight: Optional[Sequence[bool]] = None,
    edge_color: str = "#1f2937",
    edge_linewidth: float = 2.0,
    annotate: bool = True,
    annotate_fmt: str = "{v:.1%}",
):
    """Single-row bar plot with the lab's publication defaults.

    Parameters
    ----------
    ax : matplotlib axes
    x : positions for each bar (typically range(n))
    values : bar heights (one per x)
    colors : per-bar facecolour (hex or rgba)
    width : bar width, default 0.65
    yerr : matplotlib-shape yerr (either a sequence of (lo, hi) or a
        pair of sequences). Defaults to no error bars; callers wanting
        Wilson CIs should compute them with ``wilson_err()`` and pass
        the result here.
    highlight : optional per-bar boolean mask. ``True`` bars get a
        dark outline (lab convention: "this is an LLM / our method");
        ``False`` bars get no outline.
    edge_color : edge colour for highlighted bars (default near-black).
    edge_linewidth : edge stroke weight for highlighted bars (default
        2 pt — matches the axis spine weight).
    annotate : if True, place the bar value above each bar.
    annotate_fmt : format string for the annotation, applied as
        ``annotate_fmt.format(v=value)``. Default is percent with one
        decimal.

    Returns the matplotlib ``BarContainer``."""
    n = len(values)
    if len(x) != n or len(colors) != n:
        raise ValueError("x, values, and colors must all have the same length")
    edges = _edge_seq(highlight, n, edge_color)
    bars = ax.bar(
        x, values,
        width=width,
        color=list(colors),
        edgecolor=edges,
        linewidth=edge_linewidth,
        yerr=yerr,
        capsize=ERR_CAPSIZE if yerr is not None else 0,
        error_kw=ERR_KW if yerr is not None else None,
    )
    if annotate:
        # Place annotation above the upper CI cap if yerr is given.
        upper = None
        if yerr is not None:
            try:
                # yerr can be (lo, hi) pair-of-sequences or sequence of pairs.
                upper = list(yerr[1])
            except Exception:
                upper = None
        for i, (bar, v) in enumerate(zip(bars, values)):
            extra = upper[i] if upper else 0.0
            ax.annotate(
                annotate_fmt.format(v=v),
                xy=(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + extra + 0.012),
                ha="center", va="bottom",
                fontsize=11, color="#1f2937",
            )
    return bars


# ---------------------------------------------------------------------------
def paired_bars(
    ax,
    x: Sequence[float],
    values_left: Sequence[float],
    values_right: Sequence[float],
    *,
    colors: Sequence[str],
    label_left: str = "Group A",
    label_right: str = "Group B",
    width: float = 0.36,
    yerr_left: Optional[Sequence] = None,
    yerr_right: Optional[Sequence] = None,
    highlight: Optional[Sequence[bool]] = None,
    edge_color: str = "#1f2937",
    edge_linewidth: float = 2.0,
    light_frac: float = 0.55,
    annotate: bool = True,
    annotate_fmt: str = "{v:.1%}",
):
    """Two bars per category, EPS-safe.

    The left ("A") bar uses a lightened tint of each category's colour
    via :func:`pavlab_style.lighten` — *not* ``alpha=0.55``, which is
    silently dropped by the EPS writer and would make the two bars
    render identical-solid in Illustrator. The right ("B") bar uses
    the full colour. Each pair is centred on ``x[i]`` and offset by
    ``±width/2``.

    Use for: exact vs cross-walk match, strict vs lenient
    verification, before vs after a prompt patch, train vs test, etc.

    Parameters mirror :func:`pavlab_barplot`; the extras are:

    label_left / label_right
        Legend labels for the two bar series.
    light_frac
        How much to blend with white for the left bar's facecolour.
        ``0.55`` → ~45 %-saturation tint (the lab default). Larger →
        paler. ``0`` would leave the bars identical (don't do that).

    Returns ``(bars_left, bars_right)``."""
    n = len(values_left)
    if len(values_right) != n or len(x) != n or len(colors) != n:
        raise ValueError("x, values_left, values_right, colors must all match length")
    edges = _edge_seq(highlight, n, edge_color)
    light_colors = [lighten(c, light_frac) for c in colors]

    bars_left = ax.bar(
        [xi - width / 2 for xi in x], values_left,
        width=width,
        color=light_colors,
        edgecolor=edges,
        linewidth=edge_linewidth,
        yerr=yerr_left,
        capsize=ERR_CAPSIZE if yerr_left is not None else 0,
        error_kw=ERR_KW if yerr_left is not None else None,
        label=label_left,
    )
    bars_right = ax.bar(
        [xi + width / 2 for xi in x], values_right,
        width=width,
        color=list(colors),
        edgecolor=edges,
        linewidth=edge_linewidth,
        yerr=yerr_right,
        capsize=ERR_CAPSIZE if yerr_right is not None else 0,
        error_kw=ERR_KW if yerr_right is not None else None,
        label=label_right,
    )

    if annotate:
        for side, bars, values, yerr in (
            ("L", bars_left,  values_left,  yerr_left),
            ("R", bars_right, values_right, yerr_right),
        ):
            upper = None
            if yerr is not None:
                try:
                    upper = list(yerr[1])
                except Exception:
                    upper = None
            for i, (bar, v) in enumerate(zip(bars, values)):
                extra = upper[i] if upper else 0.0
                ax.annotate(
                    annotate_fmt.format(v=v),
                    xy=(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + extra + 0.012),
                    ha="center", va="bottom",
                    fontsize=11, color="#1f2937",
                )

    return bars_left, bars_right
