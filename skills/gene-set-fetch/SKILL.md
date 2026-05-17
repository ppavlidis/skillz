---
name: gene-set-fetch
description: >
  Fetches canonical, named gene sets and ad-hoc parameterized gene sets for
  human and mouse, writing provenance-stamped TSV + sidecar meta JSON to a
  user cache. Named sets (fetch.py): transcription factors (Lambert 2018,
  AnimalTFDB), protein-coding genes (Ensembl biotype or strict three-way
  intersection). Ad-hoc queries (query.py): (1) disease-gene associations —
  "genes associated with Parkinson disease" via Open Targets (default, free,
  broad), GWAS Catalog (GWAS hits only), or OMIM (Mendelian, key required);
  do NOT use literature search for these; (2) genomic structural features —
  "genes with head-to-head / bidirectional promoter arrangements on chromosome
  6" via Ensembl BioMart. Use this skill whenever a user asks for a list of
  genes in some category — TFs, protein-coding, "genes associated with disease
  X", "genes arranged head-to-head on chromosome Y", Lambert TFs, AnimalTFDB,
  or any named gene set where reproducibility and source provenance matter.
  Phrasings include: "give me mouse TFs", "human protein-coding genes",
  "genes linked to type 2 diabetes", "GWAS hits for schizophrenia",
  "head-to-head gene pairs on chr6", "bidirectionally transcribed genes".
  Distinct from gget (gene-centric lookups) and gene-annotations (GO term
  annotations). Do NOT use literature search or PubMed text-mining for
  disease-gene sets — if the association isn't in a curated database, say so.
---

# gene-set-fetch

Named gene sets for human and mouse, with provenance. Built for reproducibility-
first analyses: every artifact ships with a sidecar `.meta.json` recording
source URL, version, fetch date, sha256, and the Ensembl release used for ID
normalization. No data is bundled with the skill — every set is fetched live
from the canonical upstream source. If a source breaks, the skill fails loud
with a clear pointer to the responsible fetcher.

## Why this skill exists

Researchers and trainees regularly need answers to "give me the mouse
transcription factors" or "the human protein-coding genes" — and reach for
whichever list a labmate happens to have lying around. Those lists are usually
undated, unsourced, and irreproducible. This skill replaces that pattern with a
single command that fetches the canonical list fresh, writes it with full
provenance, and makes the choice of authority explicit (Lambert 2018 vs
AnimalTFDB; Ensembl biotype vs the strict three-way intersection).

Equally important: students should be able to see how the sausage is made, even
when an AI is making it. The fetcher scripts under `scripts/fetchers/` are
short, readable, and the *only* thing that produces the data. There is no
hidden cache of upstream artifacts. Reading the fetcher tells you exactly which
URL was hit, which columns were parsed, and which filters were applied.

## When to invoke

Trigger this skill for any request that means "produce *the list* of genes in
some named category", including:

**Named sets (use `fetch.py`):**
- "get me [the | a list of] mouse TFs"
- "give me human protein-coding genes" / "the protein-coding background"
- "Lambert TFs" / "Lambert 2018"
- "AnimalTFDB mouse" / "AnimalTFDB transcription factors"
- "intersection of Lambert and AnimalTFDB" / "TFs in both Lambert and AnimalTFDB"
- "strict protein-coding" (Ensembl ∩ HGNC/MGI ∩ GENCODE)
- "the mouse orthologs of Lambert human TFs"

**Ad-hoc disease-gene sets (use `query.py disease`):**
- "genes associated with Parkinson disease"
- "GWAS hits for schizophrenia" / "genes linked to type 2 diabetes"
- "what genes are implicated in Huntington's disease"
- "gene list for OMIM disease XXXXXX"
- Phrases: "disease genes", "genes implicated in", "genes associated with",
  "genes linked to", "GWAS genes for"

**Ad-hoc genomic structural sets (use `query.py genomic`):**
- "head-to-head gene pairs" / "bidirectionally transcribed genes"
- "genes with divergent promoters on chromosome 6"
- "which genes on chr6 are arranged head-to-head"
- Phrases: "head-to-head", "bidirectional promoter", "divergently transcribed"

**Do NOT trigger for:**
- "tell me about gene X" — that's [`gget`](../gget/SKILL.md)
- Gene-to-GO-term annotation lookups — that's [`gene-annotations`](../gene-annotations/SKILL.md)
- Disease-gene queries answered by literature search / PubMed text-mining —
  if it isn't in a curated database (Open Targets, GWAS Catalog, OMIM), report
  that and stop. Do not fall back to summarizing papers.
- Protein-protein interaction neighbors — scope-limited by design (see Future section)

## The set catalog

Every set name maps to a recipe in [`scripts/registry.yaml`](scripts/registry.yaml).
v1 ships these:

| Set name | Species | Source |
|---|---|---|
| `protein_coding_human` | human | Ensembl biotype (via `gget ref`) |
| `protein_coding_human_strict` | human | Ensembl ∩ HGNC ∩ GENCODE |
| `protein_coding_mouse` | mouse | Ensembl biotype (via `gget ref`) |
| `protein_coding_mouse_strict` | mouse | Ensembl ∩ MGI ∩ GENCODE |
| `tfs_human_lambert2018` | human | Lambert et al. 2018 supp table 2 |
| `tfs_human_animaltfdb` | human | AnimalTFDB v4 |
| `tfs_human_union` | human | Lambert ∪ AnimalTFDB |
| `tfs_human_intersection` | human | Lambert ∩ AnimalTFDB |
| `tfs_mouse_animaltfdb` | mouse | AnimalTFDB v4 |
| `tfs_mouse_lambert_orthologs` | mouse | Lambert human TFs → mouse via Ensembl Compara |
| `tfs_mouse_union` | mouse | AnimalTFDB ∪ Lambert-orthologs |
| `tfs_mouse_intersection` | mouse | AnimalTFDB ∩ Lambert-orthologs |

Set algebra joins on `ensembl_id`, normalized to a single Ensembl release
(default 113; override with `--ensembl-release N`).

## How to use it

Two CLIs:

**Named sets:**
```bash
python scripts/fetch.py <set_name> [--ensembl-release N] [--refresh] [--out PATH] [--format tsv|json]
python scripts/fetch.py --list   # show all available set names
```

**Ad-hoc parameterized queries:**
```bash
python scripts/query.py disease <term> [--source open_targets|gwas_catalog|omim]
                                       [--species human|mouse]
                                       [--min-score FLOAT]
                                       [--out PATH] [--refresh]

python scripts/query.py genomic head_to_head [--species human|mouse]
                                              [--chromosome CHR]
                                              [--max-distance N]
                                              [--out PATH] [--refresh]
```

Examples:
```bash
# Disease-gene: genes associated with Parkinson disease (Open Targets, all evidence)
python scripts/query.py disease "Parkinson disease"

# GWAS-only hits for schizophrenia
python scripts/query.py disease "schizophrenia" --source gwas_catalog

# Mendelian: OMIM genes for Huntington's (requires OMIM API key in Keychain)
python scripts/query.py disease "Huntington disease" --source omim

# High-confidence only (Open Targets association score ≥ 0.5)
python scripts/query.py disease "type 2 diabetes" --min-score 0.5

# Head-to-head gene pairs on human chromosome 6, within 1 kb
python scripts/query.py genomic head_to_head --chromosome 6

# All human head-to-head pairs, extended to 2 kb
python scripts/query.py genomic head_to_head --max-distance 2000
```

Behavior:

- Writes the artifact to `~/.cache/gene-set-fetch/<set>__ensembl<N>__<src_ver>.tsv`
  by default (override with `--out`).
- Writes a sidecar `.meta.json` next to it with full provenance.
- Prints the path of the produced TSV to stdout, so callers can grab it
  without parsing other output.
- Reuses an existing cached file unless `--refresh` is passed.
- Fails loud (non-zero exit, clear stderr) if an upstream source is unreachable
  or returns unexpected content — never silently falls back to stale data.

## Output schema

Every set, regardless of source, writes a TSV with these columns:

| column | description |
|---|---|
| `ensembl_id` | Ensembl gene ID (canonical join key, pinned to the release used) |
| `symbol` | Gene symbol as known to Ensembl at the release used |
| `entrez_id` | NCBI Entrez gene ID, where available |
| `species` | `human` or `mouse` |
| `source` | The set name that produced this row (e.g. `tfs_human_lambert2018`) |

Source-specific extras (e.g. Lambert's DBD family, AnimalTFDB family
assignment) are tacked on as additional columns for non-composite sets only.
Composite sets (union, intersection) emit only the standard schema plus a
`sources` column listing which originating sets contributed each row.

## Sidecar provenance — the `.meta.json`

Every TSV is accompanied by a sidecar with the same stem, ending `.meta.json`:

```json
{
  "set": "tfs_human_lambert2018",
  "species": "human",
  "ensembl_release": 113,
  "n_genes": 1639,
  "fetched_at": "2026-05-16T14:23:01Z",
  "source_url": "https://www.cell.com/cms/...",
  "source_version": "Lambert et al. 2018, Cell, supp table 2 (DOI: 10.1016/j.cell.2018.01.029)",
  "source_sha256": "8c1d…",
  "source_durability": "publisher-hosted supplementary file; doi-pinned",
  "output_sha256": "f3a2…",
  "tool_version": "gene-set-fetch 0.1.0",
  "gget_version": "0.29.1"
}
```

`source_sha256` hashes the raw upstream file as fetched — lets you detect
silent upstream changes. `output_sha256` hashes the TSV we wrote — lets
downstream verify they're reading the same bytes the producer emitted.

This is non-negotiable. Any downstream figure or table built from a gene-set-fetch
output should cite the `set` + `ensembl_release` + `source_version` so the
provenance chain stays intact.

## Cache layout

```
~/.cache/gene-set-fetch/
├── tfs_human_lambert2018__ensembl113__lambert2018.tsv
├── tfs_human_lambert2018__ensembl113__lambert2018.meta.json
├── protein_coding_human__ensembl113__ensembl113.tsv
├── protein_coding_human__ensembl113__ensembl113.meta.json
└── …
```

The filename encodes everything that affects content. A stale file cannot
masquerade as fresh because the cache key includes the source version.

## Dependencies

- **Python 3.9+** (helper scripts; uses `from __future__ import annotations` for newer type-hint syntax)
- `pyyaml`, `pandas`, `requests`

The [`gget`](../gget/SKILL.md) skill is *not* a hard dependency in v0.1 — the
fetchers talk directly to Ensembl BioMart REST, EBI HGNC/GENCODE, MGI, and
Ensembl Compara REST. A planned v0.2 step uses `gget.info` to backfill
`entrez_id` and normalize symbols to the requested Ensembl release on every
fetcher's output. At that point `gget` becomes an optional enrichment
dependency.

## Ad-hoc query sources

### Disease-gene associations

| Source | `--source` flag | Best for | Auth | Coverage |
|---|---|---|---|---|
| Open Targets | `open_targets` (default) | Broad disease-gene; aggregates GWAS, pathway, expression, clinical, and other evidence into a single score | None | ~60K diseases; all EFO/MONDO-curated diseases with evidence |
| GWAS Catalog | `gwas_catalog` | GWAS-hit genes only; complex/polygenic traits; published GWAS studies | None | ~5K traits; only traits with indexed GWAS studies |
| OMIM | `omim` | Mendelian (single-gene) rare disease; highest precision for causal genes | Free API key (Keychain) | ~7K phenotype entries |

The key boundary: **do not use literature search** (PubMed, text-mining, summarizing papers) as a substitute for these databases. If none of the three sources have a gene-disease association, that is the answer — not a prompt to read papers.

Scores (Open Targets only): range 0–1 across all evidence types; 0.5+ is a useful threshold for well-supported associations; use `--min-score` to filter.

### Genomic structural features

| Feature | `genomic` arg | Definition | Source |
|---|---|---|---|
| `head_to_head` | `head_to_head` | Two protein-coding genes on opposite strands with TSSs ≤ `--max-distance` bp apart (default 1 kb). These share or nearly share a promoter region. | Ensembl BioMart (protein-coding gene coordinates) |

Output for `head_to_head` includes the paired gene columns (`partner_ensembl_id`, `partner_symbol`, `tss_distance`) so users can filter by either member of each pair or compute downstream statistics.

## Design contract (read this before extending)

1. **Canonical, durable sources only.** When two sources have the same data,
   pick the more canonical and the one more likely to still exist in five
   years. Publisher journal pages beat personal GitHubs. Ensembl/HGNC/MGI/
   GENCODE beat lab websites. DOI/Zenodo/tagged-release URLs beat "latest"
   links. If the only available source is fragile, say so loudly in the
   fetcher's comments AND in the artifact's `.meta.json`.
2. **No bundled data.** This skill must not commit gene lists, ortholog maps,
   or any upstream artifact to the repository. Every fetcher hits the live
   upstream source. If an upstream goes dark, that is the user's reality to
   confront — surface it, don't paper over it.
3. **Provenance on every artifact.** Sidecar `.meta.json` is mandatory. Never
   emit a TSV without one. Hash both inputs and outputs: `source_sha256` for
   the raw upstream file, `output_sha256` for the TSV we wrote.
4. **Fail loud.** Network failure, schema drift in an upstream source, missing
   dependency — all exit non-zero with a clear message naming the fetcher to
   inspect. Silent fallbacks rot quietly.
5. **The fetcher scripts are the documentation.** Every fetcher under
   `scripts/fetchers/` must be readable end-to-end by a junior researcher. No
   clever abstractions, no inheritance chains. One file per upstream source.
   The script *is* the recipe. Include a short comment at the top naming
   which canonical source was chosen and why.
6. **Ensembl ID is the canonical key.** Symbols are unstable across releases;
   Entrez IDs aren't universal. All set algebra joins on `ensembl_id` at a
   pinned release. Other identifiers are derived columns.
7. **No single best source ⇒ support them all + compose.** When the field has
   multiple competing authorities for the same kind of set (TFs from Lambert
   vs AnimalTFDB vs TRRUST; protein-coding calls from Ensembl vs HGNC vs
   GENCODE), ship each as a first-class named set with its own fetcher and
   offer union/intersection composites over them. Don't pick the winner on
   the user's behalf.
8. **Provenance composes.** A composite set's `.meta.json` must include a
   `members[]` array referencing each contributing set's meta — set name,
   `output_sha256`, `source_url`, `source_sha256`, and path to the member's
   `.meta.json`. A downstream consumer can walk the tree from any final
   product back to every upstream raw file.

## Adding a new set

1. Add a recipe block to `scripts/registry.yaml`.
2. If the recipe needs a new source, add a fetcher under `scripts/fetchers/`.
3. Update the catalog table in this file and in `README.md`.
4. If the new set is a composite (union/intersection of others), no new fetcher
   is needed — `compose.py` handles it from the registry recipe.
5. **Run the tests** (`pytest tests/`) after a smoke fetch of the new set
   to confirm the artifact passes schema, ID-format, and (if relevant) the
   known-gene sanity checks. A new fetcher that ships without an
   accompanying live-fetch smoke test should not be merged.

## Tests

```bash
pytest tests/             # cache-only, fast, no network
pytest tests/ --network   # adds live-fetch smoke tests (slower)
```

The default suite validates artifacts already in the user cache. It covers
the silent-failure modes that surfaced during v0.1 development —
particularly **wrong-column-read bugs** (the MGI trailing-tab issue caused
pandas to auto-promote a data field to the row index, silently writing
`"Gene"` into the `ensembl_id` column; the `test_ensembl_ids_have_correct_prefix`
test catches this class of error immediately).

Categories covered:

| Test file | Catches |
|---|---|
| `test_artifact_format.py` | schema drift, missing meta fields, sha256 mismatch, empty TSVs |
| `test_id_format.py` | wrong-column-read; duplicate IDs that break set algebra |
| `test_known_genes.py` | structure-right-semantics-wrong (canonical TFs / housekeepers should be present) |
| `test_compose_invariants.py` | set algebra math, stale provenance paths |

If you add a fetcher, add at least one known-genes entry for the set it
produces.

## Future / v2 candidates

These fit the skill's mandate but need a small redesign before they land:

- **GO term members** — "give me all human genes annotated with `GO:0006915`
  (apoptosis)." Same provenance/cache/output story as the v1 sets, but the *set
  name* needs to be parameterized (a GO term ID + species). Likely change:
  registry recipe template + CLI accepts `--param key=value`.
- **KEGG pathway members** — "all genes in `hsa00010` (glycolysis)." Same
  parameterization story as GO; KEGG REST API is stable.
- **MSigDB / Reactome / WikiPathways** — same shape; pick which authorities to
  support based on user demand.

Explicitly *not* in scope:

- **Protein–protein interaction neighbors** ("all proteins that interact with
  BRCA1"). The major databases (STRING, BioGRID, IntAct, HuRI) disagree
  wildly on edges, score interactions differently, and don't share a clean
  definition of "neighbor" (1-hop? confidence-weighted? directed?).
  Reproducible PPI neighbor lists belong in their own skill with explicit
  per-source recipes — not buried as a fetcher in this one.

## References

- Lambert, S.A. *et al.* "The Human Transcription Factors." *Cell* (2018).
- AnimalTFDB: http://bioinfo.life.hust.edu.cn/AnimalTFDB4/
- Ensembl REST / BioMart: https://rest.ensembl.org/
- Ensembl Compara (homology / orthologs): https://www.ensembl.org/info/genome/compara/
- DIOPT: https://www.flyrnai.org/diopt — not used by default in v0.1
  (no documented public REST API; durability concerns). Consider adding a
  sibling fetcher if your workflow requires DIOPT-specific calls.
- gget: https://github.com/pachterlab/gget
