---
name: provenance-stamp
description: >
  Write and verify *_meta.json provenance sidecars for any analysis artifact.
  Records the sha256 of the artifact, sha256s of any inputs, the URL it
  came from, the DOI or resource identifier, the upstream version/date, the
  download timestamp, and arbitrary analysis parameters — everything needed
  to reproduce or audit the artifact later. Two modes: import as a library
  into any Python script; call as a CLI to stamp existing files. The sidecar
  format is intentionally compatible with the meta.json files produced by
  the gene-set-fetch, gene-annotations, gene-statistics, and ontology-terms
  skills. Use this skill whenever a user asks how to record provenance,
  stamp an artifact, add sha256 tracking, create a .meta.json, or audit
  whether an artifact is still intact.
---

# provenance-stamp

Every analysis artifact — a downloaded file, a processed TSV, a model
output — should ship with a `.meta.json` sidecar that answers:
- **What**: sha256 of the artifact and any inputs used to produce it
- **Where**: URL the source data came from; DOI or resource identifier
- **When**: download date (fetched_at) vs. processing date (stamped_at)
- **Which version**: the upstream's own version/date string
- **How**: analysis parameters (species, aspect, thresholds, …)

Without this, "where did this number come from" requires archaeology.
With it, it's a one-grep question.

## Usage

### As a library (add to any artifact-producing script)

```python
import sys
sys.path.insert(0, "/path/to/skills/provenance-stamp/scripts")
from stamp import write_meta

# After saving your artifact:
write_meta(
    "output/gene_set.tsv",
    source_url="https://current.geneontology.org/annotations/goa_human.gaf.gz",
    doi="10.1093/nar/gkac1052",
    data_version="2026-05-01",           # upstream's own version
    fetched_at="2026-05-01T14:23:00Z",   # when we downloaded it
    params={"species": "human", "aspect": "BP"},
    inputs=["refs/go.obo"],              # optional: sha256 inputs too
)
# Writes: output/gene_set.tsv.meta.json
```

### As a CLI

```bash
# Stamp an existing file
python scripts/stamp.py stamp output.tsv \
    --source-url https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene2go.gz \
    --doi 10.1093/nar/gkv1145 \
    --data-version 2026-05-01 \
    --fetched-at 2026-05-01T14:23:00Z \
    --param species human \
    --param aspect BP \
    --input refs/gene2go.gz

# Verify the artifact hasn't changed
python scripts/stamp.py verify output.tsv   # exits 0 on OK, 1 on mismatch

# Show the sidecar
python scripts/stamp.py show output.tsv
```

## Sidecar schema

```json
{
  "artifact":     "gene_set.tsv",
  "sha256":       "a3f7…64 hex chars…",
  "stamped_at":   "2026-05-01T14:25:00Z",
  "fetched_at":   "2026-05-01T14:23:00Z",
  "source_url":   "https://…",
  "doi":          "10.1093/nar/gkac1052",
  "data_version": "2026-05-01",
  "inputs":       { "refs/go.obo": "b8c2…" },
  "params":       { "species": "human", "aspect": "BP" },
  "tool_version": "0.1.0"
}
```

| field | required | meaning |
|---|---|---|
| `artifact` | yes | filename of the stamped artifact |
| `sha256` | yes | hex SHA-256 of artifact bytes |
| `stamped_at` | yes | ISO-8601 UTC — when provenance was recorded |
| `fetched_at` | yes | ISO-8601 UTC — when source was downloaded (= stamped_at if not supplied separately) |
| `tool_version` | yes | provenance-stamp version |
| `source_url` | recommended | URL the artifact was derived from |
| `doi` | recommended | DOI or other persistent identifier for the source |
| `data_version` | recommended | upstream's own version/date string |
| `inputs` | optional | map of input path → sha256 |
| `params` | optional | analysis parameters that affect the output |

## Compatibility

The sidecar format is designed to be a superset of the `.meta.json` files
produced by the sibling bioinformatics skills:

| provenance-stamp field | skill field equivalent |
|---|---|
| `sha256` | `output_sha256` (the `verify()` function accepts both) |
| `stamped_at` | `fetched_at` |
| `source_url` | `source_url`, `gaf_url`, `obo_url` |
| `data_version` | `obo_data_version`, `gaf_date_generated` |

## Integrating into a script — minimal pattern

```python
from pathlib import Path
from stamp import write_meta

def run(args):
    result_df = ...compute...
    out = Path(args.out) / "result.tsv"
    result_df.to_csv(out, sep="\t", index=False)
    write_meta(
        out,
        source_url=SOURCE_URL,
        doi=SOURCE_DOI,
        data_version=version_from_header,
        fetched_at=download_timestamp,
        params=vars(args),
    )
    return out
```

## Dependencies

- Python 3.9+ (stdlib only — no external packages required)

## Design contract

1. **Fail loud.** Missing artifact → FileNotFoundError. Missing sha256 field
   → KeyError. Never silently proceed.
2. **Both timestamps matter.** `fetched_at` records when upstream data was
   obtained; `stamped_at` records when the artifact was processed. They may
   differ when data is cached and reprocessed later.
3. **DOI is first-class.** A URL can rot; a DOI persists. Always record both
   when available.
4. **Extra fields are allowed.** `write_meta(..., pipeline="rnaseq-v2")` just
   works — any kwargs become top-level sidecar fields. This lets downstream
   tools extend the schema without breaking existing sidecars.
5. **verify() accepts both sha256 and output_sha256.** So it works with
   sidecars written by the bioinformatics skills as well as by this tool.
