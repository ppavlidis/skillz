"""pavlab_stripchart — opinionated lab-style strip chart.

One categorical axis, one continuous axis, points jittered horizontally.
Shares all style helpers with pavlab_scatter.

Usage
-----
    from pavlab_stripchart import pavlab_stripchart

    # basic: all black points
    pavlab_stripchart(groups, values, xlabel="Condition", ylabel="Expression")

    # categorical colour → lab accent palette + legend
    pavlab_stripchart(groups, values, color=cell_type_labels)

    # numeric colour → viridis colorbar
    pavlab_stripchart(groups, values, color=scores, color_label="score")

    # explicit group order + grand-mean line
    pavlab_stripchart(groups, values, order=["WT", "KO", "DKO"],
                      show_mean=True)

    # log-scaled y axis
    pavlab_stripchart(groups, values, log_y="log2", ylabel="TPM")

    # save
    pavlab_stripchart(groups, values, filename="fig2b.svg", figsize=(4, 5))

    # embed in a multi-panel figure
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    pavlab_stripchart(g1, v1, ax=axes[0])
    pavlab_stripchart(g2, v2, ax=axes[1])
"""

from __future__ import annotations

import warnings
from typing import Any, Union

import matplotlib.pyplot as plt
import numpy as np

try:
    from .pavlab_scatter import (
        _pick_log_kind,
        _apply_log,
        _axis_label,
        _font_sizes,
        _maybe_warn_log,
        _resolve_color,
        _BLACK,
        _N_ALPHA,
    )
except ImportError:
    from pavlab_scatter import (  # script / sys.path style
        _pick_log_kind,
        _apply_log,
        _axis_label,
        _font_sizes,
        _maybe_warn_log,
        _resolve_color,
        _BLACK,
        _N_ALPHA,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MEAN_COLOR = "#9ca3af"   # gray-400
_N_DENSITY  = 10_000      # alpha floor threshold (no hexbin mode in stripchart)

LogScale = Union[bool, str]   # False | True | "log2" | "log10"


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def pavlab_stripchart(
    x,
    y,
    color=None,
    color_label: str | None = None,
    jitter: float = 0.2,
    show_mean: bool = False,
    show_median: bool = False,
    order: list[str] | None = None,
    label_size: str | float = "med",
    xlabel: str | None = None,
    ylabel: str | None = None,
    title: str | None = None,
    log_y: LogScale = False,
    pseudocount: float = 1.0,
    origin_zero: bool = True,
    ylim: tuple | None = None,
    point_size: float | None = None,
    filename=None,
    figsize: tuple | None = None,
    ax=None,
) -> Any:
    """Pavlab-style strip chart (jittered categorical scatter).

    Parameters
    ----------
    x : array-like of str
        Group labels, one per observation.
    y : array-like of float
        Continuous values, one per observation.
    color : None | str | array-like, optional
        None → all black. A single matplotlib color string → uniform color.
        An array of strings → categorical colors (lab accent palette + legend).
        An array of floats → viridis colormap + colorbar.
    color_label : str, optional
        Colorbar label for continuous color.
    jitter : float
        Half-width of uniform horizontal jitter applied within each group
        column. Default 0.2. Set 0 to disable.
    show_mean : bool
        If True, draw the grand mean of all y values as a full-width dashed
        horizontal line (gray-400, linewidth=1, zorder below points).
    show_median : bool
        If True, draw the grand median as a full-width dotted horizontal line
        (same color and linewidth as mean line, zorder below points).
    order : list of str, optional
        Explicit group display order. Groups absent from order are silently
        dropped. Groups listed in order with no data are skipped with a warning.
    label_size : "small" | "med" | "large" | float
        Axis-label font size preset.
    xlabel, ylabel : str, optional
        Axis labels. Log-scale suffix appended automatically when a transform
        is applied.
    title : str, optional
        Figure title. Left-aligned, normal weight.
    log_y : False | True | "log2" | "log10"
        Log-transform the y axis. True auto-selects: log10 when max > 1 000
        (counts), log2 otherwise. pseudocount is added before transforming.
        A warning is issued when data spans > 100× without a transform.
    pseudocount : float
        Added to y values before log transform. Default 1.
    origin_zero : bool
        If True (default) and all post-transform y values ≥ 0, pin y-axis
        lower bound to 0. Explicit ylim= takes precedence.
    ylim : (lo, hi) | None
        Explicit y-axis limits.
    point_size : float | None
        Override automatic marker size. Default: s=20 for N ≤ 500, s=10
        otherwise (counted across all groups).
    filename : str | Path | None
        Save to file; format inferred from extension. Ignored when ax= is
        supplied.
    figsize : (w, h) | None
        Figure size in inches. Default (5.0, 5.0). Ignored when ax= is
        supplied.
    ax : matplotlib Axes | None
        Draw into an existing Axes.

    Returns
    -------
    matplotlib Axes
    """
    # ---- coerce inputs --------------------------------------------------
    x_raw = np.asarray(x, dtype=object).ravel()
    y_arr = np.asarray(y, dtype=float).ravel()
    if len(x_raw) != len(y_arr):
        raise ValueError(
            f"x and y must have equal length ({len(x_raw)} vs {len(y_arr)})"
        )

    color_raw = np.asarray(color) if color is not None else None
    if color_raw is not None and color_raw.ndim == 1 and len(color_raw) != len(x_raw):
        raise ValueError(
            f"color array length ({len(color_raw)}) must match x/y ({len(x_raw)})"
        )

    # ---- drop non-finite y ----------------------------------------------
    finite_mask = np.isfinite(y_arr)
    if not finite_mask.all():
        x_raw = x_raw[finite_mask]
        y_arr = y_arr[finite_mask]
        if color_raw is not None and color_raw.ndim == 1 and len(color_raw) == len(finite_mask):
            color_raw = color_raw[finite_mask]

    if len(y_arr) == 0:
        warnings.warn("pavlab_stripchart: no finite data points to plot.", stacklevel=2)

    # ---- resolve group order --------------------------------------------
    seen_groups: list[str] = list(dict.fromkeys(x_raw.tolist()))

    if order is not None:
        unique_groups = []
        for g in order:
            if g not in seen_groups:
                warnings.warn(
                    f"pavlab_stripchart: group {g!r} listed in order has no data; "
                    "skipping.",
                    stacklevel=2,
                )
            else:
                unique_groups.append(g)
        group_set = set(unique_groups)
        keep = np.array([g in group_set for g in x_raw.tolist()], dtype=bool)
        x_raw = x_raw[keep]
        y_arr = y_arr[keep]
        if color_raw is not None and color_raw.ndim == 1:
            color_raw = color_raw[keep]
    else:
        unique_groups = seen_groups

    n = len(y_arr)

    # ---- suggest / apply log on y --------------------------------------
    if log_y is False:
        _maybe_warn_log(y_arr, "y")

    y_kind = _pick_log_kind(log_y, y_arr, "y")
    if y_kind:
        neg = int(np.sum(np.isfinite(y_arr) & (y_arr + pseudocount <= 0)))
        if neg:
            warnings.warn(
                f"pavlab_stripchart: {neg} y value(s) will produce -inf after "
                f"log transform (pseudocount={pseudocount} insufficient).",
                stacklevel=2,
            )
        y_arr = _apply_log(y_arr, y_kind, pseudocount)

    # ---- build integer x positions + jitter ----------------------------
    group_index = {g: i for i, g in enumerate(unique_groups)}
    x_int = np.array([group_index[g] for g in x_raw.tolist()], dtype=float)
    if jitter > 0:
        x_int = x_int + np.random.uniform(-jitter, jitter, size=n)

    # ---- colour resolution ---------------------------------------------
    # Single color string must bypass _resolve_color, which treats a 0-d
    # string array as a 1-character iterable and produces garbage categories.
    if isinstance(color, str):
        c_arg, cmap_arg, norm_arg, legend_handles, is_single = color, None, None, None, True
    else:
        color_arg = color_raw if (color_raw is not None and color_raw.ndim == 1) else color
        c_arg, cmap_arg, norm_arg, legend_handles, is_single = _resolve_color(color_arg, n)

    # ---- marker size + alpha -------------------------------------------
    ps = float(point_size) if point_size is not None else (
        20.0 if n <= _N_ALPHA else 10.0
    )
    if n <= _N_ALPHA:
        alpha = 1.0
    else:
        frac = min(1.0, (n - _N_ALPHA) / max(1, _N_DENSITY - _N_ALPHA))
        alpha = max(0.15, 0.6 - frac * 0.45)

    # ---- figure setup --------------------------------------------------
    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=figsize or (5.0, 5.0))
    else:
        fig = ax.figure

    ax.set_facecolor("white")
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    label_pt, tick_pt = _font_sizes(label_size)

    # ---- mean / median reference lines (below points) ------------------
    if (show_mean or show_median) and n > 0:
        x_span_lo = -0.5
        x_span_hi = len(unique_groups) - 0.5

    if show_mean and n > 0:
        grand_mean = float(np.mean(y_arr[np.isfinite(y_arr)]))
        ax.hlines(
            grand_mean,
            x_span_lo,
            x_span_hi,
            colors=_MEAN_COLOR,
            linewidths=1,
            linestyles="dashed",
            zorder=1,
        )

    if show_median and n > 0:
        grand_median = float(np.median(y_arr[np.isfinite(y_arr)]))
        ax.hlines(
            grand_median,
            x_span_lo,
            x_span_hi,
            colors=_MEAN_COLOR,
            linewidths=1,
            linestyles="dotted",
            zorder=1,
        )

    # ---- draw points ---------------------------------------------------
    sc_kw: dict[str, Any] = {
        "s": ps,
        "alpha": alpha,
        "linewidths": 0,
        "marker": "o",
        "zorder": 2,
    }
    if is_single:
        sc_kw["color"] = c_arg
    else:
        sc_kw["c"] = c_arg
        if cmap_arg is not None:
            sc_kw["cmap"] = cmap_arg
        if norm_arg is not None:
            sc_kw["norm"] = norm_arg

    sc = ax.scatter(x_int, y_arr, **sc_kw)

    if cmap_arg is not None:
        cb = fig.colorbar(sc, ax=ax)
        if color_label:
            cb.set_label(color_label, fontsize=tick_pt)

    if legend_handles:
        ax.legend(handles=legend_handles, frameon=False, fontsize=tick_pt)

    # ---- x-axis ticks + labels -----------------------------------------
    ax.set_xticks(range(len(unique_groups)))
    ax.set_xticklabels(unique_groups)
    ax.set_xlim(-0.5, len(unique_groups) - 0.5)

    # ---- y-axis limits -------------------------------------------------
    if ylim is not None:
        ax.set_ylim(ylim)
    else:
        fy = y_arr[np.isfinite(y_arr)]
        if origin_zero and fy.size > 0 and float(fy.min()) >= 0:
            ax.set_ylim(bottom=0)

    # ---- axis labels + title -------------------------------------------
    xl = xlabel or ""
    yl = _axis_label(ylabel, y_kind)
    if xl:
        ax.set_xlabel(xl, fontsize=label_pt)
    if yl:
        ax.set_ylabel(yl, fontsize=label_pt)
    if title:
        ax.set_title(title, fontsize=label_pt, loc="left", fontweight="normal")

    ax.tick_params(axis="both", labelsize=tick_pt)

    # ---- output --------------------------------------------------------
    if own_fig:
        fig.tight_layout()
        if filename is not None:
            fig.savefig(filename, dpi=200)
            plt.close(fig)

    return ax
