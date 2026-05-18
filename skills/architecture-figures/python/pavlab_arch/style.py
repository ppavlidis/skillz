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
        "font.family": ["Helvetica", "Arial", "DejaVu Sans"],
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
