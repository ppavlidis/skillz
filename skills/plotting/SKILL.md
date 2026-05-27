---
name: plotting
description: >
  Publication-grade plotting helpers (R + Python) with opinionated lab
  defaults. Ships `pavlab_heatmap` (wraps pheatmap / seaborn.heatmap;
  diverging amber-orange→black→sky-blue palette centred at zero,
  black-body sequential alternate, no clustering by default, auto-hides
  labels when too many to read), plus distributional helpers
  `pavlab_scatter`, `pavlab_density` (KDE / histogram / violin),
  `pavlab_stripchart` (strip or swarm — lab default for showing data),
  and `pavlab_boxplot` (used sparingly; bakes in raw points + mean ± SE).
  Use for heatmaps (expression, correlation, any matrix), scatter,
  density, stripcharts, or any "lab-style figure" / "publication-quality
  figure" request.
---

# plotting

R and Python helpers wrapping `pheatmap` / `seaborn.heatmap` with the lab's
publication-figure defaults baked in. v0.1 ships `pavlab_heatmap()` in both
languages.

## Why this skill exists

Across a paper or a thesis, every heatmap should look like it came from
the same lab. That means consistent palettes, consistent handling of
missing values, consistent Z-score clipping, consistent decisions about
whether to cluster rows/columns, consistent name-hiding when there are
too many to read. Re-deciding these each time is wasted effort and
produces visually inconsistent figures across collaborators.

This skill captures those decisions as defaults, with a small set of
mode switches for the cases that come up. The function still takes
`...` and passes anything through to `pheatmap`, so any standard
pheatmap argument works.

## Setup

### Python

```bash
cd skills/plotting
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # runtime
.venv/bin/pip install -r requirements-dev.txt    # + pytest
.venv/bin/pytest tests/ -q                       # verify
```

### R

```r
install.packages(c("ggplot2", "pheatmap", "RColorBrewer"))
# optional (large-N scatter): install.packages("hexbin")
Rscript tests/test_scatter.R    # verify
```

### Gallery

```bash
.venv/bin/python examples/build_gallery.py
# opens examples/gallery/index.html
```

## Dependencies

### R

- R ≥ 4.0
- `ggplot2` ≥ 3.4, `pheatmap` ≥ 1.0.12
- `RColorBrewer` (for palette swaps)
- `hexbin` (optional, for large-N scatter)

### Python

- Python ≥ 3.9
- `matplotlib`, `seaborn`, `numpy`, `pandas`, `scipy`

## Quick start

### R

```r
source("R/pavlab_heatmap.R")
source("R/palettes.R")

# Expression matrix (rows = genes, cols = samples).
# Default: row-standardize → Z-scores, clip ±3, divergent palette.
pavlab_heatmap(expr_mat)

# Same, saved to a PDF for a paper figure.
pavlab_heatmap(expr_mat, filename = "fig_2a_heatmap.pdf",
               width = 7, height = 9)

# Correlation heatmap: diagonal -> NA, divergent palette.
pavlab_heatmap(cor(t(expr_mat)), mode = "correlation")

# Raw values (no transform). Palette is sequential black-body if all
# values are >= 0, divergent otherwise.
pavlab_heatmap(raw_intensity_mat, mode = "raw")
```

### Python

```python
import sys
sys.path.insert(0, "/path/to/skills/plotting/python")
from pavlab_heatmap import pavlab_heatmap
import pandas as pd

# Expression matrix — same defaults as R.
pavlab_heatmap(expr_df)

# Save to file (PNG, PDF, SVG — whatever matplotlib infers from the extension).
pavlab_heatmap(expr_df, filename="fig_2a_heatmap.pdf", figsize=(7, 9))

# Correlation heatmap.
pavlab_heatmap(cor_df, mode="correlation")

# Raw mode; sequential palette when all values >= 0.
pavlab_heatmap(raw_df, mode="raw")

# Draw into an existing Axes (for multi-panel figures).
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
pavlab_heatmap(expr_df, ax=axes[0])
pavlab_heatmap(cor_df, mode="correlation", ax=axes[1])
fig.tight_layout()
fig.savefig("fig.pdf")
```

## Lab defaults — what `pavlab_heatmap()` does without you asking

| Default | Reason |
|---|---|
| **No row clustering** | most heatmaps look like noise after clustering both axes; users should opt in to clustering with a specific intent |
| **No column clustering** | same |
| **Grey for missing values** (`na_color = "grey80"`) | distinguishes missing-data cells from "value near zero in a divergent palette" |
| **Z-score by row** when `mode = "expression"` | expression heatmaps should highlight relative patterns per gene, not absolute intensities |
| **Z-clipped to ±3** when standardized | one extreme value otherwise dominates the color scale |
| **Divergent palette: amber-orange → black → sky-blue** (zero anchored at black) | black-at-zero makes near-zero cells visually quiet so the eye is drawn to genuinely high/low cells; both anchors have moderate-high luminance (no near-white extremes that lose dynamic range), matched in brightness so neither side dominates, and survive dim-screen viewing. Named alternates are available — see *Divergent palette variants* below. |
| **Sequential palette: black-body** (black → red → orange → yellow → white) | brighter cells = higher values, intuitive thermal mapping; CB-friendly luminance ramp |
| **Correlation diagonal → NA** | the always-1.0 diagonal otherwise eats half the color scale, especially when all off-diagonals are small (e.g. correlations < 0.2) |
| **Hide rownames if `nrow > 50`** | unreadable labels are worse than no labels; threshold overridable |
| **Hide colnames if `ncol > 30`** | column space is tighter than row space; lower threshold |
| **`angle_col = 45`** | diagonal column labels are readable without dominating |
| **`border_color = NA`** (no gridlines between cells) | pheatmap's default `grey60` gridlines visually clutter the color signal; turning them off lets the color do the work |
| **Correlation mode: sequential palette when all correlations are essentially non-negative** | very common case (sample-sample correlations are usually all positive); using divergent here wastes half the color scale on values that don't exist. If the minimum value is between `correlation_negative_tolerance` (default `-0.1`) and 0, small negatives are *clipped to 0* (forced to the cutpoint) and we use the black-body sequential palette. If the minimum is more negative than that, we fall back to divergent. |

All defaults are explicit arguments; override anything by passing it
directly. Any unrecognized argument is forwarded to `pheatmap` (R) or
`seaborn.heatmap` (Python).

## Function signature

### R

```r
pavlab_heatmap(
  mat,
  mode = c("expression", "correlation", "raw"),
  cluster_rows = FALSE,
  cluster_cols = FALSE,
  show_rownames = NULL,    # NULL = auto: hide if nrow > rowname_threshold
  show_colnames = NULL,    # NULL = auto: hide if ncol > colname_threshold
  standardize_rows = NULL, # NULL = TRUE iff mode == "expression"
  zclip = 3,               # applied when standardize_rows == TRUE
  divergent = NULL,        # NULL = auto: TRUE if correlation/expression
                           #              or raw data spans zero
  na_color = "grey80",
  palette_n = 256,
  rowname_threshold = 50,
  colname_threshold = 30,
  angle_col = 45,
  border_color = NA,                       # no gridlines between cells
  correlation_negative_tolerance = -0.1,   # in correlation mode, clip values
                                           # in [tolerance, 0] to 0 and use
                                           # sequential (black-body)
  filename = NULL,         # if non-NULL, saved via pheatmap's filename mechanism
  ...                      # forwarded to pheatmap()
)
```

### Python

```python
pavlab_heatmap(
    mat,                        # 2D array, DataFrame, or anything array-convertible
    mode = "expression",        # "expression" | "correlation" | "raw"
    cluster_rows = False,       # raises NotImplementedError (use sns.clustermap directly)
    cluster_cols = False,
    show_rownames = None,       # None = auto: hide if nrow > rowname_threshold
    show_colnames = None,       # None = auto: hide if ncol > colname_threshold
    standardize_rows = None,    # None = True iff mode == "expression"
    zclip = 3.0,                # applied when standardize_rows == True
    divergent = None,           # None = auto
    na_color = "#cccccc",       # matches R's grey80
    palette_n = 256,
    rowname_threshold = 50,
    colname_threshold = 30,
    angle_col = 45,
    border_color = None,        # None = no gridlines (linewidths=0)
    correlation_negative_tolerance = -0.1,
    filename = None,            # if given, fig.savefig(filename) and close
    figsize = None,             # (w, h) tuple; None = mild auto-size
    cmap = None,                # override auto-chosen palette
    ax = None,                  # draw into existing Axes
    **kwargs,                   # forwarded to seaborn.heatmap
)
# Returns: matplotlib Axes
```

**Python-only notes:**

- `cluster_rows=True` / `cluster_cols=True` raises `NotImplementedError`.
  Call `sns.clustermap` directly if you need clustering; the same palette
  helpers work via `cmap=divergent_palette()`.
- Pass `ax=` to embed the heatmap in a multi-panel figure. When `ax` is
  supplied, `figsize` and `filename` are ignored (manage the figure yourself).
- File format is inferred by matplotlib from the extension (`.pdf`, `.png`,
  `.svg`, etc.).

## Divergent palette variants ("Paul-approved")

All have **black at the midpoint**, **matched luminance** on the two sides,
and **no near-white extremes** that would lose information at saturation.
Pick by feel; the construction is shared.

| Function | Look | Use when |
|---|---|---|
| `divergent_palette()` (default) | amber-orange / sky-blue | general use; bright enough to survive dim screens; not overly "primary" |
| `divergent_palette_rdbu()` | Brewer-RdBu mid red / blue | classic-paper feel; slightly more muted |
| `divergent_palette_spectral()` | Spectral-mid: red-orange / cool blue | extra warm-cool punch |
| `divergent_palette_cyan_yellow()` | cyan / yellow | high pop; vivid primaries; less paper-stylish |
| `divergent_palette_blue_yellow()` | classic blue / yellow | the classic, but yellow dominates the blue — the asymmetry is the point if you specifically want this look |

Override the default per-call:

```r
# R
pavlab_heatmap(mat, color = divergent_palette_rdbu(256))
```

```python
# Python
from palettes import divergent_palette_rdbu
pavlab_heatmap(mat, cmap=divergent_palette_rdbu(256))
```

## Modes

| `mode` | Behavior | Palette default |
|---|---|---|
| `"expression"` (default) | row-standardize → Z-scores → clip to ±zclip | divergent (zero anchored) |
| `"correlation"` | set diagonal to NA; no standardization. If `min(mat) ≥ correlation_negative_tolerance` (default -0.1), any small negatives are clipped to 0 and the palette is sequential black-body | sequential when ~all ≥ 0; divergent otherwise |
| `"raw"` | no transformation | sequential if `min(mat) >= 0`; divergent otherwise |

## When NOT to use this skill

- For exploratory clustering analyses where you genuinely want the heatmap
  to drive the discovery — call `pheatmap` (R) or `sns.clustermap` (Python)
  directly with `cluster_rows = TRUE` / `cluster_rows=True`.
- For non-publication interactive exploration (use `heatmaply`, `iheatmapr`,
  `plotly`, etc.).
- When you need annotated tracks / split rows / row clustering with custom
  cuts → use `ComplexHeatmap` (R), which `pavlab_heatmap` doesn't wrap.

## Design contract

1. **Defaults encode lab convention.** Don't change them lightly; updating
   a default ripples across every figure that uses this skill.
2. **Anything `pheatmap` / `seaborn.heatmap` accepts, you can pass via `...`
   / `**kwargs`.** This skill adds defaults; it doesn't take features away.
3. **Saving to file:** R uses pheatmap's `filename` argument (auto-detects
   format from extension). Python calls `fig.savefig(filename)` with the same
   extension-based format inference via matplotlib.
4. **Missing values are grey.** Hardcoded design choice. NA must never be
   confused with "value near zero".
5. **Divergent palette centers black at zero** — symmetric breaks, so
   negative and positive of equal magnitude render the same brightness.

---

# pavlab_scatter (Python) — v0.1

Scatter plot with the same lab-default ethos: no background, no gridlines,
black circles, large axis labels. Use this whenever a user asks for a scatter
plot, replicate comparison, PCA visualization, or any two-variable plot where
the lab's publication defaults should apply.

## Quick start

```python
import sys
sys.path.insert(0, "/path/to/skills/plotting/python")
from pavlab_scatter import pavlab_scatter

# Basic
pavlab_scatter(x, y)

# Replicate comparison with log2 axes
pavlab_scatter(tpm1, tpm2,
               xlabel="TPM rep1", ylabel="TPM rep2",
               log_x="log2", log_y="log2")

# Categorical colour → lab accent palette + legend
pavlab_scatter(pc1, pc2, color=cell_type_labels,
               xlabel="PC1", ylabel="PC2", origin_zero=False)

# Numeric colour → viridis + colorbar
pavlab_scatter(x, y, color=p_values, color_label="p-value")

# Save
pavlab_scatter(x, y, filename="fig3a.pdf", figsize=(4, 4))

# Embed in a multi-panel figure
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
pavlab_scatter(x1, y1, ax=axes[0])
pavlab_scatter(x2, y2, ax=axes[1])
```

## Lab defaults — what `pavlab_scatter()` does without you asking

| Default | Reason |
|---|---|
| **Black filled circles** | most legible for single-series data; colour reserved for cases where it adds information (grouping, a third variable) |
| **No background, no gridlines** | scatter geometry is self-locating; gridlines add noise without aiding reading of individual points |
| **Top + right spines off** | standard publication style — keeps the axes minimal |
| **`origin_zero=True`** | for non-negative data the axis should start at 0 so readers don't mistake a floating baseline |
| **Large labels by default** (`"med"` = 14 pt label / 11 pt ticks) | legible on a projector and after journal reduction to a 3-inch column width; `"large"` adds a further margin |
| **N-adaptive rendering** | ≤ 500 → solid circles (s=20); 501–10 000 → semi-transparent circles (alpha 0.60→0.15); > 10 000 → hexbin density with black-body palette |
| **Log-scale suggestion warning** | when data spans > 100× and no log transform is requested, a `UserWarning` suggests `log_x='log2'` / `'log10'` |
| **log2 for biological data, log10 for counts** | `True` auto-selects: max > 1 000 → log10 (count-like), otherwise log2 (expression / biological). `ln` is never used. |
| **No regression lines or fit overlays** | those belong in the analysis, not the default plot — pass `**kwargs` to add them explicitly if needed |

## Function signature

```python
pavlab_scatter(
    x, y,                           # array-like; NaN/inf pairs silently dropped
    color=None,                     # None=black; str=uniform; str-array=categorical;
                                    # float-array=viridis colormap
    color_label=None,               # colorbar label for numeric color
    label_size="med",               # "small" | "med" | "large" | float
    xlabel=None,                    # log suffix appended automatically
    ylabel=None,
    title=None,                     # left-aligned, normal weight
    log_x=False,                    # False | True | "log2" | "log10"
    log_y=False,
    pseudocount=1.0,                # added before log transform
    origin_zero=True,               # pin axis lower bound to 0 for non-neg data
    xlim=None,                      # override origin_zero
    ylim=None,
    point_size=None,                # None = auto from N (20 or 10)
    filename=None,                  # format from extension; ignored when ax= given
    figsize=None,                   # default (5.5, 5.0); ignored when ax= given
    ax=None,                        # draw into existing Axes
    **kwargs,                       # forwarded to ax.scatter or ax.hexbin
)
# Returns: matplotlib Axes
```

## N-adaptive rendering detail

| N | Marker | Size | Alpha | Mode |
|---|---|---|---|---|
| ≤ 500 | `o` | 20 | 1.0 | scatter |
| 501–10 000 | `o` | 10 | 0.60 → 0.15 (linear) | scatter |
| > 10 000 | — | — | — | hexbin (black-body palette, gridsize=40) |

When hexbin is active, `color=` is ignored (with a warning).

## Log-scale guide

| Data type | Recommended | Rationale |
|---|---|---|
| Gene expression (TPM, FPKM, CPM) | `log_x="log2"` | biological doubling scale; common in the literature |
| Raw counts (read counts, UMIs) | `log_x="log10"` | span many orders of magnitude; log10 is intuitive for counts |
| Data with zeros | any log + `pseudocount=1` | default pseudocount=1 shifts zeros to log2(1)=0 or log10(1)=0 |
| Values all >> 0 | `log_x=True` (auto) | heuristic: max > 1 000 → log10, else log2 |

`ln` is never used. When data spans > 100× without a transform, a
`UserWarning` is emitted suggesting the appropriate scale.

## When NOT to use this skill

- PCA / UMAP visualizations where you need per-point shape, size, or label
  callouts beyond what `**kwargs` can provide — build a custom matplotlib
  figure instead.
- When you genuinely need a regression overlay: pass `**kwargs` with
  seaborn's `regplot` approach or call `ax.plot` after getting the Axes back.

---

# pavlab_scatter (R / ggplot2) — v0.1

Same defaults as the Python version, ggplot2 backend. Returns a ggplot2 object
that can be extended with `+` layers (add `geom_abline`, annotations, etc.).

## Quick start

```r
source("/path/to/skills/plotting/R/palettes.R")
source("/path/to/skills/plotting/R/pavlab_scatter.R")

# Basic
pavlab_scatter(x, y)

# Replicate comparison with log2 axes
pavlab_scatter(tpm1, tpm2,
               xlabel = "TPM rep1", ylabel = "TPM rep2",
               log_x = "log2", log_y = "log2")

# Categorical colour → lab accent palette + legend
pavlab_scatter(pc1, pc2, color = cell_type_labels,
               xlabel = "PC1", ylabel = "PC2", origin_zero = FALSE)

# Numeric colour → viridis + colorbar
pavlab_scatter(x, y, color = p_values, color_label = "p-value")

# Save
pavlab_scatter(x, y, filename = "fig3a.pdf", figsize = c(4, 4))

# Extend with ggplot2 layers
p <- pavlab_scatter(x, y)
p + ggplot2::geom_abline(slope = 1, linetype = "dashed", color = "gray60")
```

## Function signature

```r
pavlab_scatter(
  x, y,                       # numeric vectors; NaN/Inf/NA pairs silently dropped
  color = NULL,               # NULL=black; single string=uniform; char/factor vec=categorical;
                              # numeric vec=viridis colorbar
  color_label = NULL,         # colorbar title for numeric color
  label_size  = "med",        # "small" | "med" | "large" | numeric
  xlabel = NULL,              # log suffix appended automatically
  ylabel = NULL,
  title  = NULL,              # left-aligned, normal weight
  log_x  = FALSE,             # FALSE | TRUE | "log2" | "log10"
  log_y  = FALSE,
  pseudocount = 1.0,          # added before log transform
  origin_zero = TRUE,         # expand axis lower bound to include 0 for non-neg data
  xlim = NULL,                # override origin_zero; c(lo, hi)
  ylim = NULL,
  point_size = NULL,          # ggplot2 size in mm; default 2.0 (N≤500) or 1.5
  filename = NULL,            # format from extension via ggsave
  figsize  = NULL             # c(width, height) in inches; default c(5.5, 5.0)
)
# Returns: ggplot2 object (invisibly)
```

## N-adaptive rendering

| N | Marker | Size (mm) | Alpha | Mode |
|---|---|---|---|---|
| ≤ 500 | solid circle (shape 16) | 2.0 | 1.0 | geom_point |
| 501–10 000 | solid circle (shape 16) | 1.5 | 0.60 → 0.15 (linear) | geom_point |
| > 10 000 | — | — | — | geom_hex (black-body palette, bins=40) |

hexbin package required for the density mode: `install.packages("hexbin")`.
When hexbin mode activates, `color=` is ignored with a warning.

**Note on log-scale labels with PDF output:** R's default PDF device may not
render Unicode subscripts (log₂, log₁₀) correctly. Use SVG output
(`filename="fig.svg"`) or `cairo_pdf()` for pixel-perfect subscripts.

---

# pavlab_stripchart — v0.1 (Python + R)

Jittered strip chart: categorical x-axis, continuous y-axis. Colour
stratification within groups via `color=`; no shape stratification (circles
only). Optional grand-mean / grand-median reference lines spanning the full
plot width.

## Quick start

```python
from pavlab_stripchart import pavlab_stripchart

pavlab_stripchart(cell_type, expression)                     # all black
pavlab_stripchart(cell_type, expression, color=treatment)    # stratify by treatment
pavlab_stripchart(cell_type, expression,
                 log_y="log2", ylabel="Expression (TPM)",
                 show_mean=True, order=["ctrl", "het", "hom"])
```

```r
source("R/palettes.R"); source("R/pavlab_scatter.R"); source("R/pavlab_stripchart.R")
pavlab_stripchart(cell_type, expression)
pavlab_stripchart(cell_type, expression, color=treatment,
                 log_y="log2", show_mean=TRUE, order=c("ctrl","het","hom"))
p <- pavlab_stripchart(cell_type, expression)
p + ggplot2::geom_boxplot(alpha = 0, width = 0.3)   # overlay a boxplot
```

## Key parameters (both languages)

| Parameter | Default | Effect |
|---|---|---|
| `color` | NULL/None → black | same semantics as scatter: uniform, categorical-accent, viridis |
| `kind` | "strip" | `"strip"` = uniform jitter; `"swarm"` = non-overlapping beeswarm packing (Python: built-in; R: requires `ggbeeswarm`) |
| `jitter` | 0.2 | horizontal jitter half-width when `kind="strip"`; ignored under swarm |
| `show_mean` | FALSE/False | dashed grey line at **grand mean** across full plot |
| `show_median` | FALSE/False | dotted grey line at **grand median** across full plot |
| `order` | NULL/None | explicit group order; unknown groups appended (R) or warned (Py) |
| `log_y` | FALSE/False | same as scatter: False/True/"log2"/"log10" |
| `origin_zero` | TRUE/True | pin y lower bound to 0 for non-negative data |

Mean line style: dashed `--`, gray-400 (`#9ca3af`).
Median line style: dotted `:`, same color.

### When to pick strip vs. swarm

`kind="strip"` is the right default for small-to-medium N (≲ 200 per group)
where the random jitter doesn't visually overlap much. `kind="swarm"` is
the better choice when points pile up within a group and the random
jitter starts to look like a blob; the beeswarm packs them
non-overlappingly so the shape of the distribution becomes legible at a
glance. Swarm gets expensive (O(n²) per group) above a few thousand
points per group — for those, switch to `pavlab_density` instead.

---

# pavlab_boxplot — v0.2 (Python + R)

Used **sparingly** — the lab default for distributional summaries is
`pavlab_stripchart` (raw points). When a boxplot is the right tool
(multi-panel layouts where visual compactness matters), this helper
defaults to **raw points underneath + box**. There is intentionally
no error-bar parameter: the box's own whiskers + IQR + median IS the
spread visualisation, and overlaying a separate SD or CI bar on top
just doubles the spread cue.

Two modes:

- `show_points=True` (default): swarmed raw points under the box.
- `show_points=False`: compact box-only chart (multi-panel layouts
  where every pixel counts; whiskers and IQR still carry the spread).

## Quick start

```python
from pavlab_boxplot import pavlab_boxplot

# default: swarmed points + box
pavlab_boxplot(genotype, expression, ylabel="Expression")

# compact box (no points) — whiskers still convey spread
pavlab_boxplot(genotype, expression, show_points=False)

# jittered (strip) points instead of swarmed
pavlab_boxplot(genotype, expression, points_kind="strip")
```

```r
source("R/palettes.R"); source("R/pavlab_scatter.R"); source("R/pavlab_boxplot.R")

pavlab_boxplot(genotype, expression)
pavlab_boxplot(genotype, expression, show_points = FALSE)
pavlab_boxplot(genotype, expression, points_kind = "strip")
```

## Key parameters

| Parameter | Default | Effect |
|---|---|---|
| `show_points` | True / TRUE | draw raw data points under the box |
| `points_kind` | `"swarm"` | `"swarm"` (packed) or `"strip"` (jittered) — swarm needs `ggbeeswarm` in R |
| `jitter` | 0.2 | jitter half-width when `points_kind="strip"` |
| `box_width` | 0.55 | box width in x-data units |
| `color` | None / NULL | colours the **points layer only** — the box always uses lab structural colour |
| `order`, `log_y`, `origin_zero`, `ylim`, `xlabel`, `ylabel`, `title`, `filename`, `figsize`, `point_size`, `ax` (Python only) | | same as `pavlab_stripchart` |

## Visual conventions

- Box fill: gray-100 `#f3f4f6` (very pale) so points underneath stay readable
- Box outline + median + whiskers: gray-800 `#1f2937` (TEXT)
- Median line slightly heavier than box outline
- No outlier fliers (the raw points already show outliers)
- Points: gray-700 `#374151` by default; categorical/numeric `color=` recolours **only the points layer**, not the box

## Cross-plot rule: no gridlines, ticks visible

Every chart this skill produces — and any hand-authored matplotlib /
ggplot2 figure that wants to look lab-style — uses **no gridlines** and
**short outward tick marks on both axes**, regardless of figure type
(bars, scatter, lines, heatmaps). This applies even when the global
matplotlib `rcParams` or ggplot's `theme_grey()` default would draw
gridlines.

**Why:** Gridlines compete with the data marks for visual weight.
Tick marks alone are sufficient to locate values precisely. The lab
style is "the data is the figure; everything else is chrome."

**How to apply (matplotlib):** at the top of any figure script, set:

```python
mpl.rcParams.update({
    "axes.grid":          False,   # no panel grid
    "xtick.major.size":   4,       # outward ticks, ~4 pt long
    "ytick.major.size":   4,
    "xtick.major.width":  0.8,
    "ytick.major.width":  0.8,
    "xtick.direction":    "out",
    "ytick.direction":    "out",
    "axes.spines.top":    False,
    "axes.spines.right":  False,
})
```

For per-axes overrides, call `ax.grid(False)` and
`ax.tick_params(axis="both", which="major", length=4, width=0.8,
direction="out", color="#6b7280")`.

**How to apply (ggplot2):** use the lab `theme_pavlab()` (or
`theme_classic()` + `theme(panel.grid = element_blank(),
axis.ticks = element_line(...))`). Default `theme_grey()` is rejected.

**Override:** if a reviewer or stylistic exception genuinely calls for
gridlines (e.g., a log-scale plot where the reader needs help locating
intermediate values), use light gray-200 horizontal lines only and
state the exception in the figure caption.

---

## Cross-plot rule: figure captions describe, they don't re-explain

Figure captions are not a mini-Methods. The caption describes **what
the reader is looking at in this image** — the axes, the units, the
data shown, what the colours / shapes / error bars represent. Anything
that's a *protocol detail* (sample construction, statistical test
choice, threshold rationale, model parameters, the order operations
ran in) belongs in the Methods section, not in the caption.

If the caption needs to nod toward Methods for a specific detail —
"how was the sample drawn", "which statistical test", "what's the
threshold" — use a **parenthetical reference**, not a trailing
sentence:

✔️ `…cross-walk-aware scoring (Methods).`
✔️ `…Wilson 95 % CIs throughout (see Methods).`
✔️ `Top-50 retrieval was used for the second-pass call (Methods,
    *Cell-line pipeline*).`

✖️ `… See Methods.` as a trailing sentence on every caption —
    reads as filler, signals nothing the reader didn't infer from the
    caption number alone.
✖️ Re-explaining what each annotated experimental condition means
    when the same explanation already lives in Methods — the
    caption's job is to point at the picture, not to restate the
    protocol.
✖️ A multi-sentence "this is how we ran the analysis" passage
    embedded in the caption.

**The test:** if the caption sentence would still be true with the
figure replaced by a black box, it probably belongs in Methods.
What stays in the caption is what *only the caption can say* —
"the orange diamond is MetaMuse", "dashed line is the y=x reference",
"n = 491–498 with usable rows".

Bolded leadgloss is preferred: `**Figure 3:** Strain annotation
accuracy across methods.` followed by the descriptive sentences. The
"see Methods" pointer goes inline if it has to appear at all.

This applies to: figure captions in the manuscript body, supplementary
figure captions, the caption row in `Figures_assembled.docx`-style
deliverables, and the description fields in any supplementary table
that names a figure.

---

## Cross-plot rule: error bars are never SEM (for the helpers that have them)

`pavlab_boxplot` intentionally has no `error=` parameter — the box +
whiskers + IQR already convey the data's spread. But for future
helpers that DO draw error bars (forest plots, parameter-estimate
charts, etc.), the lab-wide convention is:

- **`"sd"`** — sample standard deviation. Used when the chart plots
  the **raw data** and an explicit spread cue is needed.
- **`"ci95"`** — 95% confidence interval (mean ± 1.96 × SE). Used when
  the chart plots **parameter estimates** (means of means, regression
  coefficients, model fits). Communicates uncertainty on the estimate.

**SEM is rejected.** Future helpers that accept `error=` must reject
`"se"` / `"sem"` at the API level with a redirect to one of the two
valid choices. Rationale: SEM shrinks with N — it visually understates
spread on large-N data and reads misleadingly as a CI without being
one. SD answers *"how spread is the data?"* and CI answers *"how
certain is the estimate?"* — picking the right one for the chart's
purpose is more informative than the historically-conventional SEM.

---

# pavlab_density — v0.1 (Python + R)

Unified distribution-visualization function with three modes: density
(KDE fill), histogram, and violin. One function, consistent defaults, optional
reflection correction at boundaries for non-negative or probability data.

## Quick start

```python
from pavlab_density import pavlab_density

# Single distribution — KDE with fill
pavlab_density(tpm_values)

# Histogram
pavlab_density(counts, kind="histogram", stat="count", log_x="log10")

# Grouped overlay density (≤ 3 groups; warns above that)
pavlab_density(values, groups=cell_type, kind="density")

# Grouped faceted density (one panel per group)
pavlab_density(values, groups=cell_type, kind="density", facet=True)

# Violin (groups required)
pavlab_density(values, groups=treatment, kind="violin",
               show_mean=True, order=["ctrl", "het", "hom"])

# Probability data: reflection at 0 and 1
pavlab_density(p_values, reflect_bounds=True, xlabel="p-value")
```

```r
source("R/palettes.R"); source("R/pavlab_scatter.R"); source("R/pavlab_density.R")

# Single distribution
pavlab_density(tpm_values)

# Grouped faceted histogram
pavlab_density(values, groups=cell_type, kind="histogram",
               facet=TRUE, bins=50, stat="count")

# Violin with grand-mean reference line
pavlab_density(values, groups=treatment, kind="violin",
               show_mean=TRUE, order=c("ctrl","het","hom"))

# Probability reflection
pavlab_density(probabilities, reflect_bounds=TRUE, xlabel="p-value")

# Extend with ggplot2 layers
p <- pavlab_density(values, groups=g, kind="violin")
p + ggplot2::geom_jitter(width=0.1, alpha=0.3)
```

## Lab defaults

| Default | Reason |
|---|---|
| **`kind="density"`** | KDE fill; reveals shape without committing to a bin count |
| **Bounded-data warning** | If data appears non-negative or in [0,1] and `reflect_bounds=False`, a `UserWarning` alerts that the KDE may bleed outside the support |
| **Accent palette per group** | Cycles through `_ACCENT_COLORS` by default; uniform with `color="gray"` |
| **Overlay warns at > 3 groups** | More than 3 overlapping densities are hard to read; suggests `facet=True` |
| **Grand mean/median lines** | Full-width dashed/dotted gray-400 (`#9ca3af`) — same visual language as stripchart |
| **`origin_zero=True`** | y lower bound pinned to 0 for density/histogram when data are non-negative |

## Modes

| `kind` | Layout | Notes |
|---|---|---|
| `"density"` | Single KDE fill (single) or overlaid fills (grouped) | `facet=True` → one panel per group |
| `"histogram"` | Filled bars, `alpha=0.7`, white dividers | Shared bin edges across groups when faceted |
| `"violin"` | One violin per group, categorical x / continuous y | Requires `groups=`; `log_y` pre-transforms values (same as stripchart) |

## Boundary reflection

For KDE, reflection removes edge artifacts on bounded data. When the data minimum
is ≥ 0, boundary `lo=0` is detected automatically. If `max ≤ 1`, `hi=1` is also
set (probability data). When reflection is applied:

1. Reflect samples: `arr_reflected = [arr, 2*lo - arr]` (and/or at `hi`)
2. Estimate KDE on reflected set
3. Scale by 2× to normalize
4. Zero density outside `[lo, hi]`

`reflect_bounds=True` uses this path. Without it, a warning fires when bounds
are detected.

## Function signature (Python)

```python
pavlab_density(
    values,                      # 1-D array-like; NaN/Inf silently dropped
    groups=None,                 # same-length group labels; required for violin
    kind="density",              # "density" | "histogram" | "violin"
    facet=False,                 # True → Figure with one panel per group
    stat="density",              # "density" | "count" (histogram / density y-axis)
    bins="auto",                 # bin count for histogram; passed to np.histogram
    bw_method="scott",           # scipy KDE bandwidth
    reflect_bounds=False,        # reflect KDE at auto-detected boundaries
    color=None,                  # None=accent palette; str=uniform; list=per-group
    log_x=False,                 # False | True | "log2" | "log10"
    log_y=False,                 # same; for violin applies to values axis
    pseudocount=1.0,
    origin_zero=True,
    label_size="med",
    xlabel=None, ylabel=None, title=None,
    xlim=None, ylim=None,
    show_mean=False, show_median=False,
    order=None,                  # explicit group order; unlisted groups warned + skipped
    figsize=None, filename=None, ax=None,
)
# Returns: Axes (facet=False) or Figure (facet=True)
```

## Function signature (R)

```r
pavlab_density(
  values,                        # numeric vector; NA/Inf silently dropped
  groups         = NULL,         # character/factor vector; required for violin
  kind           = "density",    # "density" | "histogram" | "violin"
  facet          = FALSE,        # TRUE → facet_wrap by group
  stat           = "density",    # "density" | "count"
  bins           = 30,
  bw             = "nrd0",       # stats::density bandwidth
  reflect_bounds = FALSE,
  color          = NULL,         # NULL=accent; single string=uniform; vector=per-group
  log_x          = FALSE,        # FALSE | TRUE | "log2" | "log10"
  log_y          = FALSE,        # for violin: pre-transforms values (like stripchart)
  pseudocount    = 1.0,
  origin_zero    = TRUE,
  label_size     = "med",
  xlabel = NULL, ylabel = NULL, title = NULL,
  xlim = NULL, ylim = NULL,
  show_mean = FALSE, show_median = FALSE,
  order          = NULL,         # extras appended in appearance order (lenient)
  figsize = NULL, filename = NULL
)
# Returns: ggplot2 object (invisibly)
```

**Cross-language note:** Python uses `log_x` to pre-transform values for violin
(since Python treats violin y-axis as the "x" data axis internally).
R uses `log_y` for violin pre-transform (consistent with `pavlab_stripchart`).
Both behave identically in density / histogram modes.

---

## Planned v0.2

- `pavlab_boxplot()`.
- Optional `ComplexHeatmap` backend for annotated heatmaps.

## References

- Wickham H, *ggplot2: Elegant Graphics for Data Analysis*, Springer.
- pheatmap: https://cran.r-project.org/package=pheatmap
- RColorBrewer / Brewer color schemes: https://colorbrewer2.org/
- Black-body radiation colormap convention:
  https://matplotlib.org/stable/gallery/color/colormap_reference.html
  (matplotlib's `hot`, `afmhot`, `inferno`)
