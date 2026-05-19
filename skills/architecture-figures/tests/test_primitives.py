"""Smoke + unit tests for the architecture-figures skill.

Covers:
  - palette tint map sanity
  - layout.figure() returns 0..100 axes for each canonical shape
  - layout.grid_columns() respects width budget / raises when over
  - primitives.fit_text() shrinks long labels and floors at min
  - primitives draw something into an axes without raising
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.layout import figure, FIGSIZES, grid_columns, autosize_columns  # noqa: E402
from pavlab_arch.primitives import (  # noqa: E402
    fit_text, stage_box, dual_stage_box, stack_box, perf_gauge,
    ensemble_proposer, arrow, box,
    gantt_bar, gantt_variance, gantt_bar_two_tier,
    gantt_bold_changed_labels, GanttTask,
)
from pavlab_arch.style import apply_rcparams  # noqa: E402


# ---- palette --------------------------------------------------------------

def test_tint_known_color_returns_lighter_variant():
    out = P.tint(P.ACCENT)
    assert out.startswith("#") and out.lower() != P.ACCENT.lower()


def test_tint_unknown_color_returns_default_gray():
    assert P.tint("#123456") == "#f9fafb"


# ---- layout ---------------------------------------------------------------

@pytest.mark.parametrize("shape", list(FIGSIZES))
def test_figure_returns_uniform_axis_coords(shape):
    fig, ax = figure(shape=shape)
    assert ax.get_xlim() == (0, 100)
    assert ax.get_ylim() == (0, 100)
    plt.close(fig)


def test_figure_unknown_shape_raises():
    with pytest.raises(ValueError):
        figure(shape="not-a-shape")


def test_grid_columns_distributes_evenly_when_underfull():
    xs, ws = grid_columns([10, 10, 10], x_start=0, x_end=60)
    assert len(xs) == 3 and len(ws) == 3
    # widths preserved exactly when there's slack
    assert ws == [10, 10, 10]
    # columns are non-overlapping
    for i in range(len(xs) - 1):
        assert xs[i] + ws[i] <= xs[i + 1] + 1e-9


def test_grid_columns_scales_down_when_overfull():
    xs, ws = grid_columns([30, 30, 30], x_start=0, x_end=50, min_gap=2)
    # 30+30+30+2+2 = 94 > 50 → scaled down
    assert sum(ws) < 90
    # still no overlap
    for i in range(len(xs) - 1):
        assert xs[i] + ws[i] <= xs[i + 1] + 1e-9


def test_grid_columns_explicit_gap_overflow_raises():
    with pytest.raises(ValueError):
        grid_columns([30, 30, 30], x_start=0, x_end=50, gap=5)


def test_grid_columns_rejects_zero_width():
    with pytest.raises(ValueError):
        grid_columns([10, 0, 10])


def test_autosize_columns_clamps():
    ws = autosize_columns(["a", "x" * 200, "medium"], min_w=4, max_w=12)
    assert all(4 <= w <= 12 for w in ws)


# ---- text fitting ---------------------------------------------------------

def test_fit_text_short_label_keeps_default_size():
    fs = fit_text("hi", box_w=20, fontsize=10)
    assert fs == 10.0


def test_fit_text_long_label_shrinks():
    fs = fit_text("this is a very long label that won't fit", box_w=4, fontsize=10)
    assert fs < 10.0


def test_fit_text_floors_at_min():
    fs = fit_text("x" * 500, box_w=2, fontsize=10, min_fontsize=6.5)
    assert fs == pytest.approx(6.5)


# ---- primitive smoke ------------------------------------------------------

def test_smoke_draw_all_primitives_no_error():
    apply_rcparams()
    fig, ax = figure(shape="wide_half")
    stage_box(ax, 5, 40, 12, 20, "LLM stage", P.ACCENT, subtitle="model X")
    stage_box(ax, 20, 40, 12, 20, "Rules",    P.DET, is_det=True,
              subtitle="+ resolver")
    ensemble_proposer(ax, 35, 40, 12, 20,
                      top=("agent A", P.ACCENT_3),
                      bot=("agent B", P.ACCENT))
    arrow(ax, 17, 50, 20, 50)
    perf_gauge(ax, 55, 50, 20, 6, value=0.82, curator_value=0.75,
               color=P.BAR_FACTOR)
    box(ax, 80, 45, 15, 10, text="plain", fc="white")
    plt.close(fig)


def test_dual_stage_box_draws_both_halves():
    apply_rcparams()
    fig, ax = figure(shape="wide_half")
    # Hybrid stage: AI recommend (blue, left) + curator triage (amber, right)
    dual_stage_box(ax, 10, 40, 18, 12, "Candidate",
                   P.ACCENT, P.ACCENT_3,
                   subtitle="AI recommend · curator triage")
    # Should add at least two patches (one polygon per half) plus text
    assert len(ax.patches) >= 2
    assert any("Candidate" in t.get_text() for t in ax.texts)
    plt.close(fig)


def test_stack_box_draws_pile_and_ticket():
    apply_rcparams()
    fig, ax = figure(shape="wide_half")
    # Pile of 3 cards + ticket on top
    stack_box(ax, 10, 40, 18, 9,
              label="needs alignment to genome",
              task="rerun aligner",
              color=P.DET)
    # At least n_cards (3) pile patches + 1 ticket patch
    assert len(ax.patches) >= 4
    # Both texts present
    texts = [t.get_text() for t in ax.texts]
    assert "needs alignment to genome" in texts
    assert "rerun aligner" in texts
    plt.close(fig)


def test_stack_box_with_single_card():
    apply_rcparams()
    fig, ax = figure(shape="wide_half")
    stack_box(ax, 10, 40, 18, 9,
              label="solo set", task="run it", color=P.ACCENT,
              n_cards=1)
    plt.close(fig)


def test_dual_stage_box_no_subtitle_one_label():
    apply_rcparams()
    fig, ax = figure(shape="wide_half")
    dual_stage_box(ax, 10, 40, 18, 12, "Hybrid", P.ACCENT, P.ACCENT_3)
    labels = [t.get_text() for t in ax.texts]
    assert "Hybrid" in labels
    plt.close(fig)


# ---- Gantt: variance + two-tier diff -------------------------------------

@pytest.fixture
def _gantt_ax():
    apply_rcparams()
    fig, ax = plt.subplots(figsize=(6, 2))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.5, 0.5)
    yield ax
    plt.close(fig)


def test_gantt_variance_not_started_returns_not_started(_gantt_ax):
    n_before = len(_gantt_ax.patches)
    out = gantt_variance(_gantt_ax, 0, plan_start=4, plan_end=6,
                         done_end=0, today=2)
    assert out == "not_started"
    assert len(_gantt_ax.patches) == n_before  # nothing drawn


def test_gantt_variance_complete_returns_complete(_gantt_ax):
    n_before = len(_gantt_ax.patches)
    out = gantt_variance(_gantt_ax, 0, plan_start=1, plan_end=3,
                         done_end=3, today=5)
    assert out == "complete"
    assert len(_gantt_ax.patches) == n_before


def test_gantt_variance_behind_draws_overlay(_gantt_ax):
    n_before = len(_gantt_ax.patches)
    out = gantt_variance(_gantt_ax, 0, plan_start=1, plan_end=5,
                         done_end=2, today=4)
    assert out == "behind"
    assert len(_gantt_ax.patches) == n_before + 1


def test_gantt_variance_overdue_returns_overdue(_gantt_ax):
    out = gantt_variance(_gantt_ax, 0, plan_start=1, plan_end=4,
                         done_end=2, today=6)
    assert out == "overdue"


def test_gantt_variance_ahead_no_overlay(_gantt_ax):
    n_before = len(_gantt_ax.patches)
    out = gantt_variance(_gantt_ax, 0, plan_start=1, plan_end=6,
                         done_end=5, today=3)
    assert out == "ahead"
    assert len(_gantt_ax.patches) == n_before


def test_gantt_variance_on_track_no_overlay(_gantt_ax):
    n_before = len(_gantt_ax.patches)
    out = gantt_variance(_gantt_ax, 0, plan_start=1, plan_end=6,
                         done_end=3, today=3)
    assert out == "on_track"
    assert len(_gantt_ax.patches) == n_before


def test_gantt_bar_two_tier_draws_two_sets(_gantt_ax):
    n_before = len(_gantt_ax.patches)
    changed = gantt_bar_two_tier(
        _gantt_ax, 0,
        plan_start=1, plan_end=5,
        done_end_then=2, status_then="inflight",
        done_end_now=5, status_now="done",
    )
    # Each gantt_bar draws planned bg + status overlay (if any) + done
    # overlay (if any). Both tiers together must add at least 4 bars
    # (2 planned bgs + 1 status overlay (inflight T1) + 2 done overlays).
    assert len(_gantt_ax.patches) >= n_before + 4
    assert changed is True


def test_gantt_bar_two_tier_unchanged_returns_false(_gantt_ax):
    changed = gantt_bar_two_tier(
        _gantt_ax, 0,
        plan_start=1, plan_end=5,
        done_end_then=3, status_then="inflight",
        done_end_now=3, status_now="inflight",
    )
    assert changed is False


def test_gantt_bold_changed_labels_bolds_only_changed_rows():
    apply_rcparams()
    fig, ax = plt.subplots()
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["row0", "row1", "row2"])
    # bottom-to-top status order: row0=unchanged, row1=promoted, row2=regressed
    gantt_bold_changed_labels(
        ax,
        statuses_then=["inflight", "planned",  "done"],
        statuses_now =["inflight", "inflight", "blocked"],
        color_regressions=True,
    )
    labels = ax.get_yticklabels()
    assert labels[0].get_fontweight() != "bold"
    assert labels[1].get_fontweight() == "bold"
    assert labels[2].get_fontweight() == "bold"
    # row2 regressed (done -> blocked) -> should be red
    assert labels[2].get_color() == P.ACCENT_4
    # row1 promoted (planned -> inflight) -> should keep default color
    assert labels[1].get_color() != P.ACCENT_4
    plt.close(fig)


def test_gantt_bar_alpha_scale_paler_overlay():
    """alpha_scale < 1.0 should produce paler overlays. Smoke check
    that the parameter is accepted and does not raise."""
    apply_rcparams()
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.5, 0.5)
    gantt_bar(ax, 0, 1, 5, 3, status="inflight", alpha_scale=0.45)
    plt.close(fig)
