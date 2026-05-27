"""pavlab matplotlib style — publication-grade defaults.

One call to ``apply_pavlab_style()`` configures every figure that follows
with the lab's house style: heavy spines, dark text, thick ticks, EPS
fonts embedded, and a few helpers for paired-bar contrast that survive
journal EPS export.

Why a separate module instead of an rcParams block in every script?

- Repeated rcParams blocks drift apart between projects. One that's
  shipped in the skill is the single source of truth.
- The defaults below were vetted against an Adobe Illustrator
  round-trip with a real reviewer in front of the file. The notable
  bug fixes encoded here (alpha → ``lighten()`` for paired bars; cap
  thickness separated from line thickness; TrueType font embedding for
  Illustrator edibility) cost real review-cycle time the first time;
  shipping them as a skill stops the next project from rediscovering
  the same gotchas.

Public API
----------
``apply_pavlab_style()``            Apply the rcParams + return them.
``lighten(hex_color, frac=0.55)``   Print-safe substitute for ``alpha=``.
``ERR_KW``, ``ERR_CAPSIZE``         Bar-plot error-bar kwargs / capsize.
``ERR_KW_SCATTER``, ``ERR_CAPSIZE_SCATTER``
                                    Same, tuned for scatter/PR plots.
``ERR_ECOLOR_SCATTER``              Default error-bar colour on scatter.

Usage
-----

    from pavlab_style import apply_pavlab_style, lighten, ERR_KW, ERR_CAPSIZE
    apply_pavlab_style()

    bars = ax.bar(x, y, color=cols, edgecolor="#1f2937", linewidth=2.0,
                  yerr=err, capsize=ERR_CAPSIZE, error_kw=ERR_KW)

    # Paired light/dark bars — use lighten() instead of alpha=
    light = [lighten(c, 0.55) for c in cols]
    ax.bar(x - w/2, y_strict,  color=light, ...)
    ax.bar(x + w/2, y_lenient, color=cols,  ...)

See the SKILL.md for the full rationale.
"""
from __future__ import annotations

import matplotlib as mpl

# ---------------------------------------------------------------------------
# Publication-grade error-bar styling — these are the values that survived
# the verifier-figure Illustrator round-trip (a real reviewer iteration).
#
# - elinewidth 2.0 matches the bar-edge / axis stroke weight.
# - capthick 2.0 is the same as elinewidth so the cap reads as a
#   continuation of the line connecting it to the bar, not a heavier
#   feature. (Earlier iterations bumped capthick to 3.0 to lift the
#   cap above coincident bar edges; visual feedback was that the
#   thicker cap looked too prominent. The cap-visible-when-coincident
#   problem is addressed instead by capsize protruding beyond the
#   bar width — see next.)
# - capsize 7 protrudes beyond a typical bar width (0.36 data units →
#   ~25–35 device pt at column-width figure sizes), so the cap is
#   visible even when the upper Wilson bound clips at 1.0 (k = n bars
#   sitting at exactly 100 %).
# - ecolor near-black so caps sit cleanly on top of paler tinted fills.
# ---------------------------------------------------------------------------
ERR_KW: dict[str, float | str] = {
    "elinewidth": 2.0,
    "capthick":   2.0,
    "ecolor":     "#1f2937",
}
ERR_CAPSIZE: float = 7.0

# Scatter / PR plots use slightly thinner error lines than bar plots —
# markers are smaller and a full 2 pt cap would dominate the dot.
ERR_KW_SCATTER: dict[str, float] = {
    "elinewidth": 1.6,
    "capthick":   1.6,
}
ERR_CAPSIZE_SCATTER: float = 5.0

# Light gray for scatter error bars so they fade behind the data point.
ERR_ECOLOR_SCATTER: str = "#94a3b8"


# ---------------------------------------------------------------------------
# The rcParams block. ``apply_pavlab_style()`` is idempotent and returns
# the dict it applied so a caller can audit / introspect.
# ---------------------------------------------------------------------------
_PAVLAB_RC: dict[str, object] = {
    # Typography — Helvetica/Arial sans-serif. No DejaVu Sans (not on
    # stock macOS Illustrator — would trigger a font-missing dialog).
    "font.family":        ["Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
    "font.size":          13,
    "axes.titlesize":     14,
    "axes.titleweight":   "semibold",
    "axes.titlepad":      14,
    "axes.labelsize":     12.5,
    "axes.labelweight":   "regular",

    # Spines + ticks — clean / modern; top + right hidden.
    "axes.spines.top":    False,
    "axes.spines.right":  False,

    # Stroke weights — bumped from matplotlib defaults (~0.8) to 2.0 so
    # the spines / ticks / bar edges survive reduction at journal
    # column-width and stay legible when the EPS is opened in
    # Illustrator. The previous 1.2-pt strokes looked too fine in EPS.
    "axes.linewidth":     2.0,
    "axes.edgecolor":     "#1f2937",
    "axes.labelcolor":    "#0f172a",

    "xtick.color":        "#1f2937",
    "ytick.color":        "#1f2937",
    "xtick.labelsize":    11.5,
    "ytick.labelsize":    11.5,
    "xtick.major.size":   6,
    "ytick.major.size":   6,
    "xtick.major.width":  2.0,
    "ytick.major.width":  2.0,
    "xtick.direction":    "out",
    "ytick.direction":    "out",
    "ytick.major.pad":    4,

    # Default to no grid; callers opt in with ax.grid(axis="y", ...).
    "axes.grid":          False,

    # Line / patch defaults — for plots that don't override per-call.
    "lines.linewidth":    2.2,
    "patch.linewidth":    1.8,

    # Output. svg.fonttype=none keeps text as text (editable in
    # Illustrator/Inkscape). ps.fonttype=42 embeds TrueType in EPS so
    # text remains editable rather than being converted to Type 3
    # outlines.
    "figure.dpi":         120,
    "savefig.dpi":        300,
    "savefig.bbox":       "tight",
    "savefig.transparent":False,
    "svg.fonttype":       "none",
    "ps.fonttype":        42,
}


def apply_pavlab_style() -> dict:
    """Apply the lab's matplotlib style and return the rcParams dict.

    Idempotent — calling multiple times has the same effect as calling
    once. Returns a copy of the rcParams that were applied so the caller
    can audit them or merge with project-specific overrides."""
    mpl.rcParams.update(_PAVLAB_RC)
    return dict(_PAVLAB_RC)


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
def lighten(hex_color: str, frac: float = 0.55) -> str:
    """Blend a hex colour with white. ``frac`` is the white fraction:
    ``frac=0`` returns the input, ``frac=1`` returns pure white.

    Use as a print-safe substitute for ``alpha=`` on bar / scatter
    facecolour. EPS does not carry an alpha channel, so a pair of bars
    where one has ``alpha=0.55`` and the other has ``alpha=1.0`` will
    render identical-solid in Illustrator. Substituting a literal
    lightened RGB preserves the tonal split through the EPS round-trip
    *and* gives a wider visual difference on screen than alpha did.

    Common usage — paired light/dark bars:

        ax.bar(x_left,  y_a, color=[lighten(c, 0.55) for c in cols], ...)
        ax.bar(x_right, y_b, color=cols, ...)

    See `pavlab_barplot.paired_bars()` for the wrapped helper.
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"lighten expects a 6-digit hex colour, got {hex_color!r}")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = int(r + (255 - r) * frac)
    g = int(g + (255 - g) * frac)
    b = int(b + (255 - b) * frac)
    return f"#{r:02x}{g:02x}{b:02x}"


__all__ = [
    "apply_pavlab_style",
    "lighten",
    "ERR_KW",
    "ERR_CAPSIZE",
    "ERR_KW_SCATTER",
    "ERR_CAPSIZE_SCATTER",
    "ERR_ECOLOR_SCATTER",
]
