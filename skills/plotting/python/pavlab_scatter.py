"""pavlab_scatter — opinionated lab-style scatter plot.

Defaults: black filled circles, no background, no gridlines, large axis
labels. Automatically adapts rendering to N:
  N ≤ 500         full-opacity circles (s=20)
  500 < N ≤ 10 000 semi-transparent circles (alpha scales 0.60 → 0.15)
  N > 10 000       hexbin density (black-body palette)

Usage
-----
    from pavlab_scatter import pavlab_scatter

    # basic
    pavlab_scatter(x, y)

    # log-scaled axes — label gets "(log₂)" suffix automatically
    pavlab_scatter(x, y, xlabel="TPM rep1", ylabel="TPM rep2",
                   log_x="log2", log_y="log2")

    # categorical colour → lab accent palette + legend
    pavlab_scatter(x, y, color=cell_type_labels, xlabel="PC1", ylabel="PC2")

    # numeric colour → viridis colorbar
    pavlab_scatter(x, y, color=scores, color_label="score")

    # save
    pavlab_scatter(x, y, filename="fig3a.pdf", figsize=(4, 4))

    # embed in a multi-panel figure
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    pavlab_scatter(x1, y1, ax=axes[0])
    pavlab_scatter(x2, y2, ax=axes[1])
"""

from __future__ import annotations

import warnings
from typing import Any, Union

import matplotlib.pyplot as plt
import numpy as np

try:
    from .palettes import black_body_palette
except ImportError:
    from palettes import black_body_palette  # script / sys.path style

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BLACK = "#000000"

# Lab accent palette (Tailwind-style, matches global lab convention)
_ACCENT_COLORS = [
    "#2563eb",  # blue-600   – primary
    "#10b981",  # emerald-500
    "#f59e0b",  # amber-500
    "#ef4444",  # red-500
    "#8b5cf6",  # violet-500
    "#ec4899",  # pink-500
    "#14b8a6",  # teal-500
    "#f97316",  # orange-500
]

_N_ALPHA: int = 500        # above this N: add transparency
_N_DENSITY: int = 10_000   # above this N: switch to hexbin

# (axis-label pt, tick-label pt)
_LABEL_SIZES: dict[str, tuple[float, float]] = {
    "small": (10.0,  8.0),
    "med":   (14.0, 11.0),
    "large": (18.0, 14.0),
}

LogScale = Union[bool, str]   # False | True | "log2" | "log10"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _pick_log_kind(val: LogScale, arr: np.ndarray, axis: str) -> str | None:
    """Resolve a LogScale value to 'log2', 'log10', or None (no transform)."""
    if val is False or val is None:
        return None
    if val is True:
        pos = arr[np.isfinite(arr) & (arr > 0)]
        if pos.size == 0:
            warnings.warn(
                f"pavlab_scatter: {axis}-axis has no positive values; "
                "log transform skipped.",
                stacklevel=3,
            )
            return None
        # Heuristic: large counts → log10; biological/moderate range → log2.
        return "log10" if float(pos.max()) > 1_000 else "log2"
    if val in ("log2", "log10"):
        return str(val)
    raise ValueError(
        f"log_{axis} must be False, True, 'log2', or 'log10'; got {val!r}"
    )


def _apply_log(arr: np.ndarray, kind: str, pseudocount: float) -> np.ndarray:
    """Apply log2 or log10 after adding pseudocount."""
    shifted = arr + pseudocount
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log2(shifted) if kind == "log2" else np.log10(shifted)


def _axis_label(base: str | None, log_kind: str | None) -> str:
    """'FPKM' + 'log2' → 'FPKM (log₂)'; None + 'log2' → '(log₂)'."""
    suffix_map = {"log2": "(log₂)", "log10": "(log₁₀)"}
    parts = [p for p in [base, suffix_map.get(log_kind or "")] if p]
    return " ".join(parts)


def _font_sizes(label_size: str | float) -> tuple[float, float]:
    """Return (axis_label_pt, tick_label_pt)."""
    if isinstance(label_size, str):
        try:
            return _LABEL_SIZES[label_size]
        except KeyError:
            raise ValueError(
                f"label_size must be 'small', 'med', 'large', or a number; "
                f"got {label_size!r}"
            )
    v = float(label_size)
    return v, round(v * 0.78, 1)


def _maybe_warn_log(arr: np.ndarray, axis: str) -> None:
    """Suggest log scale when data spans more than two orders of magnitude."""
    pos = arr[np.isfinite(arr) & (arr > 0)]
    if pos.size < 2:
        return
    ratio = float(pos.max()) / float(pos.min())
    if ratio > 100:
        warnings.warn(
            f"pavlab_scatter: {axis}-axis spans {ratio:.0f}× — "
            f"consider log_{axis}='log2' (biological) or 'log10' (counts).",
            stacklevel=3,
        )


def _resolve_color(color, n: int):
    """Parse the color argument.

    Returns (c_arg, cmap, norm, legend_handles, is_single_color).
    When is_single_color=True use `color=` kwarg to ax.scatter (not `c=`).
    """
    import matplotlib.patches as mpatches
    from matplotlib.colors import Normalize

    if color is None:
        return _BLACK, None, None, None, True  # uniform black → color=

    arr = np.asarray(color)

    # Categorical (string / object dtype) → lab accent palette + legend
    if arr.dtype.kind in ("U", "S", "O"):
        categories = list(dict.fromkeys(arr.tolist()))
        cat_color = {
            cat: _ACCENT_COLORS[i % len(_ACCENT_COLORS)]
            for i, cat in enumerate(categories)
        }
        c_list = [cat_color[v] for v in arr.tolist()]
        handles = [
            mpatches.Patch(color=cat_color[cat], label=str(cat))
            for cat in categories
        ]
        return c_list, None, None, handles, False

    # Numeric → viridis colormap
    norm = Normalize(vmin=float(np.nanmin(arr)), vmax=float(np.nanmax(arr)))
    return arr, "viridis", norm, None, False


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def pavlab_scatter(
    x,
    y,
    color=None,
    color_label: str | None = None,
    label_size: str | float = "med",
    xlabel: str | None = None,
    ylabel: str | None = None,
    title: str | None = None,
    log_x: LogScale = False,
    log_y: LogScale = False,
    pseudocount: float = 1.0,
    origin_zero: bool = True,
    xlim: tuple | None = None,
    ylim: tuple | None = None,
    point_size: float | None = None,
    filename=None,
    figsize: tuple | None = None,
    ax=None,
    **kwargs: Any,
):
    """Pavlab-style scatter plot.

    Parameters
    ----------
    x, y : array-like
        Data coordinates. NaN / inf pairs are silently dropped.
    color : None | str | array-like, optional
        None → all black. A single matplotlib color string → uniform color.
        An array of strings → categorical colors (lab accent palette, legend
        added automatically). An array of numbers → viridis colormap +
        colorbar. In density mode (N > 10 000) color is ignored.
    color_label : str, optional
        Colorbar label for continuous color. Ignored for categorical color.
    label_size : "small" | "med" | "large" | float
        Axis-label font size preset. "large" (18 pt labels / 14 pt ticks)
        survives projector display and journal reduction to a 3-inch column.
    xlabel, ylabel : str, optional
        Axis labels. Log-scale suffix ("(log₂)" / "(log₁₀)") is appended
        automatically when a transform is applied.
    title : str, optional
        Figure title. Left-aligned, normal weight.
    log_x, log_y : False | True | "log2" | "log10"
        Log-transform the axis. True auto-selects: log10 when max > 1 000
        (counts), log2 otherwise (biological / expression). pseudocount is
        added before transforming (handles zeros). ln is never used.
        When not transforming, a warning is issued if data spans > 100×.
    pseudocount : float
        Added to values before log transform. Default 1.
    origin_zero : bool
        If True (default) and all (post-transform) data ≥ 0, pin the axis
        lower bound to 0. Explicit xlim= / ylim= take precedence.
    xlim, ylim : (lo, hi) | None
        Explicit axis limits. Take precedence over origin_zero.
    point_size : float | None
        Override the automatic marker size (matplotlib `s=`). Default: 20
        for N ≤ 500, 10 for N ≤ 10 000.
    filename : str | Path | None
        Save to file; format inferred from extension (.pdf, .png, .svg …).
        Ignored when ax= is supplied.
    figsize : (w, h) | None
        Figure size in inches. Default (5.5, 5.0). Ignored when ax= is
        supplied.
    ax : matplotlib Axes | None
        Draw into an existing Axes. figsize and filename are ignored.
    **kwargs
        Forwarded to ax.scatter (or ax.hexbin in density mode).

    Returns
    -------
    matplotlib Axes
    """
    # ---- coerce to 1-D float arrays -------------------------------------
    x_arr = np.asarray(x, dtype=float).ravel()
    y_arr = np.asarray(y, dtype=float).ravel()
    if len(x_arr) != len(y_arr):
        raise ValueError(
            f"x and y must have equal length ({len(x_arr)} vs {len(y_arr)})"
        )

    # Align per-point color with x/y, then drop non-finite pairs together.
    color_arr: Any = None
    c_tmp = np.asarray(color) if color is not None else None
    if c_tmp is not None and c_tmp.ndim == 1 and len(c_tmp) == len(x_arr):
        mask = np.isfinite(x_arr) & np.isfinite(y_arr)
        color_arr = c_tmp[mask]
        x_arr, y_arr = x_arr[mask], y_arr[mask]
    else:
        mask = np.isfinite(x_arr) & np.isfinite(y_arr)
        x_arr, y_arr = x_arr[mask], y_arr[mask]
        color_arr = color  # scalar or None — pass through unchanged

    n = len(x_arr)
    if n == 0:
        warnings.warn("pavlab_scatter: no finite data points to plot.", stacklevel=2)

    # ---- suggest log scale when not transforming ------------------------
    if log_x is False:
        _maybe_warn_log(x_arr, "x")
    if log_y is False:
        _maybe_warn_log(y_arr, "y")

    # ---- apply log transforms ------------------------------------------
    x_kind = _pick_log_kind(log_x, x_arr, "x")
    if x_kind:
        neg = int(np.sum(np.isfinite(x_arr) & (x_arr + pseudocount <= 0)))
        if neg:
            warnings.warn(
                f"pavlab_scatter: {neg} x value(s) will produce -inf after "
                f"log transform (pseudocount={pseudocount} insufficient).",
                stacklevel=2,
            )
        x_arr = _apply_log(x_arr, x_kind, pseudocount)

    y_kind = _pick_log_kind(log_y, y_arr, "y")
    if y_kind:
        neg = int(np.sum(np.isfinite(y_arr) & (y_arr + pseudocount <= 0)))
        if neg:
            warnings.warn(
                f"pavlab_scatter: {neg} y value(s) will produce -inf after "
                f"log transform (pseudocount={pseudocount} insufficient).",
                stacklevel=2,
            )
        y_arr = _apply_log(y_arr, y_kind, pseudocount)

    # ---- rendering mode ------------------------------------------------
    density_mode = n > _N_DENSITY
    if density_mode and color is not None:
        warnings.warn(
            "pavlab_scatter: N > 10 000; using hexbin density mode — "
            "'color' ignored.",
            stacklevel=2,
        )
        color_arr = None

    # ---- colour resolution ---------------------------------------------
    c_arg = cmap_arg = norm_arg = legend_handles = None
    is_single = True
    if not density_mode:
        c_arg, cmap_arg, norm_arg, legend_handles, is_single = \
            _resolve_color(color_arr, n)

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
        fig, ax = plt.subplots(figsize=figsize or (5.5, 5.0))
    else:
        fig = ax.figure

    ax.set_facecolor("white")
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # ---- draw ----------------------------------------------------------
    label_pt, tick_pt = _font_sizes(label_size)

    if density_mode:
        hb_kw: dict[str, Any] = {
            "cmap": black_body_palette(256),
            "mincnt": 1,
            "gridsize": 40,
        }
        hb_kw.update(kwargs)
        hb = ax.hexbin(x_arr, y_arr, **hb_kw)
        cb = fig.colorbar(hb, ax=ax)
        cb.set_label("count", fontsize=tick_pt)

    else:
        sc_kw: dict[str, Any] = {
            "s": ps,
            "alpha": alpha,
            "linewidths": 0,
            "marker": "o",
        }
        if is_single:
            sc_kw["color"] = c_arg   # uniform color: use color= not c=
        else:
            sc_kw["c"] = c_arg
            if cmap_arg is not None:
                sc_kw["cmap"] = cmap_arg
            if norm_arg is not None:
                sc_kw["norm"] = norm_arg
        sc_kw.update(kwargs)
        sc = ax.scatter(x_arr, y_arr, **sc_kw)

        if cmap_arg is not None:
            cb = fig.colorbar(sc, ax=ax)
            if color_label:
                cb.set_label(color_label, fontsize=tick_pt)

        if legend_handles:
            ax.legend(handles=legend_handles, frameon=False, fontsize=tick_pt)

    # ---- axis limits ---------------------------------------------------
    if xlim is not None:
        ax.set_xlim(xlim)
    else:
        fx = x_arr[np.isfinite(x_arr)]
        if origin_zero and fx.size > 0 and float(fx.min()) >= 0:
            ax.set_xlim(left=0)

    if ylim is not None:
        ax.set_ylim(ylim)
    else:
        fy = y_arr[np.isfinite(y_arr)]
        if origin_zero and fy.size > 0 and float(fy.min()) >= 0:
            ax.set_ylim(bottom=0)

    # ---- labels --------------------------------------------------------
    xl = _axis_label(xlabel, x_kind)
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
