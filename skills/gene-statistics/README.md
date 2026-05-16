# gene-statistics

Per-gene meta-statistics for honest interpretation of genomic analyses.

v0.1 ships `multifunctionality` (Gillis & Pavlidis 2011); v0.2 will add
the Differential Expression Prior (Crow, Pavlidis, Gillis 2019).

See [`SKILL.md`](SKILL.md) for the full design contract.

## Quick start

```bash
# Per-gene multifunctionality score for all human BP-annotated genes
python scripts/multifunctionality.py

# Mouse
python scripts/multifunctionality.py --species mouse

# Force re-fetch / re-compute
python scripts/multifunctionality.py --refresh
```

The output TSV is ranked: row 1 = most multifunctional gene in the species.

## Why it matters

Genes annotated to many GO terms (TP53, BRCA1, MYC, etc.) show up as top
hits in almost every guilt-by-association, enrichment, or DE analysis —
not because they're the answer to your specific question, but because
they're annotated everywhere. Flagging them via this score lets you
distinguish "this gene was already a usual suspect" from "this gene is
specifically implicated".

## Tests

```bash
.venv/bin/pytest tests/             # cache-only, fast
.venv/bin/pytest tests/ --network   # adds live recomputation tests
```
