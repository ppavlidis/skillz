# gene-set-fetch

Named, provenance-stamped gene sets for human and mouse. Built for
reproducibility-first analyses.

The skill answers "give me *the list* of X genes" — transcription factors
(Lambert 2018, AnimalTFDB), protein-coding genes (Ensembl biotype, or strict
three-way intersection against HGNC/MGI and GENCODE), and set-algebra
composites (union, intersection). Distinct from [`gget`](../gget/SKILL.md),
which answers "tell me about *this gene*".

Students and other learners should be able to see how the sausage is made,
even when an AI is making it. The fetcher scripts under
[`scripts/fetchers/`](scripts/fetchers/) are short, readable, and the *only*
thing that produces the data — there is no bundled cache of upstream
artifacts. Reading a fetcher tells you exactly which URL was hit, which
columns were parsed, and which filters were applied.

See [`SKILL.md`](SKILL.md) for the full design contract and trigger phrases.
See [`scripts/registry.yaml`](scripts/registry.yaml) for the set catalog.

## Quick start

```bash
# List available sets
python scripts/fetch.py --list

# Fetch human Lambert 2018 transcription factors
python scripts/fetch.py tfs_human_lambert2018

# Fetch the strict protein-coding set for mouse (Ensembl ∩ MGI ∩ GENCODE)
python scripts/fetch.py protein_coding_mouse_strict

# Intersection of Lambert and AnimalTFDB for human TFs
python scripts/fetch.py tfs_human_intersection

# Force re-fetch (ignore cache)
python scripts/fetch.py tfs_mouse_animaltfdb --refresh

# Use a specific Ensembl release
python scripts/fetch.py protein_coding_human --ensembl-release 112
```

Each call prints the path of the produced TSV to stdout. A sidecar
`.meta.json` lives next to every TSV with full provenance (source URL,
version, fetched_at, sha256, Ensembl release, tool version).

## Output schema

| column | meaning |
|---|---|
| `ensembl_id` | Ensembl gene ID at the pinned release (canonical key) |
| `symbol` | Symbol as known to Ensembl at that release |
| `entrez_id` | NCBI Entrez gene ID, where available |
| `species` | `human` or `mouse` |
| `source` | The set name that produced this row |

Source-specific extras (e.g. Lambert's DBD family) appear as additional
columns for non-composite sets only.

## Dependencies

- Python 3.9+
- `pyyaml`, `pandas`, `requests`
- `gget` is *not* required in v0.1; planned for v0.2 to backfill `entrez_id`
  and normalize symbols to the requested Ensembl release.

## Tests

```bash
.venv/bin/pytest tests/         # default: cache-only, no network, fast
.venv/bin/pytest tests/ --network   # adds live-fetch smoke tests
```

The default suite validates artifacts already in `~/.cache/gene-set-fetch/`:
schema, sidecar completeness, sha256 integrity, ensembl_id format and
uniqueness, known-gene presence (catches structure-right-semantics-wrong
bugs), and composite set-algebra invariants. Empty cache → tests skip
politely with instructions to populate it.

The tests are intentionally framed to surface the silent-failure modes
that bit us during v0.1 development (e.g. MGI's trailing-tab column shift
that wrote `"Gene"` into the ensembl_id column).

## Status

v0.1 — SKILL.md, registry, CLI, fetchers (`lambert2018`, `animaltfdb`,
`ensembl_biomart`, `hgnc`, `mgi`, `gencode`, `ensembl_compara_ortholog_map`),
`compose`, and a 15-test pytest suite that runs in ~1 second.

Validated end-to-end against live upstreams: Lambert (1,637 TFs), Ensembl
BioMart human, HGNC GCS, GENCODE v45, MGI two-file join (21,957 mouse
protein-coding), and the three-way `protein_coding_human_strict`
intersection (19,211 genes).

Currently broken upstream: **AnimalTFDB** (host moved to wchscu.cn and is
behind a JavaScript anti-bot challenge). The fetcher fails loud with
manual-download instructions. Composites that depend on it (`tfs_*_union`,
`tfs_*_intersection` for the TF lines) will therefore also fail until a
workaround is added.
