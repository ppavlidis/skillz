"""Software stack figure — gemma-curation-ui ecosystem.

A layered software / hardware stack figure: components live in
horizontal tier bands stacked vertically, with arrows showing
inter-tier flow labeled by protocol. Demonstrates the skill in a
domain other than pipeline / lifecycle / pathway / Gantt — the
**stack diagram** pattern is its own family, common in onboarding
docs, architecture decision records, and system overviews.

Tiers (top to bottom):

  - **Client**     — the browser
  - **Frontend**   — two React apps that share a stack
  - **Services**   — a Python agent service + a Java REST service,
                     plus the external LLM API
  - **Storage**    — the persistence tier (databases + vector index)

Style conventions established (and reusable for any stack figure):

  - **Tier bands** are soft ``SOFT_BG`` rounded rectangles with the
    tier name left-margin italic — exactly the same pattern as the
    cross-cutting container in the lifecycle figure.

  - **Service / app boxes** are rectangles with the *tech stack*
    spelled out in muted text below the bolded component name. The
    box's border colour encodes the runtime family:
      blue (ACCENT)   — frontend / JavaScript
      amber (ACCENT_3)— backend service
      violet (ACCENT_5) — external third party

  - **Data stores are pills** (``oval``), not rectangles. The shape
    distinguishes "data sitting" from "service running". Pill border
    colour encodes role:
      green (ACCENT_2)  — durable / production data
      violet (ACCENT_5) — vector / ML-adjacent data

  - **External services** (LLM API) sit at the edge of the
    services tier with a **dashed border**, signalling "out-of-band,
    third-party — we call it, we don't own it."

  - **Inter-tier arrows are labeled** with the wire protocol
    (``HTTPS``, ``JSON``, ``JDBC``, etc.) via ``labeled_arrow``.
    Default styling (italic, ACCENT, 7pt) keeps the labels quiet —
    they sit next to the arrow but don't visually compete with the
    boxes.

Tech stack drawn from ``~/Dev/gemma-curation-ui`` and the related
``gemma-curation-agents`` (Python) + Gemma (Java) repos. Some
artistic license: the exact set of dependencies is illustrative, not
exhaustive.

Outputs:
    software_stack_example.svg
    software_stack_example.png
"""
from __future__ import annotations
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

_SKILL = Path(__file__).resolve().parents[1] / "python"
sys.path.insert(0, str(_SKILL))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

from pavlab_arch import palette as P  # noqa: E402
from pavlab_arch.layout import figure, svg_safe  # noqa: E402
from pavlab_arch.primitives import (  # noqa: E402
    box, oval, cylinder, container, labeled_arrow,
)
from pavlab_arch.style import apply_rcparams  # noqa: E402


# ---------------------------------------------------------------------------
# Local helpers — specific to stack diagrams, kept inline so the example
# is self-contained.
# ---------------------------------------------------------------------------

def tier_band(ax, y_lo: float, y_hi: float,
              x_lo: float, x_hi: float, label: str) -> None:
    """Soft-background container for one stack tier + left-margin italic label."""
    ax.add_patch(FancyBboxPatch(
        (x_lo, y_lo), x_hi - x_lo, y_hi - y_lo,
        boxstyle="round,pad=0,rounding_size=0.04",
        linewidth=0, edgecolor="none", facecolor=P.SOFT_BG, zorder=1,
    ))
    ax.text(x_lo - 1.0, (y_lo + y_hi) / 2, label,
            ha="right", va="center",
            color=P.SUBTLE, fontsize=9.5, style="italic")


def tech_box(ax, x: float, y: float, w: float, h: float,
             title: str, tech_lines, color: str,
             *, dashed: bool = False) -> tuple[float, float, float, float]:
    """Rectangle with bold title + muted multi-line tech stack list.

    Returns ``(x, y, w, h)`` so the caller can anchor arrows to the
    box's edges.
    """
    linestyle = (0, (3, 2)) if dashed else "solid"
    box(ax, x, y, w, h,
        fc=P.tint(color), ec=color, lw=1.6, radius=0.10,
        linestyle=linestyle)
    # Title in upper portion of the box.
    ax.text(x + w / 2, y + h * 0.74, title,
            ha="center", va="center",
            color=P.TEXT, fontsize=10.0, fontweight="bold")
    # Tech lines stacked below.
    if isinstance(tech_lines, str):
        tech_lines = [tech_lines]
    line_pitch = 1.55
    start_y = y + h * 0.42
    for i, line in enumerate(tech_lines):
        ax.text(x + w / 2, start_y - i * line_pitch, line,
                ha="center", va="center",
                color=P.SUBTLE, fontsize=9.0)
    return (x, y, w, h)


def data_pill(ax, cx: float, cy: float, w: float, h: float,
              name: str, sub: str, color: str
              ) -> tuple[float, float, float, float]:
    """Pill-shaped data store with bold name + italic subtitle.

    Use for "data sitting" — vector indexes, file-based stores, caches.
    For relational / production databases see ``cylinder`` below.
    """
    oval(ax, cx, cy, w, h, fc=P.tint(color), ec=color, lw=1.4)
    ax.text(cx, cy + 1.0, name,
            ha="center", va="center",
            color=P.TEXT, fontsize=11.0, fontweight="bold")
    ax.text(cx, cy - 1.4, sub,
            ha="center", va="center",
            color=P.SUBTLE, fontsize=8.5, style="italic")
    return (cx - w / 2, cy - h / 2, w, h)


# ---------------------------------------------------------------------------
# Geometry — pinned at the top so the layout is easy to tweak.
# ---------------------------------------------------------------------------

BAND_X_LO = 11.0
BAND_X_HI = 99.0

# Tier y-bands: (y_lo, y_hi, label).
CLIENT_BAND   = (79.0, 89.0)
FRONTEND_BAND = (60.0, 74.0)
SERVICES_BAND = (37.0, 56.0)
STORAGE_BAND  = (15.0, 32.0)

# Helpful y midpoints inside each band.
def _mid(band): return (band[0] + band[1]) / 2


def build_stack_figure() -> tuple[Path, Path]:
    apply_rcparams()
    fig, ax = figure(shape="slide")  # 13.33 x 7.5

    # ---- Title ----
    ax.text(50, 96, "gemma-curation-ui — software stack",
            ha="center", va="top",
            color=P.TEXT, fontsize=17, fontweight="bold")
    ax.text(50, 92, "two React apps over two backends, with shared infrastructure",
            ha="center", va="top",
            color=P.SUBTLE, fontsize=11.0)

    # ---- Tier bands (background first so boxes overlay) ----
    tier_band(ax, *CLIENT_BAND,   BAND_X_LO, BAND_X_HI, "Client")
    tier_band(ax, *FRONTEND_BAND, BAND_X_LO, BAND_X_HI, "Frontend")
    tier_band(ax, *SERVICES_BAND, BAND_X_LO, BAND_X_HI, "Services")
    tier_band(ax, *STORAGE_BAND,  BAND_X_LO, BAND_X_HI, "Storage")

    # ---- Client tier: a single browser box, centred ----
    tech_box(ax, 42, 80.5, 16, 7, "Browser",
             ["any modern engine"], P.DET)

    # ---- Frontend tier ----
    # Curation UI aligned over Curation agents; Browser UI over Gemma REST.
    tech_box(ax, 15, 61.5, 28, 11, "Curation UI",
             ["React 18 · TypeScript 5.6 · Vite 5",
              "TanStack Query/Router · Tailwind"],
             P.ACCENT)
    tech_box(ax, 58, 61.5, 28, 11, "Browser UI (GemBrow)",
             ["React 18 · TypeScript 5.6 · Vite 5",
              "TanStack Query/Router · Tailwind"],
             P.ACCENT)

    # ---- Services tier — LLM API placed ADJACENT to Curation agents
    # rather than across the row past Gemma REST. Layout-first principle:
    # if a connection would have to arc over another box, move the target
    # closer to the source instead.
    tech_box(ax, 13, 39.5, 22, 14, "Curation agents",
             ["Python 3.10+ · FastAPI",
              "Pydantic · LLM SDK",
              "biolit · gspread · httpx"],
             P.ACCENT_3)
    tech_box(ax, 37, 41.5, 14, 10, "LLM API",
             ["managed inference",
              "tool use · streaming",
              "external"],
             P.ACCENT_5, dashed=True)
    tech_box(ax, 58, 39.5, 28, 14, "Gemma REST",
             ["Java 17 · Spring 6.2 · Spring Boot",
              "Spring Security 6.5 · Hibernate 6.6",
              "JCache · HikariCP · Maven"],
             P.ACCENT_3)

    # ---- Storage tier — pills for caches / vector indexes; cylinder
    # for the canonical "production database" (MySQL). The shape change
    # tells the reader at a glance which store is the durable system-of-
    # record vs. an auxiliary index or test fixture.
    data_pill(ax, 21, 23.5, 14, 7,
              "SQLite", "curation mock", P.ACCENT_2)
    data_pill(ax, 38, 23.5, 14, 7,
              "FAISS", "vector / embeddings", P.ACCENT_5)
    cylinder(ax, 64, 23.5, 12, 8,
             ec=P.ACCENT_2, fc=P.tint(P.ACCENT_2), lw=1.4,
             text="MySQL", sub="Gemma production",
             fontsize=9.0, sub_color=P.SUBTLE)
    data_pill(ax, 84, 23.5, 14, 7,
              "H2", "test fixtures", P.ACCENT_2)

    # ---- Arrows — inter-tier flows are BIDIRECTIONAL (request +
    # response), so use ``style="<|-|>"`` for filled arrowheads at both
    # ends. Single-direction arrows are reserved for purely-emit and
    # purely-consume relationships (e.g. write-only sinks).

    # Browser  <->  Frontend apps (HTTPS request/response)
    labeled_arrow(ax,
                  47, 80.5, 28, 72.5,
                  "HTTPS",
                  style="<|-|>",
                  shrinkA=2, shrinkB=2,
                  label_side=-1.0, label_along=0.55,
                  label_color=P.SUBTLE, label_fontsize=8.5)
    labeled_arrow(ax,
                  53, 80.5, 72, 72.5,
                  "HTTPS",
                  style="<|-|>",
                  shrinkA=2, shrinkB=2,
                  label_side=1.0, label_along=0.55,
                  label_color=P.SUBTLE, label_fontsize=8.5)

    # Curation UI  <->  Curation agents
    labeled_arrow(ax,
                  24, 61.5, 24, 53.5,
                  "JSON  ·  /propose, /audit",
                  style="<|-|>",
                  shrinkA=1, shrinkB=1,
                  label_side=12.5, label_along=0.5,
                  label_color=P.SUBTLE, label_fontsize=8.5)
    # Browser UI  <->  Gemma REST
    labeled_arrow(ax,
                  72, 61.5, 72, 53.5,
                  "JSON  ·  /rest",
                  style="<|-|>",
                  shrinkA=1, shrinkB=1,
                  label_side=-8.0, label_along=0.5,
                  label_color=P.SUBTLE, label_fontsize=8.5)

    # Curation agents  <->  LLM API (adjacent — no obstacle to arc over)
    labeled_arrow(ax,
                  35, 46.5, 37, 46.5,
                  "HTTPS",
                  style="<|-|>",
                  shrinkA=1, shrinkB=1,
                  label_side=1.4, label_along=0.5,
                  label_color=P.SUBTLE, label_fontsize=8.5)

    # Curation agents -> SQLite
    labeled_arrow(ax,
                  21, 39.5, 21, 27,
                  "file",
                  style="<|-|>",
                  shrinkA=1, shrinkB=2,
                  label_side=2.5, label_along=0.5,
                  label_color=P.SUBTLE, label_fontsize=8.5)
    # Curation agents -> FAISS
    labeled_arrow(ax,
                  29, 39.5, 38, 27,
                  "mmap",
                  style="<|-|>",
                  shrinkA=1, shrinkB=2,
                  label_side=-2.0, label_along=0.5,
                  label_color=P.SUBTLE, label_fontsize=8.5)
    # Gemma REST  <->  MySQL
    labeled_arrow(ax,
                  64, 39.5, 64, 27.5,
                  "JDBC",
                  style="<|-|>",
                  shrinkA=1, shrinkB=2,
                  label_side=-2.5, label_along=0.5,
                  label_color=P.SUBTLE, label_fontsize=8.5)
    # Gemma REST -> H2 (test only — dashed line signals "test path")
    labeled_arrow(ax,
                  78, 39.5, 84, 27,
                  "JDBC (test)",
                  style="<|-|>",
                  shrinkA=1, shrinkB=2,
                  linestyle=(0, (4, 2.5)),
                  label_side=-2.0, label_along=0.5,
                  label_color=P.SUBTLE, label_fontsize=8.5)

    # ---- Source caption ----
    ax.text(99, 1, "source: examples/software_stack_example.py",
            ha="right", va="bottom",
            color=P.SUBTLE, fontsize=8.5)

    svg_safe(ax)
    plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
    out = Path(__file__).resolve().parent
    svg_path = out / "software_stack_example.svg"
    png_path = out / "software_stack_example.png"
    fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return svg_path, png_path


def main() -> int:
    svg, png = build_stack_figure()
    print(f"wrote {svg}")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
