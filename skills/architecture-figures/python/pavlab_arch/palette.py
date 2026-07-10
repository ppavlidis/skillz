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
    very soft gray if not in the map.
    """
    return _TINT_MAP.get(hex_color, "#f9fafb")


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
