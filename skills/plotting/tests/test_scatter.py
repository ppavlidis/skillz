"""Tests for pavlab_scatter. Run from skills/plotting/:
    .venv/bin/pytest tests/test_scatter.py -v
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PathCollection  # noqa: E402

from pavlab_scatter import (  # noqa: E402
    _N_ALPHA,
    _N_DENSITY,
    _LABEL_SIZES,
    _axis_label,
    _font_sizes,
    _pick_log_kind,
    pavlab_scatter,
)


# ---- unit: helpers -------------------------------------------------------

def test_axis_label_base_only():
    assert _axis_label("FPKM", None) == "FPKM"


def test_axis_label_log2_suffix():
    assert _axis_label("FPKM", "log2") == "FPKM (log₂)"


def test_axis_label_log10_suffix():
    assert _axis_label(None, "log10") == "(log₁₀)"


def test_axis_label_no_base_no_log():
    assert _axis_label(None, None) == ""


def test_font_sizes_presets():
    small = _font_sizes("small")
    large = _font_sizes("large")
    assert large[0] > small[0]
    assert large[1] > small[1]


def test_font_sizes_numeric():
    label_pt, tick_pt = _font_sizes(20.0)
    assert label_pt == 20.0
    assert tick_pt < 20.0


def test_font_sizes_bad_string():
    with pytest.raises(ValueError, match="label_size"):
        _font_sizes("huge")


def test_pick_log_kind_false():
    assert _pick_log_kind(False, np.array([1.0, 2.0]), "x") is None


def test_pick_log_kind_log2_explicit():
    assert _pick_log_kind("log2", np.array([1.0, 2.0]), "x") == "log2"


def test_pick_log_kind_log10_explicit():
    assert _pick_log_kind("log10", np.array([1.0, 2.0]), "x") == "log10"


def test_pick_log_kind_true_large_counts():
    arr = np.array([1.0, 5_000.0])
    assert _pick_log_kind(True, arr, "x") == "log10"


def test_pick_log_kind_true_biological_range():
    arr = np.array([1.0, 500.0])
    assert _pick_log_kind(True, arr, "x") == "log2"


def test_pick_log_kind_bad_value():
    with pytest.raises(ValueError):
        _pick_log_kind("ln", np.array([1.0]), "x")


# ---- integration: pavlab_scatter ----------------------------------------

@pytest.fixture
def small_xy():
    rng = np.random.default_rng(0)
    return rng.standard_normal(30) + 5, rng.standard_normal(30) + 5


def test_returns_axes(small_xy):
    ax = pavlab_scatter(*small_xy)
    assert hasattr(ax, "collections")
    plt.close("all")


def test_writes_file(tmp_path, small_xy):
    out = tmp_path / "scatter.png"
    pavlab_scatter(*small_xy, filename=str(out), figsize=(4, 4))
    assert out.exists() and out.stat().st_size > 500
    plt.close("all")


def test_nan_pairs_dropped():
    x = np.array([1.0, np.nan, 3.0, 4.0])
    y = np.array([1.0, 2.0,   np.nan, 4.0])
    ax = pavlab_scatter(x, y)
    offsets = ax.collections[0].get_offsets()
    assert len(offsets) == 2   # only (1,1) and (4,4) survive
    plt.close("all")


def test_length_mismatch_raises():
    with pytest.raises(ValueError, match="equal length"):
        pavlab_scatter([1, 2], [1, 2, 3])


def test_log2_transform_applied():
    x = np.array([1.0, 3.0, 7.0])
    y = np.array([0.0, 0.0, 0.0])
    ax = pavlab_scatter(x, y, log_x="log2", pseudocount=1.0, origin_zero=False)
    offsets = ax.collections[0].get_offsets()
    expected = np.log2(x + 1.0)
    np.testing.assert_allclose(offsets[:, 0], expected, rtol=1e-5)
    plt.close("all")


def test_log10_transform_applied():
    x = np.array([9.0, 99.0, 999.0])
    y = np.zeros(3)
    ax = pavlab_scatter(x, y, log_x="log10", pseudocount=1.0, origin_zero=False)
    offsets = ax.collections[0].get_offsets()
    expected = np.log10(x + 1.0)
    np.testing.assert_allclose(offsets[:, 0], expected, rtol=1e-5)
    plt.close("all")


def test_log_label_suffix_appended():
    x = np.array([1.0, 2.0])
    ax = pavlab_scatter(x, x, xlabel="Gene", ylabel="Expr",
                        log_x="log2", log_y="log10")
    assert "(log₂)" in ax.get_xlabel()
    assert "(log₁₀)" in ax.get_ylabel()
    plt.close("all")


def test_origin_zero_nonneg_data(small_xy):
    ax = pavlab_scatter(*small_xy)   # small_xy is all > 0
    assert ax.get_xlim()[0] == pytest.approx(0.0)
    assert ax.get_ylim()[0] == pytest.approx(0.0)
    plt.close("all")


def test_origin_zero_negative_data_not_pinned():
    x = np.array([-2.0, -1.0, 1.0, 2.0])
    y = np.array([-2.0, -1.0, 1.0, 2.0])
    ax = pavlab_scatter(x, y)
    assert ax.get_xlim()[0] < 0
    assert ax.get_ylim()[0] < 0
    plt.close("all")


def test_origin_zero_false_skips_pinning(small_xy):
    ax = pavlab_scatter(*small_xy, origin_zero=False)
    assert ax.get_xlim()[0] > 0
    plt.close("all")


def test_xlim_overrides_origin_zero(small_xy):
    ax = pavlab_scatter(*small_xy, xlim=(2.0, 8.0))
    lo, hi = ax.get_xlim()
    assert lo == pytest.approx(2.0)
    assert hi == pytest.approx(8.0)
    plt.close("all")


def test_categorical_color_legend():
    rng = np.random.default_rng(1)
    x, y = rng.standard_normal(30), rng.standard_normal(30)
    labels = ["A"] * 10 + ["B"] * 10 + ["C"] * 10
    ax = pavlab_scatter(x, y, color=labels)
    leg = ax.get_legend()
    assert leg is not None
    handles = getattr(leg, "legend_handles", None) or getattr(leg, "legendHandles", [])
    assert len(handles) == 3
    plt.close("all")


def test_numeric_color_colorbar():
    rng = np.random.default_rng(2)
    x, y = rng.standard_normal(20), rng.standard_normal(20)
    scores = rng.uniform(0, 1, 20)
    ax = pavlab_scatter(x, y, color=scores, color_label="p-value")
    fig = ax.figure
    assert len(fig.axes) == 2   # main axes + colorbar axes
    plt.close("all")


def test_small_n_full_opacity(small_xy):
    ax = pavlab_scatter(*small_xy)   # n=30, well below _N_ALPHA
    coll = ax.collections[0]
    alpha = coll.get_alpha()
    assert alpha is None or float(alpha) == pytest.approx(1.0)
    plt.close("all")


def test_medium_n_reduced_alpha():
    rng = np.random.default_rng(3)
    n = _N_ALPHA + 200   # just above threshold
    x, y = rng.standard_normal(n), rng.standard_normal(n)
    ax = pavlab_scatter(x, y)
    alpha = ax.collections[0].get_alpha()
    assert alpha is not None and float(alpha) < 1.0
    plt.close("all")


def test_large_n_uses_density():
    rng = np.random.default_rng(4)
    n = _N_DENSITY + 1_000
    x, y = rng.standard_normal(n), rng.standard_normal(n)
    ax = pavlab_scatter(x, y)
    # hexbin produces PolyCollection; scatter produces PathCollection.
    assert not isinstance(ax.collections[0], PathCollection)
    plt.close("all")


def test_large_n_color_ignored_warning():
    rng = np.random.default_rng(5)
    n = _N_DENSITY + 500
    x, y = rng.standard_normal(n), rng.standard_normal(n)
    with pytest.warns(UserWarning, match="hexbin"):
        pavlab_scatter(x, y, color=["A"] * n)
    plt.close("all")


def test_no_gridlines_no_top_right_spine(small_xy):
    ax = pavlab_scatter(*small_xy)
    assert not ax.spines["top"].get_visible()
    assert not ax.spines["right"].get_visible()
    # No gridlines: grid lines list is empty or all invisible.
    grid_lines = ax.get_xgridlines() + ax.get_ygridlines()
    assert all(not ln.get_visible() for ln in grid_lines)
    plt.close("all")


def test_label_size_large_bigger_than_small(small_xy):
    ax_s = pavlab_scatter(*small_xy, xlabel="X", label_size="small")
    ax_l = pavlab_scatter(*small_xy, xlabel="X", label_size="large")
    assert ax_l.get_xaxis().get_label().get_size() > \
           ax_s.get_xaxis().get_label().get_size()
    plt.close("all")


def test_log_range_warning():
    x = np.array([1.0, 10_000.0])   # 10 000× span
    y = np.array([1.0, 1.0])
    with pytest.warns(UserWarning, match="log_x"):
        pavlab_scatter(x, y)
    plt.close("all")


def test_ax_kwarg_reuses_figure(small_xy):
    fig, axes = plt.subplots(1, 2)
    pavlab_scatter(*small_xy, ax=axes[0])
    pavlab_scatter(*small_xy, ax=axes[1])
    assert len(fig.axes) == 2
    plt.close("all")


def test_point_size_override(small_xy):
    ax = pavlab_scatter(*small_xy, point_size=50.0)
    sizes = ax.collections[0].get_sizes()
    assert float(sizes[0]) == pytest.approx(50.0)
    plt.close("all")
