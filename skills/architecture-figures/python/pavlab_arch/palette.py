"""Pavlab figure palette — Tailwind 500/600/100 ladders.

The palette is fixed across the project per Paul's user-global
figure conventions (`~/.claude/CLAUDE.md` § Figures). Border /
emphasis colors at saturation 500-600; fill tints at 100-level.

Two specialty entries:
  - BAR_FACTOR / BAR_TAG: luminosity-balanced bar colors for
    quantitative gauges. The default ACCENT (blue-600, L*≈41) is
    too dark/saturated next to ACCENT_2 (emerald-500, L*≈65) —
    the blue dominates the eye at equal F1. BAR_FACTOR uses
    blue-400 (L*≈67) instead, paired with emerald-500.
  - CURATOR_OVERLAY: per-bar-color light variants for the
    curator-corrected overlay on perf_gauge.
"""

# Borders / emphasis (Tailwind 500-600)
ACCENT   = "#2563eb"  # blue-600    — primary
ACCENT_2 = "#10b981"  # emerald-500 — secondary / "good"
ACCENT_3 = "#f59e0b"  # amber-500   — tertiary / "warning"
ACCENT_4 = "#ef4444"  # red-500     — "bad" / heavy
ACCENT_5 = "#8b5cf6"  # violet-500  — ensemble / mixed

# Neutrals
DET      = "#cbd5e1"  # slate-300   — deterministic stage
GRID     = "#e5e7eb"  # gray-200    — gridlines, gauge backgrounds
TEXT     = "#1f2937"  # gray-800    — body text
SUBTLE   = "#6b7280"  # gray-500    — captions, axis ticks
SOFT_BG  = "#f9fafb"  # gray-50     — soft backgrounds

# Luminosity-balanced bar colors for perf_gauge.
BAR_FACTOR = "#60a5fa"   # blue-400, L*≈67 (peer of emerald-500)
BAR_TAG    = ACCENT_2    # emerald-500, L*≈65

# Curator-corrected overlay colors — match the underlying bar's hue.
CURATOR_OVERLAY = {
    BAR_FACTOR: "#bfdbfe",   # blue-200 over blue-400 raw
    BAR_TAG:    "#86efac",   # green-300 over emerald-500 raw
    ACCENT:     "#93c5fd",   # fallback when called with full-saturation
    ACCENT_2:   "#86efac",
}


# Tint map for box fills — pair each border color with its 100-level
# tint. Used by stage_box() to colour the inside softly without
# overpowering the text.
_TINT_MAP = {
    ACCENT:   "#dbeafe",  # blue-100
    ACCENT_2: "#d1fae5",  # emerald-100
    ACCENT_3: "#fef3c7",  # amber-100
    ACCENT_4: "#fee2e2",  # red-100
    ACCENT_5: "#ede9fe",  # violet-100
    DET:      "#f1f5f9",  # slate-100
}


def tint(hex_color: str) -> str:
    """Return the 100-level tint for a given border color, or a
    very soft gray if not in the map. Also resolves the warm pastel
    tints of the colour-blind-safe scientific palettes below.
    """
    if hex_color in _SCI_TINT:
        return _SCI_TINT[hex_color]
    return _TINT_MAP.get(hex_color, "#f9fafb")


# ---------------------------------------------------------------------------
# Colour-blind-safe scientific palettes — an OPTIONAL alternative to the flat
# ACCENT ladder, for journal / slide figures that must survive a projector
# AND greyscale. Both palettes below are deuteranopia- and protanopia-safe;
# pick one per figure. (This is the palette from the "Scientific Figure Style
# Guide" — a warm-paper base with two candidate colour directions.)
#
# Two well-known qualitative palettes ship whole, so you can pull as many
# distinct series as a figure needs — these are the reusable, standard sets:
#
#   OKABE_ITO — Okabe & Ito (2008), the de-facto scientific standard.
#               High contrast, confident on a projector.
#   TOL_MUTED — Paul Tol's "muted" qualitative scheme. Softer / desaturated,
#               reads gently on a printed page, still fully distinct.
# ---------------------------------------------------------------------------

# Okabe–Ito, in the canonical order. Names are the colours themselves.
OKABE_ITO = {
    "black":          "#000000",
    "orange":         "#E69F00",
    "sky_blue":       "#56B4E9",
    "bluish_green":   "#009E73",
    "yellow":         "#F0E442",
    "blue":           "#0072B2",
    "vermillion":     "#D55E00",
    "reddish_purple": "#CC79A7",
}

# Paul Tol "muted", in canonical order (+ a light grey for missing/other).
TOL_MUTED = {
    "indigo": "#332288",
    "cyan":   "#88CCEE",
    "teal":   "#44AA99",
    "green":  "#117733",
    "olive":  "#999933",
    "sand":   "#DDCC77",
    "rose":   "#CC6677",
    "wine":   "#882255",
    "purple": "#AA4499",
    "grey":   "#DDDDDD",
}

# Ordered lists — hand straight to a matplotlib prop_cycle or seaborn.
OKABE_ITO_CYCLE = [OKABE_ITO[k] for k in
                   ("blue", "bluish_green", "vermillion", "orange",
                    "sky_blue", "reddish_purple", "yellow", "black")]
TOL_MUTED_CYCLE = [TOL_MUTED[k] for k in
                   ("indigo", "teal", "rose", "sand",
                    "green", "cyan", "purple", "olive", "wine")]

# Warm-paper neutrals shared by both directions.
INK   = "#2A2926"   # near-black warm ink — text, axes, structural edges
PAPER = "#FBFAF6"   # warm paper — figure + axes facecolor
SCI_GRID = "#DED9CE"  # warm grid line (distinct from the flat-palette GRID)

# Two ready-made "directions" — a curated four-colour selection with a
# matched pastel *tint* for each (border/line/series solid + fill/panel
# tint). Use one when you want a small coordinated figure family rather than
# hand-picking from the full palettes above. Keys are colours, not roles —
# assign them to whatever your figure's categories are.
#
#   SCI_A · Okabe–Ito based — grey / green / blue / orange
#   SCI_B · Tol muted based — grey / teal  / blue / rose
SCI_A = {
    "grey":   ("#7A756B", "#EDEBE4"),
    "green":  ("#009E73", "#E0F0E9"),
    "blue":   ("#0072B2", "#DBE9F4"),
    "orange": ("#D55E00", "#FBE6DB"),
}
SCI_B = {
    "grey": ("#7A756B", "#EDEBE4"),
    "teal": ("#44AA99", "#E4F1EE"),
    "blue": ("#4477AA", "#E3EAF2"),
    "rose": ("#CC6677", "#F7E6E9"),
}
SCI_SCHEMES = {"A": SCI_A, "B": SCI_B}

# Solid-colour cycle order for each scheme (load-bearing hues first, neutral
# grey last) — matches the guide's prop_cycle.
_SCI_A_ORDER = ("blue", "green", "orange", "grey")
_SCI_B_ORDER = ("blue", "teal", "rose", "grey")
_SCI_CYCLE_ORDER = {"A": _SCI_A_ORDER, "B": _SCI_B_ORDER}

# solid -> tint, so tint() resolves the scheme fills too.
_SCI_TINT = {solid: t for scheme in SCI_SCHEMES.values()
             for (solid, t) in scheme.values()}


def sci_scheme(direction: str = "A") -> dict:
    """Return the curated scheme dict for direction ``"A"`` (Okabe–Ito) or
    ``"B"`` (Tol muted). Each value is a ``(solid, tint)`` pair.
    """
    key = str(direction).strip().upper()
    if key not in SCI_SCHEMES:
        raise ValueError(
            f"unknown scheme {direction!r}; expected 'A' (Okabe–Ito) "
            f"or 'B' (Tol muted)"
        )
    return SCI_SCHEMES[key]


def sci_cycle(direction: str = "A") -> list:
    """Ordered list of the scheme's four *solid* colours, for a prop_cycle."""
    key = str(direction).strip().upper()
    sch = sci_scheme(key)
    return [sch[name][0] for name in _SCI_CYCLE_ORDER[key]]


# ---------------------------------------------------------------------------
# Modern "card" palette — an OPTIONAL alternative to the flat ACCENT palette,
# for rounded-corner card figures with soft drop shadows (see
# primitives.card()). Each entry is a ``(fill, edge, text)`` triple: a soft
# tinted fill, a crisp saturated border, and a dark same-hue text colour so
# labels stay legible on the fill. Pair with primitives.card(...) +
# CARD_ARROW for the "modern architecture diagram" look.
#
# Actor convention mirrors the ACCENT palette:
#   CARD_LLM   indigo  — LLM / agent stage
#   CARD_DET   slate   — deterministic (Python, no model)
#   CARD_IO    teal    — I/O surface (inputs / outputs / curator-facing)
#   CARD_JUDGE violet  — strong-tier judge (Opus / extended thinking)
#   CARD_WARN  amber   — load-bearing asset / warning
#   CARD_BAD   red     — failure / recall / loop-back
CARD_LLM   = ("#E0E7FF", "#6366F1", "#1E1B4B")  # indigo-100 / 500 / 950
CARD_DET   = ("#F1F5F9", "#94A3B8", "#334155")  # slate-100  / 400 / 700
CARD_IO    = ("#CCFBF1", "#14B8A6", "#134E4A")  # teal-100   / 500 / 900
CARD_JUDGE = ("#F3E8FF", "#A855F7", "#581C87")  # violet-100 / 500 / 900
CARD_WARN  = ("#FEF3C7", "#F59E0B", "#78350F")  # amber-100  / 500 / 900
CARD_BAD   = ("#FEE2E2", "#EF4444", "#7F1D1D")  # red-100    / 500 / 900

CARD_ARROW = "#94A3B8"   # slate-400 connectors
CARD_TEXT  = "#0F172A"   # slate-900 titles
CARD_SUBTLE = "#64748B"  # slate-500 captions / notes

# name -> triple, for callers that prefer to look up by role string.
CARD_PALETTE = {
    "llm": CARD_LLM, "deterministic": CARD_DET, "io": CARD_IO,
    "judge": CARD_JUDGE, "warn": CARD_WARN, "bad": CARD_BAD,
}
