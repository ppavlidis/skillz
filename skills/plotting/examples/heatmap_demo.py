#!/usr/bin/env python3
"""Python demo of pavlab_heatmap. Mirrors examples/heatmap_demo.R so the
outputs are directly comparable side-by-side.

Run from skills/plotting/:
    .venv/bin/python examples/heatmap_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow `from python.pavlab_heatmap import ...` when run from the skill root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from pavlab_heatmap import pavlab_heatmap  # noqa: E402

rng = np.random.default_rng(42)
out_dir = Path("/tmp/pavlab_heatmap_demo_py")
out_dir.mkdir(parents=True, exist_ok=True)

# ---- 1. Expression heatmap: 20 genes x 12 samples, planted block signal ----
n_genes, n_samples = 20, 12
expr = pd.DataFrame(
    rng.standard_normal((n_genes, n_samples)),
    index=[f"Gene{i+1}" for i in range(n_genes)],
    columns=[f"S{i+1}" for i in range(n_samples)],
)
expr.iloc[:5, :6] += 2.5
expr.iloc[:5, 6:] -= 2.5

p1 = out_dir / "01_expression.png"
pavlab_heatmap(expr, filename=str(p1), figsize=(6, 5))
print(f"wrote {p1}")

# ---- 2. Correlation heatmap (NA diagonal; auto sequential if non-negative) ----
cor_mat = expr.T.corr()
p2 = out_dir / "02_correlation.png"
pavlab_heatmap(cor_mat, mode="correlation", filename=str(p2), figsize=(6, 5))
print(f"wrote {p2}")

# ---- 3. Raw non-negative data: sequential black-body ----
raw_pos = pd.DataFrame(
    rng.poisson(lam=10, size=(n_genes, n_samples)) + 1,
    index=expr.index, columns=expr.columns,
)
p3 = out_dir / "03_raw_positive.png"
pavlab_heatmap(raw_pos, mode="raw", filename=str(p3), figsize=(6, 5))
print(f"wrote {p3}")

# ---- 4. Big matrix: labels auto-hide ----
big = pd.DataFrame(
    rng.standard_normal((80, 40)),
    index=[f"g{i+1}" for i in range(80)],
    columns=[f"s{i+1}" for i in range(40)],
)
p4 = out_dir / "04_big_labels_auto_hide.png"
pavlab_heatmap(big, filename=str(p4), figsize=(7, 7))
print(f"wrote {p4}")

# ---- 5. Matrix with missing values: grey cells ----
sparse = expr.copy()
flat_idx = rng.choice(expr.size, size=15, replace=False)
for k in flat_idx:
    sparse.iloc[k // expr.shape[1], k % expr.shape[1]] = np.nan
p5 = out_dir / "05_with_missing.png"
pavlab_heatmap(sparse, filename=str(p5), figsize=(6, 5))
print(f"wrote {p5}")

print(f"\nDemo complete. Outputs in: {out_dir}")
