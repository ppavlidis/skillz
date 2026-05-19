"""Tests for pavlab_boxplot (Python/matplotlib).
Run from skills/plotting/:
    .venv/bin/pytest tests/test_boxplot.py -v
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
from matplotlib.collections import PathCollection

from pavlab_boxplot import pavlab_boxplot


# ---- fixtures ---------------------------------------------------------------

@pytest.fixture
def three_groups():
    rng = np.random.default_rng(42)
    groups = ["WT"] * 20 + ["KO"] * 20 + ["DKO"] * 20
    values = np.concatenate([
        rng.normal(2.0, 0.5, 20),
        rng.normal(2.6, 0.7, 20),
        rng.normal(3.2, 0.4, 20),
    ])
    return groups, values


# ---- Argument validation ----------------------------------------------------

def test_rejects_unequal_xy_lengths():
    with pytest.raises(ValueError, match="equal length"):
        pavlab_boxplot(["A", "B"], [1.0, 2.0, 3.0])
    plt.close("all")


def test_rejects_bad_points_kind():
    with pytest.raises(ValueError, match="points_kind"):
        pavlab_boxplot(["A", "A"], [1.0, 2.0], points_kind="violin")


def test_rejects_unknown_kwargs():
    """The error= parameter no longer exists — the box+whiskers IS the
    spread visualisation; an overlaid error bar is intentionally
    unsupported. Passing error= should raise TypeError."""
    with pytest.raises(TypeError):
        pavlab_boxplot(["A", "A"], [1.0, 2.0], error="sd")


# ---- Rendering — structural assertions --------------------------------------

def test_default_draws_points_and_box(three_groups):
    """Default invocation: scatter (points underneath) + boxplot patches.
    No error bar artist — the box's whiskers / IQR / median are the
    spread visualisation."""
    groups, values = three_groups
    fig, ax = plt.subplots()
    pavlab_boxplot(groups, values, ax=ax)

    scatters = [c for c in ax.collections if isinstance(c, PathCollection)]
    assert len(scatters) == 1

    patches = [p for p in ax.patches]
    assert len(patches) >= 3  # one box per group

    err_lines = [l for l in ax.lines if l.get_marker() == "_"]
    assert len(err_lines) == 0
    plt.close(fig)


def test_show_points_false_compact_box(three_groups):
    """show_points=False: just the box (no points, no error bar). The
    whiskers and IQR still convey spread."""
    groups, values = three_groups
    fig, ax = plt.subplots()
    pavlab_boxplot(groups, values, show_points=False, ax=ax)

    scatters = [c for c in ax.collections if isinstance(c, PathCollection)]
    assert len(scatters) == 0

    patches = [p for p in ax.patches]
    assert len(patches) >= 3  # boxes still drawn
    plt.close(fig)


def test_strip_vs_swarm_both_render(three_groups):
    groups, values = three_groups
    for kind in ("strip", "swarm"):
        fig, ax = plt.subplots()
        pavlab_boxplot(groups, values, points_kind=kind, ax=ax)
        scatters = [c for c in ax.collections if isinstance(c, PathCollection)]
        assert len(scatters) == 1
        plt.close(fig)


def test_swarm_offsets_are_non_zero(three_groups):
    groups, values = three_groups
    fig, ax = plt.subplots()
    pavlab_boxplot(groups, values, points_kind="swarm", ax=ax)
    sc = [c for c in ax.collections if isinstance(c, PathCollection)][0]
    offsets = sc.get_offsets()
    x_coords = offsets[:, 0]
    in_g0 = (x_coords > -0.5) & (x_coords < 0.5)
    assert np.std(x_coords[in_g0]) > 0.0
    plt.close(fig)


def test_xtick_labels_match_groups(three_groups):
    groups, values = three_groups
    fig, ax = plt.subplots()
    pavlab_boxplot(groups, values, ax=ax)
    labels = [t.get_text() for t in ax.get_xticklabels()]
    assert labels == ["WT", "KO", "DKO"]
    plt.close(fig)


def test_xtick_labels_respect_order(three_groups):
    groups, values = three_groups
    fig, ax = plt.subplots()
    pavlab_boxplot(groups, values, order=["DKO", "WT", "KO"], ax=ax)
    labels = [t.get_text() for t in ax.get_xticklabels()]
    assert labels == ["DKO", "WT", "KO"]
    plt.close(fig)


def test_log_y_label_suffix_when_ylabel_given(three_groups):
    groups, values = three_groups
    fig, ax = plt.subplots()
    pavlab_boxplot(groups, values, log_y="log2", ylabel="Counts", ax=ax)
    ylabel = ax.get_ylabel()
    assert "log" in ylabel.lower()
    plt.close(fig)


def test_filename_saves_file(tmp_path, three_groups):
    groups, values = three_groups
    out = tmp_path / "box.png"
    pavlab_boxplot(groups, values, filename=str(out), figsize=(4, 4))
    assert out.exists() and out.stat().st_size > 0


def test_non_finite_y_dropped():
    groups = ["A", "A", "B", "B"]
    values = [1.0, np.nan, 3.0, 4.0]
    fig, ax = plt.subplots()
    pavlab_boxplot(groups, values, ax=ax)
    sc = [c for c in ax.collections if isinstance(c, PathCollection)][0]
    assert sc.get_offsets().shape[0] == 3
    plt.close(fig)


def test_empty_y_warns():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig, ax = plt.subplots()
        pavlab_boxplot(["A", "B"], [np.nan, np.nan], ax=ax)
        plt.close(fig)
    msgs = [str(w.message) for w in caught]
    assert any("no finite data points" in m for m in msgs)
