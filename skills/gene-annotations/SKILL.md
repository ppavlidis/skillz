---
name: gene-annotations
description: >
  Bidirectional gene ↔ GO term annotation lookups: GO term → genes
  (child-propagated by default; --direct overrides), gene → GO terms.
  Sources: GOA via QuickGO at EBI, NCBI gene2go. Use for "GO terms for
  BRCA1", "genes annotated to GO:0006915", "genes in apoptosis GO term",
  "GO annotations for TP53". Distinct from ontology-terms (ontology
  structure) and gene-set-fetch (named catalogs).
---

# gene-annotations

Authoritative gene ↔ GO term annotation lookups, in both directions, with
default child-propagation and full provenance.

## Why this skill exists

Asking "which genes are annotated to apoptosis in GO" or "what GO terms
does TP53 have" sounds simple but bites you in three ways: (1) most casual
sources don't propagate (they return only direct annotations, leaving out
genes annotated to more-specific descendants); (2) gene-identifier
mismatches (symbol vs UniProt vs Entrez vs Ensembl, plus aliases); (3)
no clear version or evidence-code recorded. This skill addresses all three:
propagation is the default, gene IDs are resolved transparently from
multiple input formats, and every artifact stamps the source URL, evidence
codes, and propagation flag.

## When to invoke

Trigger this skill for any question about gene-to-GO annotation:

- "what GO terms is BRCA1 annotated with"
- "give me the genes in the apoptosis GO term"
- "list genes annotated to GO:0006915"
- "GO annotations for TP53" / "functional annotations of INS"
- "which biological processes is gene X involved in"

Do **not** trigger for:
- Ontology *structure* questions (parents, children, definitions, search) —
  see `ontology-terms`
- Named gene-set catalogs (TF lists, protein-coding sets) — see `gene-set-fetch`
- Enrichment analysis itself — see `gget enrichr` or the `enrichment-analysis`
  skill (planned)

## Operations

```bash
python scripts/annotate.py genes_with_annotation <go_term> [--source goa|gene2go] [--species human|mouse] [--direct] [--limit N]
python scripts/annotate.py annotations_of_gene  <gene>    [--source goa|gene2go] [--species human|mouse] [--direct]
```

- `<go_term>` — compact form (`GO:0006915`) or full OBO URI.
- `<gene>` — accepts any of:
  - UniProtKB accession with prefix (`UniProtKB:P04637`)
  - HGNC symbol (`TP53`)
  - Ensembl gene ID (`ENSG00000141510`)
  - Entrez gene ID (`7157`, plain digits)
  - Other prefixed forms QuickGO recognizes (`ENSEMBL:`, `RNAcentral:`, …)
  - The skill resolves symbols via the UniProt REST API to UniProt accessions.
- `--direct` disables child propagation; default is propagated.
- `--species` defaults to `human`.

## Sources

| Source | Best for | Propagation | Evidence detail | Coverage |
|---|---|---|---|---|
| `goa` (default) | general use; richest pipeline coverage; one-shot | server-side via QuickGO `goUsage=descendants`; client-side via QuickGO `/ancestors` for `annotations_of_gene` | rich (IEA, IDA, EXP, ECO codes) | every GOA-supported species |
| `gaf` | offline / reproducible / version-pinned; smaller curated subset | client-side via locally cached `go.obo` (obonet) | rich | per-species GAF files (human: goa_human; mouse: mgi) |

**Note on NCBI gene2go:** as of 2026, NCBI's gene2go.gz is ~1.3 GB compressed
(3.3 GB uncompressed) due to bulk electronic-inference (IEA) growth — not
practical for casual lookup. The `gaf` source uses the GO Consortium's
per-species GAF files (~15 MB each), which contain the same annotations
filtered to one species, hosted at https://current.geneontology.org/annotations/.
For users who specifically need NCBI Entrez-keyed annotations, the gene2go
file can be parsed manually — but for almost everyone, GAF is the right
choice.

**Notably absent: Gemma.** Per the lab convention recorded in memory, Gemma
is *not* authoritative for upstream gene-GO annotations (it's a downstream
republisher of GOA data); we deliberately don't list `gemma` as a default
or even optional source here. If a user explicitly wants Gemma's view of
GO annotations, they should construct that query manually against the
Gemma API rather than have this skill pretend Gemma is authoritative.

## Output schema

Every operation writes a TSV with:

| column | meaning |
|---|---|
| `gene_id` | canonical input gene ID — `UniProtKB:X` for GOA, Entrez integer for gene2go |
| `gene_symbol` | resolved gene symbol |
| `gene_uniprot` | UniProt accession (when known) |
| `gene_entrez` | Entrez ID (when known) |
| `term_id` | GO term in compact form |
| `term_label` | GO term name |
| `term_aspect` | `biological_process` / `molecular_function` / `cellular_component` |
| `evidence_code` | GO evidence code (`IEA`, `IDA`, `EXP`, etc.) |
| `qualifier` | annotation qualifier (`involved_in`, `enables`, `part_of`, `NOT`, etc.) |
| `propagated` | `true` if the annotation came via a descendant/ancestor; `false` if direct |
| `species` | `human`, `mouse`, etc. |
| `source` | which source produced the row (`goa`, `gene2go`) |

## Sidecar provenance — the `.meta.json`

```json
{
  "operation": "genes_with_annotation",
  "source": "goa",
  "species": "human",
  "taxon_id": 9606,
  "input": "GO:0006915",
  "input_resolved": "GO:0006915",
  "propagated": true,
  "n_rows": 5526,
  "fetched_at": "2026-05-16T...",
  "source_url": "https://www.ebi.ac.uk/QuickGO/services/annotation/search?...",
  "source_version": "QuickGO (current); fetched live",
  "source_sha256": "...",
  "output_sha256": "...",
  "tool_version": "gene-annotations 0.1.0"
}
```

## Cache layout

```
~/.cache/gene-annotations/
├── genes_with_annotation__goa__GO_0006915__human__propagated.tsv
├── genes_with_annotation__goa__GO_0006915__human__propagated.meta.json
├── annotations_of_gene__goa__TP53__human__propagated.tsv
└── …
```

## Dependencies

- Python 3.9+
- `requests`, `pandas`
- `gzip` (stdlib) for gene2go parsing

## Design contract

1. **Authoritative sources only.** GOA (EBI) and NCBI gene2go for v0.1.
   Gemma is *not* a default source for this skill — it's a republisher,
   not authoritative. See the project memory
   `feedback_gemma_as_curator_not_authority.md` for rationale.
2. **No bundled data.** Every fetch is live; cache lives in `~/.cache/`.
3. **Provenance on every artifact.** sha256 input AND output, source URL,
   propagation flag, species/taxon, evidence codes preserved.
4. **Fail loud.** Network errors, unresolvable gene symbols, taxonomically
   ambiguous queries — all exit non-zero with clear messages.
5. **Propagation is the default.** Most users mean "give me apoptosis
   genes" to include descendants. Add `--direct` to opt out.
6. **Evidence codes are preserved.** Many downstream analyses filter on
   `IEA` (electronic) vs experimental (`IDA`, `EXP`, etc.). The output
   keeps the per-annotation evidence so the user can filter.

## Composing with other skills

- **`ontology-terms`** — for clean GO term resolution (definition, synonyms)
  before invoking this skill.
- **`gene-set-fetch`** — the gene IDs this skill emits can be intersected
  with named sets (e.g. "TFs annotated to apoptosis" = intersect
  `genes_with_annotation GO:0006915` with `tfs_human_lambert2018`).

### Preferred pattern: ontology-first for concept queries

When a user asks "does gene X have a function relating to concept Y?" the
preferred strategy is **ontology-first**, not keyword search over annotation
labels:

1. Use `ontology-terms search` to find the GO term(s) for concept Y
   (e.g. "carbohydrate biosynthetic process" → `GO:0016051`).
2. Use `ontology-terms children` to collect all descendant terms — this
   defines the concept precisely including specializations.
3. Call `annotations_of_gene` on gene X (propagated, the default).
4. Intersect the gene's annotation term IDs with the descendant set.

This is more complete than keyword-searching annotation labels: a gene
annotated specifically to "hexose biosynthetic process" (`GO:0019319`,
a child of carbohydrate biosynthetic process) would be missed by a label
search for "carbohydrate" but correctly caught by the ontology-first
intersection.

## References

- GOA / QuickGO: https://www.ebi.ac.uk/QuickGO/
- QuickGO API docs: https://www.ebi.ac.uk/QuickGO/api/
- NCBI gene2go: https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene2go.gz
- GO evidence codes: http://geneontology.org/docs/guide-go-evidence-codes/
- UniProt REST (for symbol resolution): https://www.uniprot.org/help/api
