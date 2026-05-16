# gene-annotations

Bidirectional gene ↔ GO term annotation lookups with default child-propagation,
authoritative sources only (GOA via QuickGO, NCBI gene2go), and full
provenance per call.

See [`SKILL.md`](SKILL.md) for the full design contract.

## Quick start

```bash
# Genes annotated to apoptosis (GO:0006915), including descendants
python scripts/annotate.py genes_with_annotation GO:0006915

# Only directly annotated (no descendants)
python scripts/annotate.py genes_with_annotation GO:0006915 --direct

# GO annotations for TP53 (symbol resolved to UniProt automatically)
python scripts/annotate.py annotations_of_gene TP53

# Mouse: annotations of insulin
python scripts/annotate.py annotations_of_gene Ins1 --species mouse

# Use GAF (GO Consortium per-species file) instead of GOA's REST
python scripts/annotate.py genes_with_annotation GO:0006915 --source gaf
```

Each call prints the path of the produced TSV to stdout. Sidecar `.meta.json`
next to every TSV records source URL, propagation flag, evidence codes,
species, sha256s.

## Why Gemma isn't a default option

Per lab convention recorded in skill memory: Gemma is authoritative for its
own dataset curation, but it's a *republisher* of upstream GO annotations
rather than the source of record. For gene-GO annotations the canonical
sources are GOA (EBI) and NCBI gene2go. This skill deliberately doesn't
expose Gemma as an option to avoid silently picking the wrong authority.

## Dependencies

- Python 3.9+
- `requests`, `pandas`

## Tests

```bash
.venv/bin/pytest tests/             # cache-only, fast, no network
.venv/bin/pytest tests/ --network   # adds live-fetch smoke tests
```
