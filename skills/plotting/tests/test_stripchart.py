"""Tests for pavlab_stripchart (Python/matplotlib).
Run from skills/plotting/:
    .venv/bin/pytest tests/test_stripchart.py -v
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
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PathCollection

from pavlab_stripchart import pavlab_stripchart


# ---- fixtures ---------------------------------------------------------------

@pytest.fixture
def simple():
    """20 points across two groups; all y positive."""
    rng = np.random.default_rng(0)
    groups = ["A"] * 10 + ["B"] * 10
    values = rng.uniform(1, 5, 20)
    return groups, values


@pytest.fixture
def three_groups():
    rng = np.random.default_rng(1)
    groups = ["ctrl"] * 15 + ["treat"] * 15 + ["dko"] * 15
    values = rng.uniform(0, 10, 45)
    return groups, values


# ---- 1. Basic rendering -----------------------------------------------------

def test_returns_axes(simple):
    ax = pavlab_stripchart(*simple)
    assert hasattr(ax, "collections")
    plt.close("all")


def test_writes_file(simple, tmp_path):
    out = tmp_path / "strip.png"
    pavlab_stripchart(*simple, filename=str(out))
    assert out.exists() and out.stat().st_size > 500
    plt.close("all")


def test_no_gridlines_no_top_right_spine(simple):
    ax = pavlab_stripchart(*simple)
    assert not ax.spines["top"].get_visible()
    assert not ax.spines["right"].get_visible()
    grid = ax.get_xgridlines() + ax.get_ygridlines()
    assert all(not ln.get_visible() for ln in grid)
    plt.close("all")


# ---- 2. Input validation ----------------------------------------------------

def test_length_mismatch_raises():
    with pytest.raises(ValueError, match="equal length"):
        pavlab_stripchart(["A", "B"], [1.0, 2.0, 3.0])


def test_color_length_mismatch_raises(simple):
    g, v = simple
    with pytest.raises(ValueError, match="color array length"):
        pavlab_stripchart(g, v, color=np.ones(len(v) + 1))


# ---- 3. Non-finite y dropped silently ---------------------------------------

def test_nonfinite_y_dropped():
    groups = ["A", "A", "B", "B", "B"]
    values = [1.0, np.nan, 2.0, np.inf, 3.0]
    ax = pavlab_stripchart(groups, values)
    # 3 finite points remain: (A,1), (B,2), (B,3)
    pts = ax.collections[-1]   # scatter PathCollection is the last collection
    assert isinstance(pts, PathCollection)
    assert len(pts.get_offsets()) == 3
    plt.close("all")


# ---- 4. Group order ---------------------------------------------------------

def test_default_group_order_matches_appearance():
    """Groups appear in the order they first appear in the input."""
    groups = ["B", "A", "B", "A"]
    values = [1.0, 2.0, 3.0, 4.0]
    ax = pavlab_stripchart(groups, values)
    labels = [t.get_text() for t in ax.get_xticklabels()]
    assert labels == ["B", "A"]
    plt.close("all")


def test_order_reorders_groups(three_groups):
    g, v = three_groups
    ax = pavlab_stripchart(g, v, order=["dko", "ctrl", "treat"])
    labels = [t.get_text() for t in ax.get_xticklabels()]
    assert labels == ["dko", "ctrl", "treat"]
    plt.close("all")


def test_order_missing_group_warns(simple):
    g, v = simple
    with pytest.warns(UserWarning, match="no data"):
        pavlab_stripchart(g, v, order=["A", "B", "MISSING"])
    plt.close("all")


# ---- 5. Mean / median reference lines ---------------------------------------

def test_show_mean_draws_hline_at_grand_mean():
    groups = ["A"] * 5 + ["B"] * 5
    values = np.arange(10, dtype=float)   # mean = 4.5
    ax = pavlab_stripchart(groups, values, show_mean=True)
    # Mean line is drawn before scatter → collections[0] is a LineCollection
    assert isinstance(ax.collections[0], LineCollection)
    segs = ax.collections[0].get_segments()
    assert len(segs) == 1
    assert segs[0][0][1] == pytest.approx(4.5)   # y-position = grand mean
    plt.close("all")


def test_show_median_draws_hline_at_grand_median():
    groups = ["A"] * 5 + ["B"] * 5
    values = np.arange(10, dtype=float)   # median = 4.5
    ax = pavlab_stripchart(groups, values, show_median=True)
    assert isinstance(ax.collections[0], LineCollection)
    segs = ax.collections[0].get_segments()
    assert segs[0][0][1] == pytest.approx(4.5)
    plt.close("all")


def test_show_mean_and_median_two_hlines():
    groups = ["A"] * 5 + ["B"] * 5
    values = np.arange(10, dtype=float)
    ax = pavlab_stripchart(groups, values, show_mean=True, show_median=True)
    line_colls = [c for c in ax.collections if isinstance(c, LineCollection)]
    assert len(line_colls) == 2
    plt.close("all")


def test_no_mean_without_flag(simple):
    ax = pavlab_stripchart(*simple, show_mean=False)
    line_colls = [c for c in ax.collections if isinstance(c, LineCollection)]
    assert len(line_colls) == 0
    plt.close("all")


# ---- 6. Log transform -------------------------------------------------------

def test_log_y_appends_label_suffix(simple):
    g, v = simple
    ax = pavlab_stripchart(g, v, log_y="log2", ylabel="Expression")
    assert "(log₂)" in ax.get_ylabel()
    plt.close("all")


def test_log_y_transforms_values():
    groups = ["A"] * 3
    values = np.array([0.0, 1.0, 3.0])   # pseudocount=1 → log2([1,2,4])=[0,1,2]
    ax = pavlab_stripchart(groups, values, log_y="log2", pseudocount=1.0,
                           origin_zero=False)
    pts = ax.collections[-1]
    y_plotted = sorted(pts.get_offsets()[:, 1].tolist())
    np.testing.assert_allclose(y_plotted, [0.0, 1.0, 2.0], atol=1e-5)
    plt.close("all")


# ---- 7. Colour modes --------------------------------------------------------

def test_uniform_black_default(simple):
    ax = pavlab_stripchart(*simple)
    pts = ax.collections[-1]
    # facecolors should all be black
    fc = pts.get_facecolors()
    assert fc.shape[1] == 4    # RGBA
    assert np.allclose(fc[:, :3], 0.0)
    plt.close("all")


def test_uniform_color_string(simple):
    g, v = simple
    ax = pavlab_stripchart(g, v, color="#2563eb")
    pts = ax.collections[-1]
    fc = pts.get_facecolors()
    # All points have the same non-black color
    assert not np.allclose(fc[:, :3], 0.0)
    assert np.allclose(fc[0], fc[-1])
    plt.close("all")


def test_categorical_color_legend(simple):
    g, v = simple
    labels = ["X"] * 10 + ["Y"] * 10
    ax = pavlab_stripchart(g, v, color=labels)
    leg = ax.get_legend()
    assert leg is not None
    handles = getattr(leg, "legend_handles", None) or leg.legendHandles
    assert len(handles) == 2
    plt.close("all")


def test_numeric_color_colorbar(simple):
    g, v = simple
    scores = np.linspace(0, 1, len(v))
    ax = pavlab_stripchart(g, v, color=scores, color_label="score")
    assert len(ax.figure.axes) == 2   # main axes + colorbar
    plt.close("all")


# ---- 8. origin_zero ---------------------------------------------------------

def test_origin_zero_pins_y_to_0(simple):
    ax = pavlab_stripchart(*simple, origin_zero=True)  # all y > 0
    assert ax.get_ylim()[0] == pytest.approx(0.0)
    plt.close("all")


def test_origin_zero_false_skips(simple):
    ax = pavlab_stripchart(*simple, origin_zero=False)
    assert ax.get_ylim()[0] > 0.0
    plt.close("all")


# ---- 9. Label size ----------------------------------------------------------

def test_label_size_large_bigger_than_small(simple):
    ax_s = pavlab_stripchart(*simple, ylabel="Y", label_size="small")
    ax_l = pavlab_stripchart(*simple, ylabel="Y", label_size="large")
    assert ax_l.get_yaxis().get_label().get_size() > \
           ax_s.get_yaxis().get_label().get_size()
    plt.close("all")


# ---- 10. ax= kwarg ----------------------------------------------------------

def test_ax_kwarg_reuses_figure(simple):
    fig, axes = plt.subplots(1, 2)
    pavlab_stripchart(*simple, ax=axes[0])
    pavlab_stripchart(*simple, ax=axes[1])
    assert len(fig.axes) == 2
    plt.close("all")
