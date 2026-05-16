# Color palettes used by pavlab_heatmap() and other plotting helpers.
#
# Sequential ("black body") palette:
#   black_body_palette()             black -> red -> orange -> yellow -> white
#
# Divergent palettes — all anchored at BLACK in the middle so near-zero cells
# look "off" and the eye is drawn to genuinely large +/- cells. Named so users
# can opt into the look they want; the default `divergent_palette()` is the
# one the lab settled on after side-by-side comparison.
#
#   divergent_palette()              DEFAULT: amber-orange / sky-blue
#   divergent_palette_rdbu()         Brewer-RdBu mid-range red / blue (classic feel)
#   divergent_palette_spectral()     Spectral-mid: vivid red-orange / vivid blue
#   divergent_palette_cyan_yellow()  bright cyan / bright yellow (high pop)
#   divergent_palette_blue_yellow()  classic blue / yellow (asymmetric on purpose)

# ---- Sequential ---------------------------------------------------------

#' Sequential "black body" palette (black -> white through red/orange/yellow).
#' Luminance-monotonic so it reads as low->high even in greyscale and is
#' reasonably color-blind-safe.
#' @param n Number of interpolated colors. Default 256.
#' @return Character vector of `n` hex colors.
black_body_palette <- function(n = 256) {
  grDevices::colorRampPalette(c(
    "#000000",  # black
    "#3a0303",  # very dark red
    "#7a0a0a",  # dark red
    "#c81e1e",  # red
    "#ff6a13",  # orange
    "#ffd11a",  # yellow
    "#ffffff"   # white
  ))(n)
}

# ---- Divergent ----------------------------------------------------------

# All divergent palettes share the same construction:
#   bright_left  ->  dim_left  ->  BLACK  ->  dim_right  ->  bright_right
# Smooth luminance valley with black at zero. The "dim" steps prevent a
# bottleneck around the middle that would otherwise make most of the gradient
# look near-black on dim screens.

.divergent <- function(left, dim_left, dim_right, right, n) {
  if (n %% 2 == 0) n <- n + 1   # force odd so the midpoint is exactly one color
  grDevices::colorRampPalette(c(left, dim_left, "#000000", dim_right, right))(n)
}

#' DEFAULT divergent palette: amber-orange / black / sky-blue.
#'
#' Settled on after side-by-side comparison ("Paul-approved"). Bright at both
#' ends so even moderate +/- values pop on a dim screen; smooth dim valley
#' into pure black at zero; matched luminance on the two sides so neither
#' dominates; no near-white extremes that would lose dynamic range.
#'
#' @param n Number of interpolated colors. Default 256 (made odd internally).
divergent_palette <- function(n = 256) {
  .divergent(left = "#FFA000",      # amber-orange
             dim_left = "#7F5000",
             dim_right = "#19607F",
             right = "#33C0FF",     # sky-blue
             n = n)
}

#' Classic-feel divergent palette: Brewer-RdBu mid-range red / blue / black.
#' Closer to what most papers use; slightly more muted than the default.
divergent_palette_rdbu <- function(n = 256) {
  .divergent(left = "#D6604D",       # Brewer RdBu mid-warm
             dim_left = "#6B3027",
             dim_right = "#21495F",
             right = "#4393C3",       # Brewer RdBu mid-cool
             n = n)
}

#' Spectral-mid divergent palette: vivid red-orange / black / vivid cool blue.
divergent_palette_spectral <- function(n = 256) {
  .divergent(left = "#FF7050",
             dim_left = "#7F3828",
             dim_right = "#356072",
             right = "#6FC1E5",
             n = n)
}

#' Cyan / black / yellow divergent palette.
#' High pop. Cyan luminance balances yellow's brightness. Some find the
#' colors too "primary" / not paper-stylish; use one of the others if so.
divergent_palette_cyan_yellow <- function(n = 256) {
  .divergent(left = "#FFFF00",       # yellow
             dim_left = "#3F3F00",
             dim_right = "#003F3F",
             right = "#00FFFF",       # cyan
             n = n)
}

#' Classic blue / black / yellow divergent palette.
#' Asymmetric on purpose — pure blue is much darker than pure yellow, so the
#' yellow side will visually dominate. Use only if you specifically want this
#' look.
divergent_palette_blue_yellow <- function(n = 256) {
  .divergent(left = "#ffff1a",       # yellow
             dim_left = "#3a3a00",
             dim_right = "#000040",
             right = "#1a2bff",       # blue
             n = n)
}
