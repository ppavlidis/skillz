"""pavlab_heatmap (Python) — opinionated seaborn.heatmap wrapper.

Mirror of R/pavlab_heatmap.R. Same lab defaults, same five named divergent
palettes, same auto-behavior for correlation/expression/raw modes. Outputs
are publication-grade matplotlib figures.

Usage:
    from pavlab_heatmap import pavlab_heatmap

    pavlab_heatmap(expr_df)                                  # expression mode (default)
    pavlab_heatmap(expr_df, filename="fig2a.pdf")            # save to file
    pavlab_heatmap(cor_df, mode="correlation")               # correlation mode
    pavlab_heatmap(raw_df, mode="raw")                       # raw mode
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

try:
    from .palettes import black_body_palette, divergent_palette  # package-style
except ImportError:
    from palettes import black_body_palette, divergent_palette  # script-style (sys.path)

Mode = Literal["expression", "correlation", "raw"]


def pavlab_heatmap(
    mat,
    mode: Mode = "expression",
    cluster_rows: bool = False,
    cluster_cols: bool = False,
    show_rownames: bool | None = None,
    show_colnames: bool | None = None,
    standardize_rows: bool | None = None,
    zclip: float | None = 3.0,
    divergent: bool | None = None,
    na_color: str = "#cccccc",
    palette_n: int = 256,
    rowname_threshold: int = 50,
    colname_threshold: int = 30,
    angle_col: int = 45,
    border_color: str | None = None,           # None = no gridlines
    correlation_negative_tolerance: float = -0.1,
    filename: str | Path | None = None,
    figsize: tuple[float, float] | None = None,
    cmap=None,
    ax=None,
    **kwargs: Any,
):
    """Pavlab-style heatmap (Python port of R pavlab_heatmap).

    Wraps seaborn.heatmap with lab defaults. Any unrecognized kwarg is
    forwarded to seaborn.heatmap. See ../SKILL.md for the rationale behind
    each default.

    Parameters
    ----------
    mat : 2D array, pandas DataFrame, or anything convertible.
        The matrix to plot. If a DataFrame, index/columns become labels.
    mode : {"expression", "correlation", "raw"}
        Sets transformation and palette defaults.
    cluster_rows, cluster_cols : bool
        Default False. (seaborn doesn't cluster in `heatmap`; use
        `sns.clustermap` if you want clustering — this wrapper doesn't
        switch backends for you, but will warn if you ask for clustering.)
    standardize_rows : bool, optional
        None = True iff mode == "expression". Computes row Z-scores.
    zclip : float, optional
        Clip standardized values to [-zclip, +zclip]. Default 3.
    divergent : bool, optional
        Force divergent vs sequential palette. None = auto from mode +
        data. In correlation mode, if all values are >= correlation_negative_tolerance,
        small negatives are clipped to 0 and the sequential black-body
        palette is used.
    na_color : str
        Color for NaN cells. Default "#cccccc" (matches R grey80).
    border_color : str or None
        Cell-edge color (forwarded to seaborn as `linecolor`). Default
        None = no gridlines (sets linewidths=0).
    correlation_negative_tolerance : float
        See SKILL.md. Default -0.1.
    filename : str | Path | None
        If provided, the figure is saved via fig.savefig and not shown.
    figsize : (w, h) tuple, optional
        Override the default figure size.
    cmap : matplotlib Colormap, optional
        Override the auto-chosen palette.
    ax : matplotlib Axes, optional
        Draw into an existing Axes (figsize and filename are ignored).
    **kwargs
        Forwarded to seaborn.heatmap.

    Returns
    -------
    matplotlib Axes object containing the heatmap.
    """
    # --- normalize input ---
    if isinstance(mat, pd.DataFrame):
        mat = mat.copy()
        is_df = True
    else:
        mat = np.asarray(mat, dtype=float)
        mat = pd.DataFrame(mat)
        is_df = False  # noqa: F841

    if cluster_rows or cluster_cols:
        # Pheatmap/seaborn split: clustering needs clustermap, not heatmap.
        # We don't transparently switch; surface this to the caller.
        raise NotImplementedError(
            "pavlab_heatmap (Python) does not currently dispatch to "
            "sns.clustermap. Call sns.clustermap directly if you need "
            "clustering; the same palette helpers work via cmap=."
        )

    # --- resolve auto-defaults ---
    if standardize_rows is None:
        standardize_rows = (mode == "expression")
    if show_rownames is None:
        show_rownames = mat.shape[0] <= rowname_threshold
    if show_colnames is None:
        show_colnames = mat.shape[1] <= colname_threshold

    # --- mode-specific transforms ---
    if mode == "correlation":
        if mat.shape[0] == mat.shape[1]:
            arr = mat.to_numpy(copy=True)
            np.fill_diagonal(arr, np.nan)
            mat = pd.DataFrame(arr, index=mat.index, columns=mat.columns)
        else:
            import warnings
            warnings.warn(
                "pavlab_heatmap: mode='correlation' but matrix isn't square; "
                "leaving diagonal alone"
            )

    if standardize_rows:
        # Row Z-score: (x - row mean) / row std.
        row_mean = mat.mean(axis=1)
        row_std = mat.std(axis=1, ddof=1).replace(0, np.nan)
        mat = mat.sub(row_mean, axis=0).div(row_std, axis=0)
        if zclip is not None and np.isfinite(zclip) and zclip > 0:
            mat = mat.clip(lower=-zclip, upper=zclip)

    # --- palette decision (mirrors R logic) ---
    if cmap is None:
        if divergent is None:
            if mode == "expression":
                divergent = True
            elif mode == "correlation":
                min_val = np.nanmin(mat.to_numpy())
                if not np.isfinite(min_val):
                    divergent = False
                elif min_val >= correlation_negative_tolerance:
                    if min_val < 0:
                        # Clip small negatives to 0 (the cutpoint).
                        mat = mat.clip(lower=0)
                    divergent = False
                else:
                    divergent = True
            else:  # raw
                vals = mat.to_numpy()
                vals = vals[np.isfinite(vals)]
                divergent = vals.size > 0 and (vals < 0).any() and (vals > 0).any()

        if divergent:
            cmap = divergent_palette(palette_n)
        else:
            cmap = black_body_palette(palette_n)
        cmap.set_bad(na_color)

    # --- breaks: symmetric for divergent ---
    vmin = vmax = None
    if divergent:
        max_abs = np.nanmax(np.abs(mat.to_numpy()))
        if not np.isfinite(max_abs) or max_abs == 0:
            max_abs = 1.0
        vmin, vmax = -max_abs, max_abs

    # --- figure setup ---
    own_fig = False
    if ax is None:
        if figsize is None:
            # mild auto-sizing
            figsize = (max(5, mat.shape[1] * 0.25 + 2),
                       max(4, mat.shape[0] * 0.22 + 1))
        fig, ax = plt.subplots(figsize=figsize)
        own_fig = True
    else:
        fig = ax.figure

    # --- forward to seaborn ---
    linewidths = 0 if border_color is None else 0.5
    linecolor = border_color if border_color is not None else "white"

    sns_kwargs = dict(
        cmap=cmap,
        vmin=vmin, vmax=vmax,
        xticklabels=show_colnames,
        yticklabels=show_rownames,
        linewidths=linewidths,
        linecolor=linecolor,
        cbar=True,
        square=False,
        ax=ax,
    )
    sns_kwargs.update(kwargs)
    sns.heatmap(mat, **sns_kwargs)

    # Rotate column labels (the R angle_col equivalent).
    if show_colnames:
        plt.setp(ax.get_xticklabels(), rotation=angle_col,
                 ha="right", rotation_mode="anchor")

    if own_fig:
        fig.tight_layout()
        if filename is not None:
            fig.savefig(filename, dpi=200)
            plt.close(fig)

    return ax
