"""pavlab_boxplot — opinionated lab-style boxplot.

Used **sparingly**. The box itself — quartiles + whiskers + median —
IS the spread/uncertainty visualization; no separate overlaid error
bar is drawn. Two modes:

  - ``show_points=True`` (default): raw data points (swarmed) under
    the box. Points show the actual distribution; the box gives a
    structural summary.
  - ``show_points=False``: compact box only (quartiles + whiskers +
    median). Used in multi-panel figures where visual compactness
    matters and the box's own whiskers carry the spread information.

There is intentionally no ``error=`` parameter: a separate
mean ± SD / ± 95% CI bar overlaid on top of a box would double up the
spread cue the box already encodes via its whiskers and IQR, and the
lab convention is that the box itself does that job. Helpers for
parameter-estimate plots (forest plots, regression-coefficient charts,
etc.) WILL carry an error-bar API in the future, following the
cross-plot rule documented in ``feedback_error_bars_never_sem.md`` —
SD for raw-data charts, 95% CI for parameter-estimate charts, never
SEM.

Usage
-----
    from pavlab_boxplot import pavlab_boxplot

    pavlab_boxplot(groups, values, ylabel="Expression")
    pavlab_boxplot(groups, values, show_points=False)        # compact
    pavlab_boxplot(groups, values, points_kind="strip")      # jittered
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
        _N_ALPHA,
    )
    from .pavlab_stripchart import _swarm_x_offsets
except ImportError:
    from pavlab_scatter import (  # script / sys.path style
        _pick_log_kind,
        _apply_log,
        _axis_label,
        _font_sizes,
        _maybe_warn_log,
        _resolve_color,
        _N_ALPHA,
    )
    from pavlab_stripchart import _swarm_x_offsets

# Style constants — match the rest of the plotting skill / CLAUDE.md.
_BOX_COLOR    = "#1f2937"   # gray-800 (TEXT) for box outline + median
_POINT_COLOR  = "#374151"   # gray-700 — slightly lighter than the box so the
                            # box reads as the structural element on top of
                            # the raw points (which are the "data layer").
_BOX_FILL     = "#f3f4f6"   # gray-100 — very pale box fill so the points
                            # underneath stay readable.
_BOX_LW       = 1.2
_MEDIAN_LW    = 1.6
_WHISKER_LW   = 1.0
_CAP_LW       = 1.0
_BOX_WIDTH    = 0.55

LogScale = Union[bool, str]


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def pavlab_boxplot(
    x,
    y,
    color=None,
    color_label: str | None = None,
    show_points: bool = True,
    points_kind: str = "swarm",
    jitter: float = 0.2,
    box_width: float = _BOX_WIDTH,
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
    """Pavlab-style boxplot with raw-points underlayer and error-bar overlay.

    Parameters
    ----------
    x : array-like of str
        Group labels, one per observation.
    y : array-like of float
        Continuous values, one per observation.
    color : None | str | array-like, optional
        Point colour: None → gray-700; single color string → uniform;
        array of strings → categorical colors + legend; array of floats
        → viridis colorbar. Only the *point* layer respects ``color`` —
        the box itself always uses the lab structural colour.
    color_label : str, optional
        Colorbar label for continuous color.
    show_points : bool
        Draw raw data points underneath the box. Default True — the
        lab default. Set False for a compact box-only chart; the
        whiskers and IQR still convey the spread.
    points_kind : "strip" | "swarm"
        Layout for the points underlayer. ``"swarm"`` (default) packs
        points non-overlappingly via the same beeswarm algorithm as
        ``pavlab_stripchart(kind="swarm")``. ``"strip"`` uses uniform
        horizontal jitter.
    jitter : float
        Half-width of horizontal jitter when ``points_kind="strip"``.
        Default 0.2. Ignored under swarm.
    box_width : float
        Width of each box in x-data units. Default 0.55 (boxes sit
        comfortably within the 1.0-wide category column with room for
        the points underlayer to extend slightly past the box edges).
    order, label_size, xlabel, ylabel, title, log_y, pseudocount,
    origin_zero, ylim, point_size, filename, figsize, ax
        Same semantics as ``pavlab_stripchart``.

    Returns
    -------
    matplotlib Axes
    """
    # ---- validate / coerce inputs --------------------------------------
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

    pk = points_kind.lower() if isinstance(points_kind, str) else "swarm"
    if pk not in ("strip", "swarm"):
        raise ValueError(f"points_kind must be 'strip' or 'swarm', got {points_kind!r}")

    # ---- drop non-finite y ---------------------------------------------
    finite_mask = np.isfinite(y_arr)
    if not finite_mask.all():
        x_raw = x_raw[finite_mask]
        y_arr = y_arr[finite_mask]
        if color_raw is not None and color_raw.ndim == 1 and len(color_raw) == len(finite_mask):
            color_raw = color_raw[finite_mask]

    if len(y_arr) == 0:
        warnings.warn("pavlab_boxplot: no finite data points to plot.", stacklevel=2)

    # ---- resolve group order -------------------------------------------
    seen_groups: list[str] = list(dict.fromkeys(x_raw.tolist()))
    if order is not None:
        unique_groups = []
        for g in order:
            if g not in seen_groups:
                warnings.warn(
                    f"pavlab_boxplot: group {g!r} listed in order has no "
                    "data; skipping.",
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

    # ---- log transform (matches pavlab_stripchart) ---------------------
    if log_y is False:
        _maybe_warn_log(y_arr, "y")
    y_kind = _pick_log_kind(log_y, y_arr, "y")
    if y_kind:
        neg = int(np.sum(np.isfinite(y_arr) & (y_arr + pseudocount <= 0)))
        if neg:
            warnings.warn(
                f"pavlab_boxplot: {neg} y value(s) will produce -inf after "
                f"log transform (pseudocount={pseudocount} insufficient).",
                stacklevel=2,
            )
        y_arr = _apply_log(y_arr, y_kind, pseudocount)

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

    # Lock x/y limits BEFORE drawing so the swarm transform is meaningful.
    # We can't rely on matplotlib's auto-fit (nothing's been drawn yet),
    # so compute ylim from the data directly with a small margin.
    group_index = {g: i for i, g in enumerate(unique_groups)}
    ax.set_xlim(-0.5, len(unique_groups) - 0.5)
    if ylim is not None:
        ax.set_ylim(ylim)
    else:
        fy = y_arr[np.isfinite(y_arr)]
        if fy.size > 0:
            y_lo = float(fy.min())
            y_hi = float(fy.max())
            margin = max(1e-9, 0.05 * (y_hi - y_lo)) if y_hi > y_lo else 1.0
            if origin_zero and y_lo >= 0:
                ax.set_ylim(0, y_hi + margin)
            else:
                ax.set_ylim(y_lo - margin, y_hi + margin)

    # ---- per-group data --------------------------------------------------
    groups_arr = np.array([group_index[g] for g in x_raw.tolist()], dtype=int)
    per_group_y = [y_arr[groups_arr == gi] for gi in range(len(unique_groups))]

    # ---- raw points underneath (lowest zorder) -------------------------
    if show_points and n > 0:
        ps = float(point_size) if point_size is not None else (
            20.0 if n <= _N_ALPHA else 10.0
        )
        # Build per-point x position.
        x_pts = np.array(groups_arr, dtype=float)
        if pk == "swarm":
            for gi in range(len(unique_groups)):
                mask = groups_arr == gi
                if not np.any(mask):
                    continue
                offs = _swarm_x_offsets(y_arr[mask], ax, ps)
                # Clip swarm offsets to box_width so points stay roughly
                # within the box's horizontal footprint.
                clip = box_width * 0.45
                offs = np.clip(offs, -clip, clip)
                x_pts[mask] = gi + offs
        else:
            if jitter > 0:
                x_pts = x_pts + np.random.uniform(-jitter, jitter, size=n)

        # Resolve point colour. Mirrors pavlab_stripchart's colour logic.
        if color is None:
            c_arg, cmap_arg, norm_arg, legend_handles, is_single = (
                _POINT_COLOR, None, None, None, True,
            )
        elif isinstance(color, str):
            c_arg, cmap_arg, norm_arg, legend_handles, is_single = (
                color, None, None, None, True,
            )
        else:
            color_arg = (
                color_raw if (color_raw is not None and color_raw.ndim == 1)
                else color
            )
            c_arg, cmap_arg, norm_arg, legend_handles, is_single = _resolve_color(
                color_arg, n,
            )

        if n <= _N_ALPHA:
            alpha = 1.0
        else:
            frac = min(1.0, (n - _N_ALPHA) / max(1, 10_000 - _N_ALPHA))
            alpha = max(0.15, 0.6 - frac * 0.45)

        sc_kw: dict[str, Any] = {
            "s": ps,
            "alpha": alpha,
            "linewidths": 0,
            "marker": "o",
            "zorder": 1,  # below the box
        }
        if is_single:
            sc_kw["color"] = c_arg
        else:
            sc_kw["c"] = c_arg
            if cmap_arg is not None:
                sc_kw["cmap"] = cmap_arg
            if norm_arg is not None:
                sc_kw["norm"] = norm_arg
        sc = ax.scatter(x_pts, y_arr, **sc_kw)
        if cmap_arg is not None:
            cb = fig.colorbar(sc, ax=ax)
            if color_label:
                cb.set_label(color_label, fontsize=tick_pt)
        if legend_handles:
            ax.legend(handles=legend_handles, frameon=False, fontsize=tick_pt)

    # ---- the box itself ------------------------------------------------
    # Skip empty groups (matplotlib boxplot dislikes empty arrays).
    positions = []
    box_data = []
    for gi, ys in enumerate(per_group_y):
        if ys.size > 0:
            positions.append(gi)
            box_data.append(ys)

    if box_data:
        bp = ax.boxplot(
            box_data,
            positions=positions,
            widths=box_width,
            showfliers=False,           # raw points already show outliers
            patch_artist=True,
            medianprops=dict(color=_BOX_COLOR, linewidth=_MEDIAN_LW),
            boxprops=dict(facecolor=_BOX_FILL, edgecolor=_BOX_COLOR,
                          linewidth=_BOX_LW, alpha=0.85),
            whiskerprops=dict(color=_BOX_COLOR, linewidth=_WHISKER_LW),
            capprops=dict(color=_BOX_COLOR, linewidth=_CAP_LW),
            zorder=2,
        )
        # boxplot's per-artist zorder kwarg is honored for the patch but
        # not for whiskers/medians in older mpl. Belt-and-braces:
        for line in bp["whiskers"] + bp["medians"] + bp["caps"]:
            line.set_zorder(2.5)
        for patch in bp["boxes"]:
            patch.set_zorder(2)

    # ---- re-apply x-tick labels (matplotlib's boxplot overrides them) --
    ax.set_xticks(range(len(unique_groups)))
    ax.set_xticklabels(unique_groups)

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

    # ---- save ----------------------------------------------------------
    if own_fig:
        fig.tight_layout()
        if filename is not None:
            fig.savefig(filename, dpi=200)
            plt.close(fig)

    return ax
