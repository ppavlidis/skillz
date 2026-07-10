"""Tests for the colour-blind-safe scientific palettes (option C).

Covers the silent-failure categories that matter for a palette:
  - every colour is a valid 6-digit hex (a typo'd hex fails silently in a
    figure — matplotlib renders black, no error)
  - solids within a scheme are distinct (a duplicate would merge two series)
  - tint() resolves the scheme fills AND still falls back for unknowns
  - the ordered cycles have the documented length / first colour
  - apply_sci_rcparams() actually sets the warm-paper base + palette cycle
  - the shipped figures.mplstyle parses with no warnings and matches the
    programmatic Direction-A cycle (the two must not drift apart)
"""
from __future__ import annotations
import re
import sys
import warnings
from pathlib import Path

import pytest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.style import (  # noqa: E402
    apply_sci_rcparams, display_title, DISPLAY_FONT,
)

_HEX = re.compile(r"#[0-9A-Fa-f]{6}$")
_MPLSTYLE = Path(__file__).resolve().parents[1] / "assets" / "figures.mplstyle"


def _all_solids():
    out = list(P.OKABE_ITO.values()) + list(P.TOL_MUTED.values())
    for sch in P.SCI_SCHEMES.values():
        out += [pair[0] for pair in sch.values()]
    return out


def _all_hex():
    out = _all_solids()
    for sch in P.SCI_SCHEMES.values():
        out += [pair[1] for pair in sch.values()]
    out += [P.INK, P.PAPER, P.SCI_GRID]
    return out


# ---- hex validity ---------------------------------------------------------

@pytest.mark.parametrize("hx", _all_hex())
def test_every_colour_is_valid_hex(hx):
    assert _HEX.match(hx), f"{hx!r} is not a #RRGGBB hex"


def test_standard_palettes_have_expected_sizes():
    # Okabe–Ito is 8 colours; Tol muted is 9 + a light grey.
    assert len(P.OKABE_ITO) == 8
    assert len(P.TOL_MUTED) == 10
    # Both cycles expose all their colours.
    assert len(P.OKABE_ITO_CYCLE) == 8
    assert len(P.TOL_MUTED_CYCLE) == 9


# ---- distinctness ---------------------------------------------------------

@pytest.mark.parametrize("scheme", ["A", "B"])
def test_scheme_solids_are_distinct(scheme):
    solids = [v[0] for v in P.sci_scheme(scheme).values()]
    assert len(set(s.lower() for s in solids)) == len(solids)


@pytest.mark.parametrize("scheme", ["A", "B"])
def test_scheme_solid_and_tint_differ(scheme):
    for name, (solid, tint) in P.sci_scheme(scheme).items():
        assert solid.lower() != tint.lower(), f"{scheme}/{name} solid==tint"


def test_okabe_ito_colours_are_unique():
    vals = [v.lower() for v in P.OKABE_ITO.values()]
    assert len(set(vals)) == len(vals)


# ---- tint resolution ------------------------------------------------------

def test_tint_resolves_scheme_fills():
    assert P.tint("#0072B2") == "#DBE9F4"      # Direction A blue -> its tint
    assert P.tint("#44AA99") == "#E4F1EE"      # Direction B teal -> its tint


def test_tint_unknown_still_falls_back():
    # Guard the earlier behaviour: an unknown colour returns the soft grey,
    # not a KeyError.
    assert P.tint("#123456") == "#f9fafb"


# ---- cycles / accessors ---------------------------------------------------

def test_sci_cycle_order_and_first_colour():
    assert P.sci_cycle("A")[0] == "#0072B2"    # grounded-blue leads
    assert P.sci_cycle("B")[0] == "#4477AA"
    assert len(P.sci_cycle("A")) == 4
    assert len(P.sci_cycle("B")) == 4


def test_sci_scheme_unknown_direction_raises():
    with pytest.raises(ValueError):
        P.sci_scheme("Z")
    with pytest.raises(ValueError):
        P.sci_cycle("nope")


def test_sci_scheme_case_insensitive():
    assert P.sci_scheme("a") is P.sci_scheme("A")


# ---- rcParams applier -----------------------------------------------------

@pytest.mark.parametrize("scheme,first", [("A", "#0072b2"), ("B", "#4477aa")])
def test_apply_sci_rcparams_sets_paper_and_cycle(scheme, first):
    apply_sci_rcparams(scheme)
    assert plt.rcParams["figure.facecolor"] == P.PAPER
    assert plt.rcParams["axes.facecolor"] == P.PAPER
    assert plt.rcParams["axes.edgecolor"] == P.INK
    assert plt.rcParams["grid.color"] == P.SCI_GRID
    # SVG-safe fonts: never DejaVu (would break the Illustrator round-trip).
    assert "DejaVu Sans" not in plt.rcParams["font.sans-serif"]
    cyc = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    assert cyc[0].lower() == first


# ---- shipped mplstyle -----------------------------------------------------

def test_figures_mplstyle_exists():
    assert _MPLSTYLE.is_file()


def test_figures_mplstyle_parses_without_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        plt.style.use(str(_MPLSTYLE))
    assert plt.rcParams["figure.facecolor"] == P.PAPER


def test_mplstyle_cycle_matches_direction_A():
    # The literal asset and the programmatic applier must not drift.
    plt.style.use(str(_MPLSTYLE))
    cyc = [c.lower() for c in
           plt.rcParams["axes.prop_cycle"].by_key()["color"]]
    assert cyc == [c.lower() for c in P.sci_cycle("A")]


# ---- display font (Gill Sans titles, Helvetica axes) ----------------------

def test_display_font_has_safe_tail():
    # However Gill resolves (or not), the chain must end in installed,
    # DejaVu-free fallbacks so the SVG round-trip stays clean.
    assert DISPLAY_FONT[-3:] == ["Helvetica", "Arial", "sans-serif"]
    assert "DejaVu Sans" not in DISPLAY_FONT


def test_display_title_on_axes_uses_display_font_and_leaves_axes_helvetica():
    apply_sci_rcparams("A")
    fig, ax = plt.subplots()
    t = display_title(ax, "Grouped bar")
    ax.set_ylabel("score")
    assert t.get_fontfamily() == DISPLAY_FONT          # title -> Gill Sans chain
    # axis label untouched -> inherits the Helvetica rcParam family
    assert ax.yaxis.label.get_fontfamily() != DISPLAY_FONT
    plt.close(fig)


def test_display_title_on_figure_sets_suptitle():
    fig, ax = plt.subplots()
    t = display_title(fig, "Direction A")
    assert t.get_text() == "Direction A"
    assert t.get_fontfamily() == DISPLAY_FONT
    plt.close(fig)
