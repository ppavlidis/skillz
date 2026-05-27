#!/usr/bin/env python3
"""Python demo of pavlab_scatter.

Run from skills/plotting/:
    .venv/bin/python examples/scatter_demo.py

Outputs five PNGs to <tempdir>/pavlab_scatter_demo_py/.
"""

from __future__ import annotations

import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from pavlab_scatter import pavlab_scatter  # noqa: E402

rng = np.random.default_rng(42)
out_dir = Path(tempfile.gettempdir()) / "pavlab_scatter_demo_py"
out_dir.mkdir(parents=True, exist_ok=True)


# ---- 1. Basic: two positive arrays, origin at 0 -------------------------
x1 = rng.uniform(0.5, 8.0, 80)
y1 = x1 * 0.9 + rng.normal(0, 0.8, 80)
y1 = np.clip(y1, 0.1, None)

p1 = out_dir / "01_basic.png"
pavlab_scatter(x1, y1, xlabel="Replicate 1", ylabel="Replicate 2",
               title="Basic scatter", filename=str(p1), figsize=(5, 5))
print(f"wrote {p1}")


# ---- 2. Log2-scaled replicate comparison (expression data) ---------------
# Simulate TPM values: mostly low, some high — classic log-scale scenario.
tpm1 = rng.lognormal(mean=2, sigma=2, size=200)
tpm2 = tpm1 * rng.lognormal(mean=0, sigma=0.3, size=200)

p2 = out_dir / "02_log2_replicates.png"
with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)  # suppress log-suggestion (we're applying it)
    pavlab_scatter(tpm1, tpm2,
                   xlabel="TPM replicate 1", ylabel="TPM replicate 2",
                   log_x="log2", log_y="log2", pseudocount=1.0,
                   title="Replicate comparison (log₂ TPM+1)",
                   filename=str(p2), figsize=(5, 5))
print(f"wrote {p2}")


# ---- 3. Categorical color: PCA-style plot --------------------------------
n_cells = 120
pca1 = rng.standard_normal(n_cells)
pca2 = rng.standard_normal(n_cells)
cell_types = (["Neuron"] * 40 + ["Astrocyte"] * 40 + ["Microglia"] * 40)

p3 = out_dir / "03_categorical_color.png"
with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    pavlab_scatter(pca1, pca2, color=cell_types,
                   xlabel="PC1", ylabel="PC2",
                   title="PCA — cell types",
                   origin_zero=False,
                   filename=str(p3), figsize=(5.5, 5))
print(f"wrote {p3}")


# ---- 4. Medium N: semi-transparent circles --------------------------------
n_med = 2_000
x4 = rng.uniform(1, 10, n_med)
y4 = x4 + rng.normal(0, 1.5, n_med)
y4 = np.clip(y4, 0.1, None)

p4 = out_dir / "04_medium_n_alpha.png"
pavlab_scatter(x4, y4, xlabel="X", ylabel="Y",
               title=f"Medium N = {n_med}: semi-transparent",
               filename=str(p4), figsize=(5, 5))
print(f"wrote {p4}")


# ---- 5. Large N: hexbin density ------------------------------------------
n_big = 30_000
x5 = rng.standard_normal(n_big)
y5 = x5 * 0.7 + rng.standard_normal(n_big) * 0.7

p5 = out_dir / "05_large_n_density.png"
with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    pavlab_scatter(x5, y5, xlabel="X", ylabel="Y",
                   title=f"Large N = {n_big:,}: hexbin density",
                   origin_zero=False,
                   filename=str(p5), figsize=(5.5, 5))
print(f"wrote {p5}")


print(f"\nDemo complete. Outputs in: {out_dir}")
