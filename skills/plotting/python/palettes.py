"""Color palettes — Python port of R/palettes.R.

All divergent palettes share construction `[bright_left, dim_left, BLACK,
dim_right, bright_right]` and return a matplotlib LinearSegmentedColormap
with `bad` (NaN) set to lightgrey. Returned colormaps are drop-in for
seaborn.heatmap (`cmap=...`) and matplotlib (`pcolormesh`, `imshow`).

Hex anchors are byte-for-byte identical to the R versions so figures
produced in either language match.
"""

from __future__ import annotations

from matplotlib.colors import LinearSegmentedColormap

_BAD = "#cccccc"   # matches R's grey80 used for NA


def _make_cmap(name: str, hex_colors: list[str], n: int = 256) -> LinearSegmentedColormap:
    cmap = LinearSegmentedColormap.from_list(name, hex_colors, N=n)
    cmap.set_bad(_BAD)
    return cmap


# ---- Sequential ---------------------------------------------------------


def black_body_palette(n: int = 256) -> LinearSegmentedColormap:
    """Sequential "black body" colormap: black -> red -> orange -> yellow -> white.

    Luminance-monotonic; reads as low->high even in greyscale.
    """
    return _make_cmap(
        "pavlab_blackbody",
        [
            "#000000",  # black
            "#3a0303",  # very dark red
            "#7a0a0a",  # dark red
            "#c81e1e",  # red
            "#ff6a13",  # orange
            "#ffd11a",  # yellow
            "#ffffff",  # white
        ],
        n=n,
    )


# ---- Divergent ----------------------------------------------------------


def _divergent(name: str, left: str, dim_left: str, dim_right: str, right: str,
               n: int = 256) -> LinearSegmentedColormap:
    return _make_cmap(name, [left, dim_left, "#000000", dim_right, right], n=n)


def divergent_palette(n: int = 256) -> LinearSegmentedColormap:
    """DEFAULT divergent palette: amber-orange / BLACK / sky-blue.

    Settled on after side-by-side comparison ("Paul-approved"). Bright at
    both ends so even moderate values pop on a dim screen; smooth dim
    valley into pure black at zero; matched luminance on the two sides;
    no near-white extremes that would lose dynamic range.
    """
    return _divergent(
        "pavlab_divergent",
        left="#FFA000",
        dim_left="#7F5000",
        dim_right="#19607F",
        right="#33C0FF",
        n=n,
    )


def divergent_palette_rdbu(n: int = 256) -> LinearSegmentedColormap:
    """Brewer-RdBu mid-range red / black / blue. Classic-paper feel."""
    return _divergent(
        "pavlab_rdbu",
        left="#D6604D",
        dim_left="#6B3027",
        dim_right="#21495F",
        right="#4393C3",
        n=n,
    )


def divergent_palette_spectral(n: int = 256) -> LinearSegmentedColormap:
    """Spectral-mid divergent: vivid red-orange / black / vivid cool blue."""
    return _divergent(
        "pavlab_spectral",
        left="#FF7050",
        dim_left="#7F3828",
        dim_right="#356072",
        right="#6FC1E5",
        n=n,
    )


def divergent_palette_cyan_yellow(n: int = 256) -> LinearSegmentedColormap:
    """Cyan / black / yellow divergent. High pop; primary colors."""
    return _divergent(
        "pavlab_cyan_yellow",
        left="#FFFF00",
        dim_left="#3F3F00",
        dim_right="#003F3F",
        right="#00FFFF",
        n=n,
    )


def divergent_palette_blue_yellow(n: int = 256) -> LinearSegmentedColormap:
    """Classic blue / black / yellow divergent. Asymmetric on purpose."""
    return _divergent(
        "pavlab_blue_yellow",
        left="#ffff1a",
        dim_left="#3a3a00",
        dim_right="#000040",
        right="#1a2bff",
        n=n,
    )
