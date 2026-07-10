"""Matplotlib rcParams for Pavlab architecture figures.

Helvetica fallback chain + editable SVG text + white facecolor +
no top/right spines (those are for data axes, not architecture
diagrams which use ax.set_xticks([]) anyway).
"""
from __future__ import annotations
import matplotlib.pyplot as plt
from . import palette as _p


def apply_rcparams() -> None:
    """Set rcParams to the Pavlab figure style.

    Call once at the top of every figure script — before any
    `plt.subplots()`.
    """
    plt.rcParams.update({
        # Only fonts a stock macOS / Illustrator install ships with.
        # Avoid DejaVu Sans (bundled with matplotlib but not present
        # on most systems) — referenced fonts that aren't installed
        # trigger a Font Problems dialog on SVG roundtrip.
        "font.family": ["Helvetica", "Arial", "sans-serif"],
        # ...but the trailing generic "sans-serif" gets expanded through
        # ``font.sans-serif`` (and monospace through ``font.monospace``),
        # which default to a DejaVu-first list — so with ``svg.fonttype:
        # none`` the SVG font-family string leaked "DejaVu Sans" deck-wide.
        # Pin BOTH generic families to installed, DejaVu-free fallbacks so
        # the round-trip stays clean (caught 2026-07-02, figure regen).
        "font.sans-serif": ["Helvetica", "Arial", "Liberation Sans"],
        "font.monospace": ["Menlo", "Consolas", "Courier New", "monospace"],
        "svg.fonttype": "none",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "white",
        "axes.labelcolor": _p.TEXT,
        "axes.titlesize": 11,
        "axes.titleweight": "normal",
        "axes.titlelocation": "left",
        "xtick.color": _p.SUBTLE,
        "ytick.color": _p.SUBTLE,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.bottom": False,
        "axes.spines.left": False,
    })


# The style guide's DISPLAY face — Gill Sans for titles, section headers, and
# explanatory prose OUTSIDE the plot area. In-plot text (axis labels, tick
# numbers, in-plot annotations) deliberately stays Helvetica: "Gill Sans does
# the talking, Helvetica does the measuring, monospace holds identifiers."
#
# Gill Sans ships on macOS (as "Gill Sans") and Windows (as "Gill Sans MT").
# We resolve to whichever variant is actually installed and prepend ONLY that
# one — listing font names matplotlib can't find spams a `findfont` warning per
# name, per text, so we never put a missing name in the family list. The tail
# (Helvetica/Arial/sans-serif) keeps it sane where no Gill is present.
#
# This is a considered exception to the skill's "only reference installed
# fonts" SVG rule (§1 below): it rides on *titles / prose* you're willing to
# let fall back — never on load-bearing axis text — and resolves cleanly on a
# stock Mac Illustrator install. Don't set this as the global font.family
# (that would put your axis numbers in Gill Sans too); apply it per-title via
# display_title() instead.
def _resolve_display_font() -> list[str]:
    from matplotlib import font_manager as _fm
    installed = {f.name for f in _fm.fontManager.ttflist}
    tail = ["Helvetica", "Arial", "sans-serif"]
    for name in ("Gill Sans", "Gill Sans MT", "GillSans", "Gill Sans Nova"):
        if name in installed:
            return [name] + tail
    return tail


DISPLAY_FONT = _resolve_display_font()


def display_title(obj, text: str, **kwargs):
    """Set a title in the DISPLAY face (Gill Sans), leaving the plot's
    axis/tick text in Helvetica.

    ``obj`` is an Axes (routes to ``set_title``) or a Figure (routes to
    ``suptitle``). Extra kwargs pass straight through, so
    ``display_title(ax, "Grouped bar", loc="left", fontsize=13)`` works. Use
    this for titles / section headers / free prose; leave ``set_xlabel`` /
    tick formatting alone so the numbers stay in the measuring face.
    """
    import matplotlib.axes
    kwargs.setdefault("fontfamily", DISPLAY_FONT)
    if isinstance(obj, matplotlib.axes.Axes):
        return obj.set_title(text, **kwargs)
    return obj.suptitle(text, **kwargs)


def apply_sci_rcparams(scheme: str = "A") -> None:
    """Warm-paper base for the colour-blind-safe scientific palettes
    (`palette.OKABE_ITO` / `TOL_MUTED` / `SCI_A` / `SCI_B`).

    This is the DATA-figure companion to `apply_rcparams()` (which is tuned
    for spineless architecture diagrams on a white ground). Use this one for
    scatter / bar / line panels: warm paper (`palette.PAPER`), warm ink
    (`palette.INK`), a quiet warm grid, top/right spines dropped but
    left/bottom kept, and the scheme's four solids as the prop_cycle so bare
    `ax.plot` / `ax.bar` calls come out in palette order. `scheme` picks the
    cycle: `"A"` (Okabe–Ito) or `"B"` (Tol muted). The equivalent literal is
    shipped as `assets/figures.mplstyle` for `plt.style.use`.

    Fonts follow the same SVG-safety rule as `apply_rcparams` (Helvetica /
    Arial + installed fallbacks, never DejaVu). The style guide's display
    face is Gill Sans; pinning it here would break the SVG round-trip on
    machines that don't ship it, so titles stay in the pinned sans — set
    `font.family` yourself afterward if you have Gill Sans and don't need
    portability.
    """
    from cycler import cycler
    plt.rcParams.update({
        "font.family": ["Helvetica", "Arial", "sans-serif"],
        "font.sans-serif": ["Helvetica", "Arial", "Liberation Sans"],
        "font.monospace": ["Menlo", "Consolas", "Courier New", "monospace"],
        "svg.fonttype": "none",
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "normal",
        "axes.titlelocation": "left",
        "axes.labelsize": 11,
        "figure.facecolor": _p.PAPER,
        "axes.facecolor": _p.PAPER,
        "savefig.facecolor": _p.PAPER,
        "axes.edgecolor": _p.INK,
        "axes.labelcolor": _p.INK,
        "text.color": _p.INK,
        "axes.linewidth": 0.8,
        "xtick.color": _p.INK,
        "ytick.color": _p.INK,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": _p.SCI_GRID,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": cycler("color", _p.sci_cycle(scheme)),
        "savefig.dpi": 300,
    })
