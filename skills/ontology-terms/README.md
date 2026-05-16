# ontology-terms

Focused ontology operations — immediate parents, immediate children,
definition, and free-text search — across multiple sources (OLS at EBI,
Gemma's annotations API). Provenance-stamped outputs in a user cache.

See [`SKILL.md`](SKILL.md) for the full design contract and trigger phrases.

## Quick start

```bash
# Immediate parents of apoptotic process (GO:0006915), from OLS
python scripts/ontology.py parents GO:0006915

# Same, but from Gemma (lab-alignment use case)
python scripts/ontology.py parents GO:0006915 --source gemma

# Children of a MONDO term using full URI
python scripts/ontology.py children http://purl.obolibrary.org/obo/MONDO_0000408

# Term definition + label
python scripts/ontology.py definition MP:0001262

# Search the Human Phenotype Ontology for hippocampus-related terms
python scripts/ontology.py search hippocampus --ontology hp --limit 25
```

Each call prints the path of the produced TSV to stdout. A sidecar
`.meta.json` lives next to every TSV.

## Output schema

| column | meaning |
|---|---|
| `term_id` | compact form (`GO:0006915`) |
| `term_uri` | full OBO URI |
| `term_label` | human-readable name |
| `ontology` | ontology slug |
| `relation` | `is_a`/`part_of`/etc. for parents/children; otherwise op name |
| `source` | `ols` or `gemma` |

Plus operation-specific columns: `definition` for `definition`, `score` for `search`.

## Dependencies

- Python 3.9+
- `requests`, `pandas`

## Tests

```bash
.venv/bin/pytest tests/             # cache-only, fast, no network
.venv/bin/pytest tests/ --network   # adds live-fetch smoke tests
```

Tests model the gene-set-fetch suite: schema/meta integrity, term-ID format,
known-term sanity (e.g. parents of `GO:0006915 apoptotic process` must include
the canonical parent), and source-agreement spot checks.
