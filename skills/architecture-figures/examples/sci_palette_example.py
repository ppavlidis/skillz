#!/usr/bin/env python3
"""Colour-blind-safe scientific palettes — showcase + demo charts.

Renders, for BOTH candidate colour directions:

  - swatch panels for the two full standard palettes (Okabe–Ito, Tol muted)
  - the two curated four-colour *schemes* (solid over its matched tint)
  - a grouped bar chart and a scatter, on the warm-paper base, so you can
    see the palette on real data (not just chips)

and writes a self-contained ``sci_palette_index.html`` that inlines every
SVG so the whole showcase opens in one file.

Run:  python examples/sci_palette_example.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.style import apply_sci_rcparams, display_title  # noqa: E402
from pavlab_arch.layout import svg_safe  # noqa: E402

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Swatch panels — the full standard palettes.
# ---------------------------------------------------------------------------

def _swatch_panel(title, mapping, path):
    """One row of labelled chips for a full palette (name + hex under each)."""
    apply_sci_rcparams("A")
    n = len(mapping)
    fig, ax = plt.subplots(figsize=(0.6 + 1.15 * n, 2.0))
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    ax.axis("off")
    display_title(ax, title, loc="left", fontsize=13, color=P.INK, pad=10)
    for i, (name, hex_) in enumerate(mapping.items()):
        ax.add_patch(FancyBboxPatch(
            (i + 0.08, 0.42), 0.84, 0.42,
            boxstyle="round,pad=0,rounding_size=0.04",
            facecolor=hex_, edgecolor=P.INK, linewidth=0.6))
        ax.text(i + 0.5, 0.32, name.replace("_", " "),
                ha="center", va="top", fontsize=8.5, color=P.INK)
        ax.text(i + 0.5, 0.20, hex_.upper(),
                ha="center", va="top", fontsize=7.5, color=P.SUBTLE,
                family="monospace")
    fig.tight_layout()
    svg_safe(ax)
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _scheme_panel(path):
    """The two curated schemes A + B — each a column of solid-over-tint pairs."""
    apply_sci_rcparams("A")
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.1))
    for ax, key in zip(axes, ("A", "B")):
        sch = P.sci_scheme(key)
        ax.set_xlim(0, 6)
        ax.set_ylim(0, len(sch) + 0.6)
        ax.axis("off")
        nm = "Okabe–Ito" if key == "A" else "Tol muted"
        display_title(ax, f"Scheme {key} · {nm}", loc="left", fontsize=12,
                      color=P.INK, pad=8)
        for j, (name, (solid, tint)) in enumerate(reversed(list(sch.items()))):
            y = j + 0.3
            # tint fill (panel) with the solid border (line/series).
            ax.add_patch(FancyBboxPatch(
                (0.1, y), 2.3, 0.7,
                boxstyle="round,pad=0,rounding_size=0.04",
                facecolor=tint, edgecolor=solid, linewidth=2.0))
            ax.text(1.25, y + 0.35, name, ha="center", va="center",
                    fontsize=9, color=P.INK, fontweight="bold")
            ax.text(2.7, y + 0.35,
                    f"{solid.upper()}  ·  {tint.upper()}",
                    ha="left", va="center", fontsize=8, color=P.SUBTLE,
                    family="monospace")
    fig.tight_layout()
    svg_safe(axes[0]); svg_safe(axes[1])
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Demo charts on the warm-paper base — palette on real data.
# ---------------------------------------------------------------------------

def _demo_charts(direction, path):
    apply_sci_rcparams(direction)
    cyc = P.sci_cycle(direction)
    fig, (axb, axs) = plt.subplots(1, 2, figsize=(9.5, 3.4))

    # grouped bar — four categories × three groups
    groups = ["Batch 1", "Batch 2", "Batch 3"]
    cats = ["alpha", "beta", "gamma", "delta"]
    vals = np.array([[0.62, 0.71, 0.66],
                     [0.48, 0.55, 0.52],
                     [0.80, 0.74, 0.78],
                     [0.35, 0.41, 0.39]])
    xw = np.arange(len(groups))
    bw = 0.2
    for i, cat in enumerate(cats):
        axb.bar(xw + (i - 1.5) * bw, vals[i], bw, label=cat,
                color=cyc[i], edgecolor=P.INK, linewidth=0.4)
    axb.set_xticks(xw); axb.set_xticklabels(groups)
    axb.set_ylabel("score")                 # axis label stays Helvetica
    display_title(axb, "Grouped bar", loc="left")
    axb.legend(frameon=False, fontsize=8, ncol=2)
    axb.yaxis.grid(True); axb.xaxis.grid(False)

    # scatter — four clusters
    rng = np.random.default_rng(7)
    for i in range(4):
        cx, cy = rng.uniform(0.2, 0.8, 2)
        xs = rng.normal(cx, 0.06, 40)
        ys = rng.normal(cy, 0.06, 40)
        axs.scatter(xs, ys, s=22, color=cyc[i], edgecolor="white",
                    linewidth=0.3, alpha=0.9, label=f"cluster {i+1}")
    display_title(axs, "Scatter", loc="left")
    axs.set_xlabel("dim 1"); axs.set_ylabel("dim 2")   # axis labels Helvetica
    axs.legend(frameon=False, fontsize=8, ncol=2)
    axs.grid(True)

    nm = "Okabe–Ito" if direction == "A" else "Tol muted"
    display_title(fig, f"Direction {direction} · {nm}", x=0.02, ha="left",
                  fontsize=13, color=P.INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    svg_safe(axb); svg_safe(axs)
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------

def _write_index(svgs, out):
    """Self-contained HTML inlining every SVG (order preserved)."""
    blocks = []
    for caption, path in svgs:
        svg = Path(path).read_text()
        # strip the xml prolog so it embeds inline cleanly
        if svg.lstrip().startswith("<?xml"):
            svg = svg[svg.index("?>") + 2:]
        blocks.append(
            f'<figure><figcaption>{caption}</figcaption>'
            f'<div class="fig">{svg}</div></figure>'
        )
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>Scientific figure palettes</title>
<style>
  body {{ background:#FBFAF6; color:#2A2926; margin:0;
         font:15px/1.5 Helvetica, Arial, sans-serif; }}
  main {{ max-width:1000px; margin:0 auto; padding:32px 24px 80px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }}
  p.lede {{ color:#6b7280; margin:0 0 28px; max-width:60ch; }}
  figure {{ margin:0 0 34px; }}
  figcaption {{ font-size:12px; letter-spacing:.06em; text-transform:uppercase;
                color:#6b7280; margin:0 0 8px; }}
  .fig {{ background:#FBFAF6; border:1px solid #DED9CE; border-radius:10px;
          padding:14px; overflow-x:auto; }}
  .fig svg {{ max-width:100%; height:auto; display:block; margin:0 auto; }}
</style>
<main>
  <h1>Colour-blind-safe scientific palettes</h1>
  <p class="lede">Two candidate colour directions on a warm-paper base, both
  deuteranopia- and protanopia-safe. A · Okabe–Ito is the scientific standard
  (confident on a projector); B · Tol muted reads gently in print. Pick one
  per figure. Regenerated by <code>examples/sci_palette_example.py</code>.</p>
  {''.join(blocks)}
</main>
"""
    Path(out).write_text(html)


def main():
    swI = HERE / "sci_okabe_ito.svg"
    swT = HERE / "sci_tol_muted.svg"
    scheme = HERE / "sci_schemes.svg"
    demoA = HERE / "sci_demo_A.svg"
    demoB = HERE / "sci_demo_B.svg"

    _swatch_panel("Okabe–Ito — the scientific standard (8 colours)",
                  P.OKABE_ITO, swI)
    _swatch_panel("Paul Tol “muted” — softer, print-friendly (9 + grey)",
                  P.TOL_MUTED, swT)
    _scheme_panel(scheme)
    _demo_charts("A", demoA)
    _demo_charts("B", demoB)

    index = HERE / "sci_palette_index.html"
    _write_index([
        ("Full palette · Okabe–Ito", swI),
        ("Full palette · Tol muted", swT),
        ("Curated schemes · solid over tint", scheme),
        ("Demo · Direction A on warm paper", demoA),
        ("Demo · Direction B on warm paper", demoB),
    ], index)
    print(f"wrote 5 SVGs + {index.name}")


if __name__ == "__main__":
    main()
