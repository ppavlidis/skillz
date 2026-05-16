"""Tests for the Python pavlab_heatmap. Run from skills/plotting/:
    .venv/bin/pytest tests/test_heatmap.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402

from pavlab_heatmap import pavlab_heatmap  # noqa: E402
from palettes import (  # noqa: E402
    black_body_palette,
    divergent_palette,
    divergent_palette_rdbu,
    divergent_palette_spectral,
    divergent_palette_cyan_yellow,
    divergent_palette_blue_yellow,
)


# ---- palette tests -------------------------------------------------------

def test_palette_lengths():
    """Colormaps respect the requested N (matplotlib stores .N)."""
    assert black_body_palette(64).N == 64
    assert black_body_palette(256).N == 256
    for fn in (divergent_palette, divergent_palette_rdbu,
               divergent_palette_spectral, divergent_palette_cyan_yellow,
               divergent_palette_blue_yellow):
        assert fn(128).N == 128


def test_divergent_palettes_have_black_midpoint():
    """Each divergent palette must hit pure black at the exact midpoint."""
    for fn in (divergent_palette, divergent_palette_rdbu,
               divergent_palette_spectral, divergent_palette_cyan_yellow,
               divergent_palette_blue_yellow):
        cmap = fn(257)
        mid_rgba = cmap(0.5)
        # 0.5 should map to pure black (alpha=1 is fine).
        assert mid_rgba[0] < 0.02 and mid_rgba[1] < 0.02 and mid_rgba[2] < 0.02, \
            f"{fn.__name__} midpoint not black: {mid_rgba}"


def test_palette_bad_color_set():
    """NaN cells must render in the configured 'bad' color, not the default."""
    cmap = divergent_palette()
    bad = cmap.get_bad()
    # Should not be the matplotlib default (transparent).
    assert bad[3] == 1.0, f"bad alpha should be 1.0, got {bad[3]}"


# ---- pavlab_heatmap end-to-end ------------------------------------------

@pytest.fixture
def expr_df():
    rng = np.random.default_rng(1)
    return pd.DataFrame(
        rng.standard_normal((10, 6)),
        index=[f"g{i}" for i in range(10)],
        columns=[f"s{i}" for i in range(6)],
    )


def test_expression_mode_writes_file(tmp_path, expr_df):
    out = tmp_path / "expr.png"
    ax = pavlab_heatmap(expr_df, mode="expression", filename=str(out), figsize=(4, 4))
    assert out.exists() and out.stat().st_size > 1000
    plt.close("all")


def test_correlation_mode_writes_file(tmp_path, expr_df):
    cor = expr_df.T.corr()
    out = tmp_path / "cor.png"
    pavlab_heatmap(cor, mode="correlation", filename=str(out), figsize=(4, 4))
    assert out.exists() and out.stat().st_size > 1000
    plt.close("all")


def test_raw_mode_writes_file(tmp_path, expr_df):
    out = tmp_path / "raw.png"
    pavlab_heatmap(expr_df, mode="raw", filename=str(out), figsize=(4, 4))
    assert out.exists() and out.stat().st_size > 1000
    plt.close("all")


def test_zclip_bounds_matrix(expr_df):
    """After expression mode with zclip=2, no rendered value should fall
    outside [-2, +2]."""
    out_df = expr_df.copy()
    out_df.iloc[0, 0] = 100  # outlier
    ax = pavlab_heatmap(out_df, mode="expression", zclip=2.0, figsize=(3, 3))
    arr = ax.collections[0].get_array()
    finite = arr[~np.isnan(arr)] if hasattr(arr, "compressed") else arr[np.isfinite(arr)]
    assert float(finite.max()) <= 2.0 + 1e-6
    assert float(finite.min()) >= -2.0 - 1e-6
    plt.close("all")


def test_nan_cells_handled(tmp_path, expr_df):
    sparse = expr_df.copy()
    sparse.iloc[0, 0] = np.nan
    sparse.iloc[3, 2] = np.nan
    out = tmp_path / "nan.png"
    pavlab_heatmap(sparse, filename=str(out), figsize=(4, 4))
    assert out.exists() and out.stat().st_size > 1000
    plt.close("all")


def test_big_matrix_autohides_labels():
    rng = np.random.default_rng(2)
    big = pd.DataFrame(
        rng.standard_normal((80, 40)),
        index=[f"g{i}" for i in range(80)],
        columns=[f"s{i}" for i in range(40)],
    )
    ax = pavlab_heatmap(big, figsize=(5, 5))
    # rowname_threshold=50, colname_threshold=30 by default; 80>50 and 40>30
    # so both should be hidden.
    assert len(ax.get_yticklabels()) == 0
    assert len(ax.get_xticklabels()) == 0
    plt.close("all")


def test_correlation_all_positive_uses_sequential(expr_df):
    """When all correlations are >= 0, the palette should be sequential
    (black-body), not divergent."""
    # Build a correlation matrix that's guaranteed all positive: |cor(x)|.
    cor = expr_df.T.corr().abs()
    ax = pavlab_heatmap(cor, mode="correlation", figsize=(3, 3))
    cmap = ax.collections[0].get_cmap()
    # black_body_palette cmap name was registered as "pavlab_blackbody".
    assert cmap.name == "pavlab_blackbody", \
        f"expected sequential black-body, got {cmap.name}"
    plt.close("all")


def test_no_gridlines_by_default(expr_df):
    """border_color=None should set linewidths=0 — verify by inspecting
    the QuadMesh."""
    ax = pavlab_heatmap(expr_df, figsize=(3, 3))
    qm = ax.collections[0]
    lw = qm.get_linewidth()
    arr_lw = lw if not hasattr(lw, "__iter__") else lw[0]
    assert float(arr_lw) == 0.0
    plt.close("all")


def test_clustering_not_supported(expr_df):
    with pytest.raises(NotImplementedError):
        pavlab_heatmap(expr_df, cluster_rows=True)
