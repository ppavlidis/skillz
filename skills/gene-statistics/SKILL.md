---
name: gene-statistics
description: >
  Per-gene meta-statistics that quantify "gene-level biases" in genomic
  analyses. v0.1 ships `multifunctionality` — the Gillis & Pavlidis (2011)
  AUC-style score over GO biological-process annotations: how easily a gene
  stands out from background by virtue of its annotations alone. High-MF
  genes appear as top hits in almost every guilt-by-association,
  enrichment, or differential-expression analysis regardless of the
  underlying biology, so flagging or correcting for MF is critical for
  honest interpretation. Future operations include the Differential
  Expression Prior (Crow, Pavlidis, Gillis 2019) and similar per-gene
  meta-statistics. Use this skill whenever a user asks about gene
  multifunctionality, MF score, "is this gene always a hit", DE prior,
  guilt-by-association bias, or how to flag genes that are statistically
  privileged in genomic analyses. Distinct from `gene-annotations`
  (which produces the raw annotations this skill consumes), `ontology-terms`
  (ontology structure), and `gene-set-fetch` (named gene catalogs).
---

# gene-statistics

Per-gene meta-statistics that quantify how a gene's properties bias the
analyses it participates in. Genes are not equal: some are annotated to
many GO terms (highly multifunctional → tend to appear in any enrichment),
some are perpetually differentially expressed across studies regardless of
condition (high DE prior → suspect interpretation). This skill computes
these scores so downstream analyses can flag, weight, or correct for them.

## Why this skill exists

In any guilt-by-association, enrichment, or DE analysis, a handful of
genes show up at the top *no matter what the question is*. They're not
necessarily the answer — they're just genes that have a head start. The
canonical examples:

- **Multifunctional genes** (Gillis & Pavlidis 2011) — genes annotated
  to many GO terms covering many biological processes. A guilt-by-association
  network analysis will rank them as "predicted to share function" with
  almost any input list, because they share annotations with almost any
  input.
- **Differentially-expressed-prior genes** (Crow, Pavlidis, Gillis 2019)
  — genes that show up as DE across a wide range of unrelated studies.
  Some are technical artifacts of common preprocessing pipelines; some
  are real but biologically uninformative (housekeeping, ribosomal);
  treating them as "novel hits" in any one study is misleading.

Computing these scores is the first step toward correcting for them.
ermineJ / ermineR uses per-gene MF for the `MFPvalue` /
`CorrectedMFPvalue` columns; the same idea generalizes.

## Operations

```bash
python scripts/multifunctionality.py [--species human|mouse] [--source gaf] [--aspect BP] \
    [--background-set <gene-set-fetch-set-name> | --background-tsv <path> | --background-set annotated] \
    [--refresh] [--out PATH]
# planned v0.2: python scripts/de_prior.py ...
```

`multifunctionality` produces a per-gene TSV ranked by MF score.

**Composes with `gene-set-fetch`.** The default `--background-set` is
`protein_coding_<species>_strict`, fetched from the sibling
[`gene-set-fetch`](../gene-set-fetch/SKILL.md) skill via subprocess and
restricted by Symbol match. The MF computation runs *within* the
restricted universe (N and nᵢ are recomputed over the protein-coding
gene set), not as a post-hoc filter. This matches the conventional usage:
G&P 2011 and ermineJ both compute MF on the protein-coding universe.
Pass `--background-set annotated` to opt out and use every GAF-annotated
gene (includes splice variants, miRNAs, etc. — N is larger but less
comparable across studies).

## Multifunctionality formula

Per Gillis & Pavlidis (2011), for each gene g annotated (via the GO
true-path rule) to a set of GO terms G_g:

```
MF(g) = Σᵢ∈G_g  1 / (nᵢ · (N − nᵢ))
```

where `nᵢ` is the number of genes annotated to term i (after propagation),
and N is the size of the annotated universe (genes with at least one
annotation in the chosen aspect/source). Terms with `nᵢ = N` or `nᵢ = 0`
are degenerate and excluded (the root term `biological_process` has
nᵢ = N and contributes nothing useful).

The raw MF score's absolute value isn't meaningful; only the ordering /
percentile is. The output records both `mf_score` and `mf_percentile`
(0 = least multifunctional, 1 = most).

## Defaults

Per design discussion with the user (2026-05-16):

| Decision | v0.1 default | Rationale |
|---|---|---|
| Aspect | **BP only** | MF score across aspects mixes incommensurable structures; user explicit |
| Evidence codes | **all** | IEA is not lower-quality (see feedback memory); filtering biases toward well-studied genes |
| Annotations | **propagated** (true-path) | required by the formula; G&P 2011 |
| Background | **protein-coding strict** (via `gene-set-fetch protein_coding_<species>_strict`) | MF is conventionally computed within the protein-coding universe; explicitly opt out with `--background-set annotated` |
| Term-size filters | **none** | size limits belong to enrichment, not MF |
| Source | **gaf** (GO Consortium per-species file + locally cached go.obo) | reproducible (date/sha256-pinned) |

## Output schema

| column | meaning |
|---|---|
| `gene_id` | typed gene-product ID (e.g. `UniProtKB:P04637`) |
| `gene_symbol` | gene symbol from the GAF Symbol column |
| `gene_uniprot` | UniProt accession if known |
| `n_annotations` | number of (propagated) BP terms gene is annotated to |
| `mf_score` | raw multifunctionality score |
| `mf_rank` | 1 = most multifunctional |
| `mf_percentile` | (N − rank + 1) / N; near 1.0 = top, near 0 = bottom |
| `species` | `human` or `mouse` |
| `source` | `gaf` |

## Sidecar `.meta.json`

Records every decision that affects the result: GAF date, OBO data-version,
both sha256s, aspect filter, evidence-code filter, number of terms used in
the calculation (after dropping degenerate ones), N (annotated universe
size), tool version. Reproducibility: a reviewer can verify by re-running
with the same GAF and OBO files (sha256-matched).

## Cache layout

```
~/.cache/gene-statistics/
├── multifunctionality__gaf__human__BP__allevidence.tsv
├── multifunctionality__gaf__human__BP__allevidence.meta.json
└── refs/    (shared with gene-annotations if both are installed)
```

## Design contract

1. **No bundled data.** Every fetch is live; cache lives in `~/.cache/`.
2. **Provenance on every artifact.** GAF date, OBO data-version, sha256s
   of the source files, all filter choices.
3. **Fail loud.** Empty annotated universe, degenerate term set, missing
   OBO terms — all exit non-zero with a clear message.
4. **Don't pre-judge evidence quality.** Default to all evidence codes;
   filtering is opt-in. See
   [feedback_iea_not_lower_quality.md](../../../.claude/projects/-Users-pzoot-Dev-skillz/memory/feedback_iea_not_lower_quality.md)
   in user memory.
5. **The output's value is the ordering, not the raw scores.** Always
   emit `mf_rank` and `mf_percentile` alongside `mf_score`.

## References

- Gillis J, Pavlidis P (2011). The Impact of Multifunctional Genes on
  "Guilt by Association" Analysis. *PLoS ONE* 6(2):e17258.
  doi:10.1371/journal.pone.0017258
- Crow M, Pavlidis P, Gillis J (2019). Predictability of human
  differential gene expression. *PNAS* 116(13):6491-6500.
  doi:10.1073/pnas.1802973116 (planned v0.2 op: `de_prior`)
- ermineJ / ermineR: https://github.com/PavlidisLab/ermineR

## Dependencies

- Python 3.9+
- `requests`, `pandas`, `obonet`
