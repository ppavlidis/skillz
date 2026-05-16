"""pavlab_density — opinionated lab-style density / histogram / violin plot.

Shares all style helpers with pavlab_scatter. Supports three kinds:
  "density"   — kernel-density estimate with optional reflection at bounds
  "histogram" — frequency or count histogram with shared bin edges across groups
  "violin"    — split violin bodies per group on a categorical axis

Usage
-----
    from pavlab_density import pavlab_density

    # single distribution
    pavlab_density(expr_values, xlabel="log2 TPM", title="Expression")

    # overlapping density per group (overlay)
    pavlab_density(values, groups=cell_types, kind="density",
                   xlabel="Score", title="Score by cell type")

    # faceted histogram, log x axis
    pavlab_density(counts, groups=conditions, kind="histogram",
                   facet=True, stat="count", log_x="log10", xlabel="Counts")

    # violin plot across multiple conditions
    pavlab_density(values, groups=treatment, kind="violin",
                   ylabel="Expression", order=["ctrl", "low", "high"])

    # reflect KDE at zero for non-negative data
    pavlab_density(probabilities, kind="density", reflect_bounds=True,
                   xlabel="Probability", show_mean=True)

    # save to SVG
    pavlab_density(values, groups=labels, kind="density",
                   filename="fig1a.svg", figsize=(6, 4))
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
        _ACCENT_COLORS,
        _N_ALPHA,
        _BLACK,
    )
except ImportError:
    from pavlab_scatter import (
        _pick_log_kind,
        _apply_log,
        _axis_label,
        _font_sizes,
        _maybe_warn_log,
        _ACCENT_COLORS,
        _N_ALPHA,
        _BLACK,
    )

try:
    from .palettes import black_body_palette
except ImportError:
    from palettes import black_body_palette

_MEAN_COLOR = "#9ca3af"
_N_DENSITY_WARN = 3

LogScale = Union[bool, str]


def _group_colors(color, unique_groups: list[str]) -> list[str]:
    n = len(unique_groups)
    if color is None:
        return [_ACCENT_COLORS[i % len(_ACCENT_COLORS)] for i in range(n)]
    if isinstance(color, str):
        return [color] * n
    color_list = list(color)
    if len(color_list) != n:
        raise ValueError(
            f"color list length ({len(color_list)}) must match number of groups ({n})"
        )
    return color_list


def _detect_bounds(arr: np.ndarray) -> tuple[float | None, float | None]:
    lo = 0.0 if float(arr.min()) >= 0.0 else None
    hi = 1.0 if (lo is not None and float(arr.max()) <= 1.0) else None
    return lo, hi


def _compute_kde(
    arr: np.ndarray,
    bw_method,
    lo: float | None = None,
    hi: float | None = None,
    n_grid: int = 512,
) -> tuple[np.ndarray, np.ndarray]:
    try:
        from scipy.stats import gaussian_kde
    except ImportError as exc:
        raise ImportError(
            "pavlab_density: scipy is required for KDE; install with: pip install scipy"
        ) from exc

    std = float(arr.std()) if arr.std() > 0 else 1.0
    x_lo = float(lo) if lo is not None else float(arr.min()) - 3 * std
    x_hi = float(hi) if hi is not None else float(arr.max()) + 3 * std
    x_grid = np.linspace(x_lo, x_hi, n_grid)

    if lo is not None or hi is not None:
        reflected = list(arr)
        if lo is not None:
            reflected = np.concatenate([reflected, 2 * lo - arr])
        if hi is not None:
            reflected = np.concatenate([reflected, 2 * hi - arr])
        reflected = np.asarray(reflected)
        kde = gaussian_kde(reflected, bw_method=bw_method)
        density = kde(x_grid) * 2.0
        if lo is not None:
            density[x_grid < lo] = 0.0
        if hi is not None:
            density[x_grid > hi] = 0.0
    else:
        kde = gaussian_kde(arr, bw_method=bw_method)
        density = kde(x_grid)

    return x_grid, density


def _apply_theme(ax: plt.Axes, label_pt: float, tick_pt: float) -> None:
    ax.set_facecolor("white")
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=tick_pt, colors="#6b7280")
    ax.xaxis.label.set_color("#1f2937")
    ax.yaxis.label.set_color("#1f2937")


def pavlab_density(
    values,
    groups=None,
    kind: str = "density",
    facet: bool = False,
    stat: str = "density",
    bins: Any = "auto",
    bw_method: Any = "scott",
    reflect_bounds: bool = False,
    color=None,
    log_x: LogScale = False,
    log_y: bool = False,
    pseudocount: float = 1.0,
    origin_zero: bool = True,
    label_size: str | float = "med",
    xlabel: str | None = None,
    ylabel: str | None = None,
    title: str | None = None,
    xlim: tuple | None = None,
    ylim: tuple | None = None,
    show_mean: bool = False,
    show_median: bool = False,
    order: list[str] | None = None,
    figsize: tuple | None = None,
    filename=None,
    ax: plt.Axes | None = None,
) -> Any:
    """Pavlab-style density / histogram / violin plot.

    Parameters
    ----------
    values : array-like
        1-D numeric data.
    groups : array-like of str, optional
        Same-length categorical group labels. Required for kind="violin".
    kind : "density" | "histogram" | "violin"
        Plot type.
    facet : bool
        If True, draw one panel per group (density/histogram only).
        Returns a Figure instead of Axes.
    stat : "density" | "count"
        Y-axis metric.
    bins : int or str
        Bin specification for histogram ("auto", "fd", "sturges", "scott",
        or an integer).
    bw_method : scalar or str
        Bandwidth method forwarded to scipy.stats.gaussian_kde.
    reflect_bounds : bool
        When True, auto-detect bounds at 0 (non-negative data) and/or 1
        (probability data), and apply reflection correction so KDE does not
        bleed past those bounds.
    color : None | str | list
        None → accent palette per group. Single str → all groups same color.
        List/array of per-group color strings → explicit mapping.
    log_x : False | True | "log2" | "log10"
        Transform values before KDE/histogram.
    log_y : bool
        Apply log scale to the y axis (freq/density).
    pseudocount : float
        Added before log_x transform. Default 1.
    origin_zero : bool
        Pin y lower bound to 0 for non-negative data.
    label_size : "small" | "med" | "large" | float
        Axis-label font size preset.
    xlabel, ylabel, title : str, optional
        Axis labels and figure title.
    xlim, ylim : (lo, hi) | None
        Explicit axis limits.
    show_mean : bool
        Draw grand mean of all values as a full-width dashed grey line.
    show_median : bool
        Draw grand median as a full-width dotted grey line.
    order : list of str, optional
        Explicit group order.
    figsize : (w, h) | None
        Figure size in inches.
    filename : str | Path | None
        Save to file; format inferred from extension.
    ax : matplotlib Axes | None
        Draw into an existing Axes. Ignored when facet=True or kind="violin".

    Returns
    -------
    matplotlib.axes.Axes (facet=False) or matplotlib.figure.Figure (facet=True)
    """
    vals_arr = np.asarray(values, dtype=float).ravel()

    grp_arr: np.ndarray | None = None
    if groups is not None:
        grp_arr = np.asarray(groups, dtype=object).ravel()
        if len(grp_arr) != len(vals_arr):
            raise ValueError(
                f"values and groups must have equal length "
                f"({len(vals_arr)} vs {len(grp_arr)})"
            )

    if kind == "violin" and grp_arr is None:
        raise ValueError("kind='violin' requires groups to be provided")

    if not isinstance(log_y, bool):
        warnings.warn(
            "pavlab_density: log_y must be a bool (True/False); "
            f"got {log_y!r}. Treating as bool.",
            stacklevel=2,
        )
        log_y = bool(log_y)

    finite_mask = np.isfinite(vals_arr)
    if not finite_mask.all():
        vals_arr = vals_arr[finite_mask]
        if grp_arr is not None:
            grp_arr = grp_arr[finite_mask]

    if len(vals_arr) == 0:
        warnings.warn("pavlab_density: no finite data points to plot.", stacklevel=2)

    if log_x is False:
        _maybe_warn_log(vals_arr, "x")

    x_kind = _pick_log_kind(log_x, vals_arr, "x")
    if x_kind:
        neg = int(np.sum(np.isfinite(vals_arr) & (vals_arr + pseudocount <= 0)))
        if neg:
            warnings.warn(
                f"pavlab_density: {neg} value(s) will produce -inf after "
                f"log transform (pseudocount={pseudocount} insufficient).",
                stacklevel=2,
            )
        vals_arr = _apply_log(vals_arr, x_kind, pseudocount)

    seen: list[str] = list(dict.fromkeys(grp_arr.tolist())) if grp_arr is not None else []

    if order is not None and grp_arr is not None:
        unique_groups: list[str] = []
        for g in order:
            if g not in seen:
                warnings.warn(
                    f"pavlab_density: group {g!r} in order has no data; skipping.",
                    stacklevel=2,
                )
            else:
                unique_groups.append(g)
        group_set = set(unique_groups)
        keep = np.array([g in group_set for g in grp_arr.tolist()], dtype=bool)
        vals_arr = vals_arr[keep]
        grp_arr = grp_arr[keep]
    else:
        unique_groups = seen

    label_pt, tick_pt = _font_sizes(label_size)

    if kind in ("density", "histogram"):
        return _plot_dist(
            vals_arr=vals_arr,
            grp_arr=grp_arr,
            unique_groups=unique_groups,
            kind=kind,
            facet=facet,
            stat=stat,
            bins=bins,
            bw_method=bw_method,
            reflect_bounds=reflect_bounds,
            color=color,
            log_y=log_y,
            origin_zero=origin_zero,
            label_pt=label_pt,
            tick_pt=tick_pt,
            x_kind=x_kind,
            xlabel=xlabel,
            ylabel=ylabel,
            title=title,
            xlim=xlim,
            ylim=ylim,
            show_mean=show_mean,
            show_median=show_median,
            figsize=figsize,
            filename=filename,
            ax=ax,
        )

    return _plot_violin(
        vals_arr=vals_arr,
        grp_arr=grp_arr,
        unique_groups=unique_groups,
        bw_method=bw_method,
        color=color,
        log_y=log_y,
        origin_zero=origin_zero,
        label_pt=label_pt,
        tick_pt=tick_pt,
        x_kind=x_kind,
        xlabel=xlabel,
        ylabel=ylabel,
        title=title,
        xlim=xlim,
        ylim=ylim,
        show_mean=show_mean,
        show_median=show_median,
        figsize=figsize,
        filename=filename,
        ax=ax,
    )


def _plot_dist(
    vals_arr, grp_arr, unique_groups, kind, facet, stat, bins, bw_method,
    reflect_bounds, color, log_y, origin_zero, label_pt, tick_pt, x_kind,
    xlabel, ylabel, title, xlim, ylim, show_mean, show_median,
    figsize, filename, ax,
) -> Any:
    has_groups = grp_arr is not None and len(unique_groups) > 0
    n_groups = len(unique_groups) if has_groups else 1

    if has_groups and n_groups > _N_DENSITY_WARN and not facet:
        warnings.warn(
            f"pavlab_density: {n_groups} groups in overlay mode; "
            "consider facet=True for clarity.",
            stacklevel=3,
        )

    group_vals: list[np.ndarray] = []
    if has_groups:
        for g in unique_groups:
            group_vals.append(vals_arr[grp_arr == g])
    else:
        group_vals = [vals_arr]

    colors = _group_colors(color, unique_groups if has_groups else ["_all"])

    if kind == "histogram":
        shared_edges = np.histogram_bin_edges(vals_arr, bins=bins)

    grand_mean = float(np.mean(vals_arr)) if show_mean else None
    grand_median = float(np.median(vals_arr)) if show_median else None

    x_all_min = float(vals_arr.min()) if len(vals_arr) > 0 else 0.0
    x_all_max = float(vals_arr.max()) if len(vals_arr) > 0 else 1.0

    y_label_default = "Density" if stat == "density" else "Count"
    y_label = ylabel if ylabel is not None else y_label_default
    x_label = _axis_label(xlabel, x_kind)

    if kind == "density" and not reflect_bounds and len(vals_arr) > 0:
        lo, hi = _detect_bounds(vals_arr)
        if lo is not None or hi is not None:
            bound_str = (
                f"lower bound at {lo}" if hi is None
                else f"upper bound at {hi}" if lo is None
                else f"bounds at {lo} and {hi}"
            )
            warnings.warn(
                f"pavlab_density: data appears to have {bound_str} but "
                "reflect_bounds=False; KDE may bleed outside the support. "
                "Consider reflect_bounds=True.",
                stacklevel=3,
            )

    lo_reflect = hi_reflect = None
    if kind == "density" and reflect_bounds and len(vals_arr) > 0:
        lo_reflect, hi_reflect = _detect_bounds(vals_arr)

    if facet:
        fw, fh = figsize if figsize is not None else (4.0 * n_groups, 4.0)
        fig, axes = plt.subplots(1, n_groups, sharey=True, figsize=(fw, fh))
        if n_groups == 1:
            axes = [axes]

        for i, (gvals, clr, panel_ax) in enumerate(zip(group_vals, colors, axes)):
            _apply_theme(panel_ax, label_pt, tick_pt)
            _draw_dist_panel(
                panel_ax, gvals, clr, kind, stat, shared_edges if kind == "histogram" else None,
                bw_method, lo_reflect, hi_reflect, x_all_min, x_all_max,
                alpha=0.7,
            )
            if show_mean and grand_mean is not None:
                panel_ax.axvline(grand_mean, color=_MEAN_COLOR, linewidth=1,
                                 linestyle="dashed", zorder=1)
            if show_median and grand_median is not None:
                panel_ax.axvline(grand_median, color=_MEAN_COLOR, linewidth=1,
                                 linestyle="dotted", zorder=1)
            grp_label = unique_groups[i] if has_groups else ""
            panel_ax.set_title(grp_label, fontsize=label_pt, loc="left",
                               fontweight="normal")
            if i == 0 and y_label:
                panel_ax.set_ylabel(y_label, fontsize=label_pt)
            if log_y:
                panel_ax.set_yscale("log")
            if xlim is not None:
                panel_ax.set_xlim(xlim)
            if ylim is not None:
                panel_ax.set_ylim(ylim)
            elif origin_zero and stat == "density":
                panel_ax.set_ylim(bottom=0)

        if x_label:
            fig.supxlabel(x_label, fontsize=label_pt, color="#1f2937")
        if title:
            fig.suptitle(title, fontsize=label_pt, x=0.0, ha="left",
                         fontweight="normal")
        fig.tight_layout()
        if filename is not None:
            fig.savefig(filename, dpi=200)
            plt.close(fig)
        return fig

    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=figsize or (5.5, 4.5))
    else:
        fig = ax.figure

    _apply_theme(ax, label_pt, tick_pt)

    import matplotlib.patches as mpatches
    legend_handles = []

    for i, (gvals, clr) in enumerate(zip(group_vals, colors)):
        alpha = 0.5 if has_groups else 0.7
        lbl = unique_groups[i] if has_groups else None
        _draw_dist_panel(
            ax, gvals, clr, kind, stat,
            shared_edges if kind == "histogram" else None,
            bw_method, lo_reflect, hi_reflect, x_all_min, x_all_max,
            alpha=alpha, label=lbl,
        )
        if has_groups:
            legend_handles.append(mpatches.Patch(color=clr, label=lbl))

    if has_groups:
        ax.legend(handles=legend_handles, frameon=False, fontsize=tick_pt)

    if show_mean and grand_mean is not None:
        ax.axvline(grand_mean, color=_MEAN_COLOR, linewidth=1,
                   linestyle="dashed", zorder=1)
    if show_median and grand_median is not None:
        ax.axvline(grand_median, color=_MEAN_COLOR, linewidth=1,
                   linestyle="dotted", zorder=1)

    if x_label:
        ax.set_xlabel(x_label, fontsize=label_pt)
    if y_label:
        ax.set_ylabel(y_label, fontsize=label_pt)
    if title:
        ax.set_title(title, fontsize=label_pt, loc="left", fontweight="normal")
    if log_y:
        ax.set_yscale("log")
    if xlim is not None:
        ax.set_xlim(xlim)
    if ylim is not None:
        ax.set_ylim(ylim)
    elif origin_zero and stat == "density":
        ax.set_ylim(bottom=0)

    if own_fig:
        fig.tight_layout()
        if filename is not None:
            fig.savefig(filename, dpi=200)
            plt.close(fig)

    return ax


def _draw_dist_panel(
    ax, gvals, clr, kind, stat, shared_edges, bw_method,
    lo_reflect, hi_reflect, x_all_min, x_all_max, alpha=0.5, label=None,
) -> None:
    if len(gvals) == 0:
        return

    if kind == "density":
        x_grid, density = _compute_kde(gvals, bw_method, lo_reflect, hi_reflect)
        if stat == "count":
            density = density * len(gvals)
        ax.fill_between(x_grid, density, alpha=alpha, color=clr, label=label)
        ax.plot(x_grid, density, color=clr, linewidth=1.5, alpha=1.0)

    elif kind == "histogram":
        edges = shared_edges if shared_edges is not None else \
            np.histogram_bin_edges(gvals, bins="auto")
        ax.hist(
            gvals,
            bins=edges,
            density=(stat == "density"),
            color=clr,
            alpha=alpha,
            edgecolor="none",
            label=label,
        )


_VIOLIN_GREY = "#4b5563"


def _plot_violin(
    vals_arr, grp_arr, unique_groups, bw_method, color, log_y, origin_zero,
    label_pt, tick_pt, x_kind, xlabel, ylabel, title, xlim, ylim,
    show_mean, show_median, figsize, filename, ax,
) -> plt.Axes:
    n_groups = len(unique_groups)
    colors = ([_VIOLIN_GREY] * n_groups) if color is None else _group_colors(color, unique_groups)

    dataset = [vals_arr[grp_arr == g] for g in unique_groups]
    positions = list(range(n_groups))

    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=figsize or (max(4.0, 1.5 * n_groups), 5.0))
    else:
        fig = ax.figure

    _apply_theme(ax, label_pt, tick_pt)

    parts = ax.violinplot(
        dataset,
        positions=positions,
        widths=0.8,
        showmeans=False,
        showextrema=False,
        showmedians=False,
        bw_method=bw_method,
    )

    for body, clr in zip(parts["bodies"], colors):
        body.set_facecolor(clr)
        body.set_alpha(0.7)
        body.set_edgecolor("none")

    ax.set_xticks(range(n_groups))
    ax.set_xticklabels(unique_groups, fontsize=tick_pt)
    ax.set_xlim(-0.5, n_groups - 0.5)

    grand_mean = float(np.mean(vals_arr)) if show_mean else None
    grand_median = float(np.median(vals_arr)) if show_median else None

    if show_mean and grand_mean is not None:
        ax.axhline(grand_mean, color=_MEAN_COLOR, linewidth=1,
                   linestyle="dashed", zorder=1)
    if show_median and grand_median is not None:
        ax.axhline(grand_median, color=_MEAN_COLOR, linewidth=1,
                   linestyle="dotted", zorder=1)

    y_label = _axis_label(ylabel, x_kind)
    x_label = xlabel or ""
    if x_label:
        ax.set_xlabel(x_label, fontsize=label_pt)
    if y_label:
        ax.set_ylabel(y_label, fontsize=label_pt)
    if title:
        ax.set_title(title, fontsize=label_pt, loc="left", fontweight="normal")

    if log_y:
        ax.set_yscale("log")

    if xlim is not None:
        ax.set_xlim(xlim)
    if ylim is not None:
        ax.set_ylim(ylim)
    else:
        fy = vals_arr[np.isfinite(vals_arr)]
        if origin_zero and fy.size > 0 and float(fy.min()) >= 0:
            ax.set_ylim(bottom=0)

    if own_fig:
        fig.tight_layout()
        if filename is not None:
            fig.savefig(filename, dpi=200)
            plt.close(fig)

    return ax
