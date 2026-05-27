---
name: supplementary-table
description: >
  Write supplementary tables (xlsx + csv / tsv) that name the figure they
  back. Adds a `Provenance` sheet to every xlsx (or a sheet-level fixed
  header row) and `#`-prefixed comment lines to every csv / tsv. The
  provenance block carries figure_id, build script, source path, sha256,
  and stamped_at — so a reviewer reading table_s1.xlsx knows it's the
  data behind figure 3 panel b without grepping the paper. Two formats
  with one call. Sibling to provenance-stamp (which produces
  *_meta.json sidecars for any analysis artifact); use this one when
  the artifact IS the table.
---

# supplementary-table

Every supplementary table that backs a paper or a deck must say which
figure it powers. Reviewers and future-you should never have to guess
which sheet belongs to which panel.

This skill is the writer. It takes rows of data + provenance fields
and emits:
- **xlsx**: one or more data sheets + a `Provenance` sheet listing
  every sheet's `figure_id | script | source | sha256 | stamped_at`.
- **csv / tsv**: a header block of `#`-prefixed comment lines, then
  the data. Tolerated by every modern parser (`pandas.read_csv(comment='#')`,
  `R read.csv(comment.char='#')`, polars, duckdb, julia CSV.jl).

## Library usage

```python
import sys
sys.path.insert(0, "/path/to/skills/supplementary-table/scripts")
from supp_table import write_csv, write_tsv, write_xlsx

# CSV — single sheet of rows
write_csv(
    "supp/table_s1.csv",
    rows=[
        {"gene": "STAT5B", "mf_rank": 0.991, "score": 0.42},
        {"gene": "YY1",    "mf_rank": 0.957, "score": 0.81},
    ],
    figure="figure_3_panel_b",
    script="scripts/build_figures.py::build_fig3()",
    source="runs/2026-05-25/summary.json",
    description="Per-gene MF-corrected scores used to colour panel b.",
)

# TSV — identical shape, just tab-separated
write_tsv("supp/table_s1.tsv", rows=rows, figure="figure_3_panel_b", ...)

# xlsx — multi-sheet; one Provenance sheet auto-appended
write_xlsx(
    "supp/table_s1.xlsx",
    sheets={
        "MF_scores":     rows_a,
        "Enrichment":    rows_b,
    },
    figure="figure_3",         # applied to every sheet unless overridden
    script="scripts/build_figures.py",
    source="runs/2026-05-25/summary.json",
    per_sheet_figures={        # optional: panel-level granularity
        "MF_scores":  "figure_3_panel_b",
        "Enrichment": "figure_3_panel_c",
    },
)
```

`rows` is a list of dicts (column order = first row's key order).

## What the output looks like

### supp/table_s1.csv

```
# figure: figure_3_panel_b
# script: scripts/build_figures.py::build_fig3()
# source: runs/2026-05-25/summary.json
# sha256: 7f3a9c…
# stamped_at: 2026-05-25T16:42:11Z
# description: Per-gene MF-corrected scores used to colour panel b.
gene,mf_rank,score
STAT5B,0.991,0.42
YY1,0.957,0.81
```

### supp/table_s1.xlsx → each data sheet gets a banner row

The first row of every data sheet says which figure it backs, so a reader
opening the workbook sees the cross-reference immediately without
scrolling to the Provenance sheet. Bold text, amber tint, merged across
the data columns.

| Backs Figure 3 Panel B *(spans all columns, bold, amber-tinted)*       |
|---|
| **gene** | **mf_rank** | **score** |
| STAT5B | 0.991 | 0.42 |
| YY1    | 0.957 | 0.81 |

`figure_id`s that are already human-readable (`"Figure 3"`,
`"Supplementary Figure S2"`) pass through with just a `Backs ` prefix.
snake_case ids (`figure_3_panel_b`) get title-cased. Pass `banner=False`
to suppress (e.g., if the caller wants the unadorned data starting at
row 1).

### supp/table_s1.xlsx → `Provenance` sheet (always present)

| sheet_name | figure_id          | script                                  | source                          | sha256    | stamped_at           |
|---|---|---|---|---|---|
| MF_scores  | figure_3_panel_b   | scripts/build_figures.py                | runs/2026-05-25/summary.json    | 7f3a9c…   | 2026-05-25T16:42:11Z |
| Enrichment | figure_3_panel_c   | scripts/build_figures.py                | runs/2026-05-25/summary.json    | 1d2a44…   | 2026-05-25T16:42:11Z |

## Why two formats?

Journals and reviewers prefer xlsx because everyone can open it; analysis
pipelines prefer csv / tsv because every parser handles them well. Build
both in one call so they don't drift. The `sha256` in the provenance block
is computed over the *data rows only* (not the header / comment block)
so the two formats hash to the same value, proving they're the same data.

## Composition

- **provenance-stamp**: writes `*_meta.json` sidecars for any artifact.
  Use that when the artifact isn't a table (a model file, a downloaded
  ontology, etc.).
- **plotting**: figure scripts call into supplementary-table from
  inside their build functions, so each figure's data is automatically
  exported when the figure is generated. Pattern in `examples/`.

## Dependencies

- Python 3.9+
- `openpyxl` for xlsx (stdlib doesn't ship one). CSV / TSV are stdlib-only.
- No `pandas` requirement — keeps the helper light enough to drop into
  any build script without dragging the scientific-stack dep tree.

## CLI

```bash
python scripts/supp_table.py csv  table_s1.csv  --figure figure_3_panel_b \
    --script scripts/build_figures.py::build_fig3 \
    --source runs/2026-05-25/summary.json \
    --rows-from data.csv

python scripts/supp_table.py xlsx table_s1.xlsx --figure figure_3 \
    --sheet MF_scores=mf.csv  --sheet Enrichment=enrich.csv
```

The CLI is convenience for ad-hoc post-hoc stamping; for figure scripts
that own the data already, prefer the library form.
