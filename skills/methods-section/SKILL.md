---
name: methods-section
description: >
  Draft a Methods paragraph from an analysis directory. Runs scan.py to
  extract tools, versions, analysis parameters, and provenance records
  from lockfiles (requirements*.txt, renv.lock, conda environment.yaml,
  pyproject.toml) and *.meta.json sidecars (from the provenance-stamp
  skill). Returns structured JSON that Claude uses to draft a Methods
  paragraph in standard academic style: tool names, version numbers,
  citations, data sources with DOIs, download dates, and key parameters.
  Use this skill whenever a user asks to draft, write, or update the
  Methods section, Materials and Methods, or Data Availability section
  of an analysis.
---

# methods-section

Reproducible science requires an accurate Methods section. This skill
automates the mechanical part — finding which tools at which versions
were used, where data came from, and what parameters were applied — so
the paragraph is grounded in the actual analysis rather than reconstructed
from memory.

## Workflow

```
1. Run scan.py → structured JSON of tools, artifacts, workflows
2. Claude reads the JSON and drafts the paragraph
3. Claude fills in citations for each tool (from memory or DOI lookup)
```

## Step 1: Run the scanner

```bash
python scripts/scan.py /path/to/analysis/directory
```

or with explicit output file:

```bash
python scripts/scan.py /path/to/analysis --out /tmp/scan.json
```

The scanner finds:
- **Lockfiles**: `requirements*.txt`, `renv.lock`, `environment.yml/yaml`,
  `pyproject.toml` — tools, versions, package sources (PyPI, CRAN, Bioconductor, conda)
- **Provenance sidecars** (`*.meta.json`) — sha256, download date (`fetched_at`),
  processing date (`stamped_at`), source URL, DOI, upstream version string, params
- **Workflows**: `Snakefile`, `*.nf`, `*.smk`, `*.wdl`, `*.cwl`
- **Runtime versions**: R (from `renv.lock`), Python (from `renv.lock` Python block or conda yaml)

## Step 2: Draft the Methods paragraph

Using the scan JSON, write a paragraph following this structure:

```
[Data sources] Data were retrieved from [source] (version/date [V], 
downloaded [date], DOI [doi]). [Followed by additional sources.]

[Analysis tools] All analyses were performed using [language + version].
[Key packages] were [task]: [package] v[version] ([citation]). 
[Workflows] The analysis pipeline was implemented as a Snakemake 
(v[version]) workflow.

[Parameters] [Key parameters that affect interpretation].

[Availability] All code is available at [URL].
```

### Example

Given scan output showing pandas 2.0.3, DESeq2 1.40.2 in R 4.3.2, and a
GOA artifact downloaded 2026-05-01 with DOI 10.1093/nar/gkac1052:

> Gene Ontology annotations were retrieved from the GOA database (version
> 2026-05-01, downloaded 2026-05-01, doi:10.1093/nar/gkac1052). Differential
> expression analysis was performed in R v4.3.2 using DESeq2 v1.40.2 (Love
> et al., 2014). Downstream analysis and visualization used Python 3.10 with
> pandas v2.0.3 (pandas development team, 2020). The analysis pipeline is
> fully reproducible; all code and exact dependency versions are recorded in
> the accompanying `renv.lock` and `requirements.txt` files.

## What to cite

For each tool in the scan output, look up the preferred citation:

| source field | how to cite |
|---|---|
| `"source": "CRAN"` | R package citation: `citation("pkgname")` in R |
| `"source": "Bioconductor"` | Bioconductor paper or package vignette citation |
| `"source": "PyPI"` | Package documentation / JOSS / JMLR / Nature Methods paper |
| `"source": "conda"` | Same as PyPI / tool's own documentation |
| `"doi"` in artifact | Use the DOI directly |

Common tools and their preferred citations:
- **DESeq2**: Love MI, Huber W, Anders S (2014). Genome Biol 15:550. doi:10.1186/s13059-014-0550-8
- **ggplot2**: Wickham H (2016). ggplot2: Elegant Graphics for Data Analysis. Springer.
- **pandas**: pandas development team (2020). doi:10.5281/zenodo.3509134
- **scipy**: Virtanen P et al. (2020). Nat Methods 17:261–272. doi:10.1038/s41592-019-0686-2
- **Snakemake**: Mölder F et al. (2021). F1000Research 10:33. doi:10.12688/f1000research.29032.2
- **GOA/QuickGO**: Binns D et al. (2009). Bioinformatics 25(22):3045–3046. doi:10.1093/bioinformatics/btp536

## What the scanner cannot find

- Custom / unpublished scripts not listed in a lockfile — mention them explicitly
- Tool versions installed system-wide (e.g., samtools from PATH) unless in a conda env
- R packages loaded without renv — run `renv::snapshot()` first
- Database access dates not recorded in a `.meta.json` — use provenance-stamp to capture them

## Composing with provenance-stamp

The `*.meta.json` sidecars that methods-section reads are produced by the
[`provenance-stamp`](../provenance-stamp/SKILL.md) skill. For complete
methods provenance:
1. Every data download script should call `write_meta()` from provenance-stamp
2. Every output artifact should be stamped with its inputs, source URL, DOI,
   and data_version
3. methods-section then reads all these sidecars and produces a complete
   data-sources list automatically

## Dependencies

- Python 3.9+ (stdlib only — no external packages required)

## Design contract

1. **No LLM calls in the scanner.** scan.py is pure mechanical extraction —
   fast, deterministic, and auditable. The draft happens in Claude using
   the JSON output.
2. **DOI and fetched_at are first-class.** The scanner surfaces them
   explicitly because a URL can rot but a DOI persists, and "downloaded on"
   is required by many journals.
3. **Handles both provenance-stamp and skill-native sidecars.** The scanner
   accepts both `sha256`/`stamped_at`/`fetched_at` (provenance-stamp format)
   and `output_sha256`/`fetched_at`/`gaf_url` (gene-set-fetch / gene-annotations
   format) — whichever fields are present get surfaced.
4. **Skips .venv, node_modules, __pycache__.** Only project-level lockfiles,
   not transitive dependency lock files from installed environments.
