"""Tests for pavlab_density (Python/matplotlib).
Run from skills/plotting/:
    .venv/bin/pytest tests/test_density.py -v
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
import matplotlib.figure

from pavlab_density import _detect_bounds, _group_colors, _compute_kde, pavlab_density, _ACCENT_COLORS


# ---- fixtures ---------------------------------------------------------------

@pytest.fixture
def pos_vals():
    """200 positive exponential values."""
    return np.random.default_rng(0).exponential(2.0, 200)


@pytest.fixture
def grouped(pos_vals):
    groups = np.array(["A"] * 100 + ["B"] * 100)
    return pos_vals, groups


# ---- unit: helpers ----------------------------------------------------------

def test_detect_bounds_nonneg():
    lo, hi = _detect_bounds(np.array([0.0, 1.5, 3.0]))
    assert lo == 0.0
    assert hi is None


def test_detect_bounds_probability():
    lo, hi = _detect_bounds(np.array([0.0, 0.3, 0.9, 1.0]))
    assert lo == 0.0
    assert hi == 1.0


def test_detect_bounds_signed():
    lo, hi = _detect_bounds(np.array([-1.0, 0.5, 2.0]))
    assert lo is None
    assert hi is None


def test_group_colors_none_cycles_accent():
    colors = _group_colors(None, ["A", "B", "C"])
    assert colors[0] == _ACCENT_COLORS[0]
    assert colors[1] == _ACCENT_COLORS[1]
    assert len(colors) == 3


def test_group_colors_uniform_string():
    colors = _group_colors("red", ["A", "B"])
    assert all(c == "red" for c in colors)


def test_group_colors_explicit_list():
    colors = _group_colors(["#aaa", "#bbb"], ["A", "B"])
    assert colors == ["#aaa", "#bbb"]


def test_group_colors_length_mismatch():
    with pytest.raises(ValueError, match="color list length"):
        _group_colors(["red"], ["A", "B"])


def test_compute_kde_shape():
    arr = np.linspace(1, 5, 50)
    x, d = _compute_kde(arr, "scott")
    assert len(x) == len(d) == 512
    assert np.all(d >= 0)


def test_compute_kde_reflection_zeros_outside():
    arr = np.linspace(0.01, 3.0, 100)
    x, d = _compute_kde(arr, "scott", lo=0.0)
    assert d[x < 0].sum() == 0.0
    assert d.max() > 0


# ---- density mode -----------------------------------------------------------

def test_density_single_returns_axes(pos_vals):
    ax = pavlab_density(pos_vals)
    assert hasattr(ax, "collections") or hasattr(ax, "lines")
    plt.close("all")


def test_density_writes_file(pos_vals, tmp_path):
    out = tmp_path / "dens.png"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pavlab_density(pos_vals, filename=str(out))
    assert out.exists() and out.stat().st_size > 500
    plt.close("all")


def test_density_bounds_warning_when_nonneg(pos_vals):
    with pytest.warns(UserWarning, match="reflect_bounds"):
        pavlab_density(pos_vals)
    plt.close("all")


def test_density_no_bounds_warning_when_signed():
    vals = np.linspace(-3.0, 3.0, 100)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        try:
            pavlab_density(vals)
        except UserWarning as e:
            if "reflect_bounds" in str(e):
                pytest.fail("Should not warn about bounds for signed data")
    plt.close("all")


def test_density_reflect_bounds_no_leak():
    """With reflect_bounds=True, density curve should be zero for x < 0."""
    rng = np.random.default_rng(1)
    vals = rng.exponential(1.0, 300)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ax = pavlab_density(vals, reflect_bounds=True)
    lines = ax.get_lines()
    for ln in lines:
        xdata, ydata = ln.get_xdata(), ln.get_ydata()
        neg_mask = xdata < 0
        assert np.all(ydata[neg_mask] == pytest.approx(0.0, abs=1e-6)), \
            "density leaks below 0 despite reflect_bounds=True"
    plt.close("all")


def test_density_grouped_overlay_returns_axes(grouped):
    vals, groups = grouped
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ax = pavlab_density(vals, groups=groups, kind="density")
    assert hasattr(ax, "lines")
    plt.close("all")


def test_density_grouped_warns_over_3_groups():
    rng = np.random.default_rng(2)
    vals = rng.standard_normal(100)
    groups = np.array(["A"] * 25 + ["B"] * 25 + ["C"] * 25 + ["D"] * 25)
    with pytest.warns(UserWarning, match="facet=True"):
        pavlab_density(vals, groups=groups, kind="density", facet=False)
    plt.close("all")


def test_density_faceted_returns_figure(grouped):
    vals, groups = grouped
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = pavlab_density(vals, groups=groups, kind="density", facet=True)
    assert isinstance(result, matplotlib.figure.Figure)
    assert len(result.axes) == 2
    plt.close("all")


def test_density_log_x_label_suffix(pos_vals):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ax = pavlab_density(pos_vals, log_x="log2", xlabel="TPM")
    assert "(log₂)" in ax.get_xlabel()
    plt.close("all")


def test_density_show_mean_vline(pos_vals):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ax = pavlab_density(pos_vals, show_mean=True)
    vlines = [ln for ln in ax.get_lines() if ln.get_linestyle() == "--"]
    assert len(vlines) >= 1
    plt.close("all")


def test_density_show_median_vline(pos_vals):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ax = pavlab_density(pos_vals, show_median=True)
    dotted = [ln for ln in ax.get_lines() if ln.get_linestyle() in (":", "dotted")]
    assert len(dotted) >= 1
    plt.close("all")


# ---- histogram mode ---------------------------------------------------------

def test_histogram_returns_axes(pos_vals):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ax = pavlab_density(pos_vals, kind="histogram")
    assert len(ax.patches) > 0
    plt.close("all")


def test_histogram_faceted_returns_figure(grouped):
    vals, groups = grouped
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = pavlab_density(vals, groups=groups, kind="histogram", facet=True)
    assert isinstance(result, matplotlib.figure.Figure)
    plt.close("all")


def test_histogram_shared_bins_grouped(grouped):
    """Faceted histogram panels should have identical bin edges."""
    vals, groups = grouped
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fig = pavlab_density(vals, groups=groups, kind="histogram", facet=True)
    edges0 = [p.get_x() for p in fig.axes[0].patches]
    edges1 = [p.get_x() for p in fig.axes[1].patches]
    assert len(edges0) == len(edges1)
    plt.close("all")


# ---- violin mode ------------------------------------------------------------

def test_violin_requires_groups(pos_vals):
    with pytest.raises(ValueError, match="groups"):
        pavlab_density(pos_vals, kind="violin")


def test_violin_returns_axes(grouped):
    vals, groups = grouped
    ax = pavlab_density(vals, groups=groups, kind="violin")
    assert hasattr(ax, "collections")
    plt.close("all")


def test_violin_show_mean_hline(grouped):
    vals, groups = grouped
    ax = pavlab_density(vals, groups=groups, kind="violin", show_mean=True)
    hlines = [ln for ln in ax.get_lines() if ln.get_linestyle() == "--"]
    assert len(hlines) >= 1
    expected = float(np.mean(vals))
    y_vals = [float(ln.get_ydata()[0]) for ln in hlines]
    assert any(abs(y - expected) < 1e-6 for y in y_vals)
    plt.close("all")


def test_violin_group_order(grouped):
    vals, groups = grouped
    ax = pavlab_density(vals, groups=groups, kind="violin", order=["B", "A"])
    labels = [t.get_text() for t in ax.get_xticklabels()]
    assert labels == ["B", "A"]
    plt.close("all")


# ---- input validation -------------------------------------------------------

def test_unequal_length_raises(pos_vals):
    with pytest.raises(ValueError, match="equal length"):
        pavlab_density(pos_vals, groups=np.array(["A"] * (len(pos_vals) - 1)))


def test_nonfinite_dropped_silently():
    vals = np.array([1.0, np.nan, 2.0, np.inf, 3.0])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ax = pavlab_density(vals, kind="histogram", stat="count")
    total_count = sum(p.get_height() for p in ax.patches)
    assert total_count == pytest.approx(3.0)
    plt.close("all")


def test_theme_no_top_right_spine(pos_vals):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ax = pavlab_density(pos_vals)
    assert not ax.spines["top"].get_visible()
    assert not ax.spines["right"].get_visible()
    plt.close("all")
