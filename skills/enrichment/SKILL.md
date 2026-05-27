---
name: enrichment
description: >
  Stringent gene-set enrichment via PR-AUC (Ballouz, Pavlidis & Gillis 2017,
  ermineJ/ermineR). Takes a ranked/scored gene list + gene sets (default GO
  BP; GMT files for KEGG/Reactome/MSigDB) and reports per-set PR-AUC,
  permutation p-values, BH q-values, and multifunctionality-corrected
  p-values that flag hits driven by always-multifunctional genes
  (TP53/TNF/etc.). Use for any gene-set enrichment question — "enriched
  for apoptosis", "over-represented GO terms in DE genes", "rank KEGG
  pathways". Composes with gene-set-fetch (background), gene-statistics
  (MF correction), gene-annotations / GAF (default GO library).
---

# enrichment

Gene-set enrichment using the precision-recall AUC method from Ballouz
et al. (2017). The most stringent of the standard parametric enrichment
methods for small gene sets ranked against a large background — and the
default method in `ermineJ` / `ermineR` for that reason.

## Why this method (Ballouz et al. 2017)

Standard enrichment methods over-detect when the gene set is small
relative to the background:

- **Fisher's exact / ORA**: treats top-N genes as binary "selected", loses
  the rank information, sensitive to N threshold.
- **ROC-AUC**: high recall at low precision can inflate AUC; tends to call
  almost any large gene set "enriched".
- **PR-AUC** (this skill): rewards early ranks AND precision; only calls a
  set enriched when its members are *concentrated* at the top of the
  ranking, not just present. For typical GO terms (10–200 genes) against
  a 16K-gene protein-coding background, PR-AUC is the right shape.

Combined with **multifunctionality correction**, this method explicitly
distinguishes "your gene list is enriched for X" from "the top-ranked
genes are highly multifunctional and would look enriched for X *regardless
of what you put in*".

## Operations

Two ops in v0.1, both with MF correction on by default.

### `pr_enrichment` — scored gene list, PR-AUC method (Ballouz 2017)

```bash
python scripts/pr_enrichment.py \
    --scores <tsv> \
    [--score-col score] [--gene-col symbol] [--score-direction higher|lower] \
    [--library go-bp | gmt:<path>] \
    [--species human|mouse] \
    [--background-set <name> | --background-set annotated] \
    [--min-set-size 5] [--max-set-size 200] \
    [--permutations 10000] [--seed 0] \
    [--mf-correction / --no-mf-correction] \
    [--refresh] [--out <path>]
```

### `ora` — hit list, hypergeometric / Fisher's exact

```bash
python scripts/ora.py \
    --hits <file>    # TSV with --gene-col column, OR plain-text one symbol per line
    [--gene-col symbol] \
    [--library go-bp | gmt:<path>] \
    [--species human|mouse] \
    [--background-set <name> | --background-set annotated] \
    [--min-set-size 5] [--max-set-size 200] \
    [--mf-correction / --no-mf-correction] \
    [--refresh] [--out <path>]
```

ORA per-set statistic: `P(X >= k)` under `Hypergeometric(N=background, K=set ∩ background, n=hits ∩ background, k=hits ∩ set)`. Equivalent to a one-tailed Fisher's exact for enrichment.

**ORA MF correction** uses a different approach than `pr_enrichment`: it runs ORA in parallel with a synthetic hit list = the top-n most multifunctional genes (same size as the user's hit list, drawn from the same background). The output's `mf_baseline_pvalue` column shows what *that* run would have called significant for each set; sets where the user's pvalue is low but the MF-baseline pvalue is high are specifically enriched in the user's hit list (vs. being a consequence of multifunctional overlap).

## Inputs

**Scores file** (`--scores`): TSV with at least two columns:
- `gene-col` (default `symbol`): gene symbol matching your library/background
- `score-col` (default `score`): numeric score

`--score-direction` says whether higher or lower means "more interesting"
(higher = default; e.g. -log10(pvalue) or fold-change magnitude). The skill
ranks the gene list accordingly before computing PR-AUC.

**Gene-set library** (`--library`):
- `go-bp` (default) — GO biological process. Built from the GO Consortium
  per-species GAF file + go.obo (true-path propagated). Same machinery as
  gene-statistics, sha256-pinned.
- `gmt:<path>` — any [GMT-format](https://software.broadinstitute.org/cancer/software/gsea/wiki/index.php?title=Data_formats#GMT:_Gene_Matrix_Transposed_file_format_.28.2A.gmt.29)
  file. Lets you use MSigDB hallmark sets, KEGG, Reactome exports, custom
  experimental sets, etc.
- v0.2 candidates: `kegg`, `reactome`, `msigdb-hallmark`, `go-mf`, `go-cc`.

## Defaults — what this skill does without flags

| Decision | Default | Rationale |
|---|---|---|
| Background | `protein_coding_<species>_strict` via gene-set-fetch | matches ermineJ + gene-statistics conventions |
| Library | `go-bp` | most common; uses same GAF + go.obo we already cache |
| Set size limits | min 5, max 200 | ermineJ defaults; very small sets are noisy, very large sets are uninformative |
| Score direction | `higher` | standard interpretation |
| Permutations | 10,000 | sufficient for FDR thresholds down to ~1e-3 |
| MF correction | **on** | the whole point of using this method is honest interpretation; see `feedback_go_bloat_and_inference.md` |

## Per-set output TSV

### `pr_enrichment` columns

| column | meaning |
|---|---|
| `set_id` | e.g. `GO:0006915` for go-bp; from column 1 of GMT files |
| `set_name` | human-readable name |
| `set_size` | total genes in the set (after background restriction) |
| `n_genes_in_input` | how many of the user's scored genes appear in this set |
| `pr_auc` | Ballouz PR-AUC statistic, in [0, 1] |
| `pvalue` | empirical p-value from permutation null |
| `qvalue` | BH-adjusted across all sets tested |
| `mf_pr_auc` | PR-AUC against the MF-only ranking (the "what would happen anyway" baseline) |
| `mf_corrected_pvalue` | heuristic-corrected p-value (shift-based against random null; rigorous conditional-permutation version queued for v0.2) |
| `mf_corrected_qvalue` | BH-adjusted |
| `library_source`, `species`, `background_kind` | provenance shortcuts |

### `ora` columns

| column | meaning |
|---|---|
| `set_id`, `set_name` | identifiers |
| `set_size`, `set_size_after_filter` | total + post-background-restriction size |
| `n_hits_in_set` | k in the hypergeometric (intersection of user's hits with set) |
| `expected_hits` | K × n / N (under uniform sampling) |
| `fold_enrichment` | n_hits_in_set / expected_hits |
| `pvalue`, `qvalue` | hypergeometric p + BH q across all sets |
| `mf_baseline_n_hits_in_set` | k when "hits" = top-n most multifunctional genes |
| `mf_baseline_pvalue`, `mf_baseline_qvalue` | sibling ORA over the MF baseline hit list |
| `library_source`, `species`, `background_kind` | provenance |

## Sidecar `.meta.json`

Records all provenance: input scores sha256, library source + sha256 (e.g.
GAF date + OBO version for go-bp), background set sha256, MF artifact path
+ sha256 if correction used, permutation count + seed, every knob choice.

## Cache layout

```
~/.cache/enrichment/
├── pr_enrichment__<input-stem>__go-bp__human__protein_coding_human_strict__perm10000.tsv
├── pr_enrichment__<input-stem>__go-bp__human__protein_coding_human_strict__perm10000.meta.json
└── refs/
```

## Design contract

1. **No bundled data.** Library and background fetched fresh per call (cached).
2. **Provenance composes.** A reviewer can trace the result back to: input
   scores file (sha256), GAF date+sha256, OBO version+sha256, background
   TSV sha256, MF artifact sha256.
3. **Fail loud.** Score file with no overlap to background, library with zero
   sets passing size filter, MF artifact mismatch — all exit non-zero with
   clear messages.
4. **MF correction on by default.** Honest interpretation is the point.
   `--no-mf-correction` to opt out, but documented as "rarely the right
   choice in real analyses".
5. **Set size filters apply to the LIBRARY, not the input.** Filtering the
   input gene list to a size range is the user's choice; filtering library
   gene sets is principled (tiny sets are noisy; huge sets like
   "biological_process" itself are uninformative).
6. **Permutation is gene-label, not gene-score, permutation.** Shuffles the
   gene → score assignment so the null preserves the score distribution
   and library set sizes; standard.

## Dependencies

- Python 3.9+
- `pandas`, `numpy`, `requests`, `obonet`

## References

- Ballouz S, Pavlidis P, Gillis J (2017). Using predictive specificity to
  determine when gene set analysis is biologically meaningful.
  *Nucleic Acids Research* 45(4):e20. doi:10.1093/nar/gkw957
- Gillis J, Pavlidis P (2011). The Impact of Multifunctional Genes on
  "Guilt by Association" Analysis. *PLoS ONE* 6(2):e17258.
- ermineJ / ermineR: https://github.com/PavlidisLab/ermineR

## Composes with

- [`gene-set-fetch`](../gene-set-fetch/SKILL.md) — supplies background sets
- [`gene-statistics`](../gene-statistics/SKILL.md) — supplies MF percentiles
  for MF-corrected p-value (auto-fetched if not present in cache)
- [`gene-annotations`](../gene-annotations/SKILL.md) — same GAF + obo
  machinery; libraries are conceptually compatible
- [`ontology-terms`](../ontology-terms/SKILL.md) — to resolve GO term labels
  / annotate enriched sets
