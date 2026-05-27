---
name: ontology-terms
description: >
  Ontology term operations (immediate parents, immediate children,
  definition / label, free-text search) for OBO Foundry biomedical
  ontologies — GO, MONDO, MP, HP, CL, UBERON, DOID, etc. Sources: OLS
  at EBI (default), Gemma's annotations API. Writes provenance-stamped
  TSV + meta.json. Accepts compact IDs (GO:0006915) and OBO URIs. Use
  for ontology term hierarchy, "parents of GO:0006915", "children of
  MONDO:0000408", "definition of MP:0001262", or any OBO term lookup.
  Distinct from gene-set / enrichment skills — this is about ontology
  structure itself, not gene-to-term annotations.
---

# ontology-terms

Focused operations on biomedical ontology terms — parents, children,
definitions, and search — across multiple authoritative sources, with full
provenance on every artifact. Built to the same reproducibility-first
contract as `gene-set-fetch`.

## Why this skill exists

Researchers regularly ask questions like "what are the immediate parents of
this GO term?" and reach for whichever API they remember. The answers can
vary by source (OLS vs Gemma vs OntoBee can disagree on which relations are
shown, which propagated terms are included, and which obsolete terms are
hidden) and by date (ontologies are updated frequently). This skill
standardizes the ask, makes the source explicit, and stamps every output
with provenance — so a downstream analysis or figure can be reconstructed.

As with `gene-set-fetch`: the fetcher scripts under `scripts/sources/` are
short, readable, and the *only* thing that produces the data. There is no
hidden cache of upstream artifacts. Students should be able to see how the
sausage is made, even when an AI is making it.

## When to invoke

Trigger this skill whenever a user asks for an ontology term operation:

- "what are the parents of GO:0006915" / "give me the immediate parents of MONDO:0000408"
- "children of CL:0000000" / "what's directly below this term"
- "definition of MP:0001262" / "what does this GO term mean"
- "search HP for hippocampus" / "find GO terms matching 'apoptosis'"
- "ontology lookup" / "OBO term" / phrasings naming GO, MONDO, MP, HP, CL,
  UBERON, DOID, EFO, etc.

Do **not** trigger for:
- Gene-to-term annotation lookups ("what GO terms is BRCA1 annotated with"
  — that's enrichment / annotation; use gget or the relevant skill)
- Constructing a gene set from an ontology term ("genes in pathway X" — see
  the planned `gene-set-fetch` v2 parameterized recipes for GO/KEGG)
- Enrichment analysis itself

## The four operations

```bash
python scripts/ontology.py parents    <term> [--source ols|gemma] [--ontology auto|<ont>]
python scripts/ontology.py children   <term> [--source ols|gemma] [--ontology auto|<ont>]
python scripts/ontology.py definition <term> [--source ols|gemma]
python scripts/ontology.py search     <query> [--source ols|gemma] [--ontology <ont>] [--limit N]
```

`<term>` accepts either form:
- Compact: `GO:0006915`, `MONDO:0000408`, `MP:0001262`
- URI: `http://purl.obolibrary.org/obo/GO_0006915`

`--ontology auto` (default) infers from the term prefix (`GO:` → `go`,
`MONDO:` → `mondo`, etc.). Pass an explicit ontology slug if the prefix is
ambiguous or you want to query a different ontology's view of a cross-listed term.

## Supported ontologies

The skill recognises any ontology reachable via OLS or Gemma. The following
prefixes are in the built-in registry and have URI construction fully handled:

**OBO Foundry (OBO PURL URIs):** GO, MONDO, MP, HP, CL, UBERON, DOID, CHEBI,
PR, OBI, PATO, EMAPA, MA, ZFA, FBBT, WBBT, NBO, SYMP, SO, OBA, NCBITAXON,
RO, BFO, IAO, OGMS

**Non-OBO (EBI URIs):** EFO (`http://www.ebi.ac.uk/efo/EFO_XXXXXXX`)

For any other prefix the skill warns and tries `prefix.lower()` as the ontology
slug — this works for the majority of OLS-hosted ontologies even without an
explicit registry entry. Pass `--ontology <slug>` to override.

## Sources

No source is "the default" universally — each has a sweet spot:

| Source | Best for | Coverage | parents/children semantics | Version pinning |
|---|---|---|---|---|
| `ols` | general use; parents/children/definition with explicit ontology version | every OBO ontology and many beyond (including EFO) | **immediate only** | yes — version + version IRI recorded per call |
| `gemma` | lab alignment with Gemma; strong free-text search across all loaded ontologies | GO, MONDO, MP, HP, CL, UBERON, EFO, OBI, CHEBI, DOID, and others loaded in Gemma | **transitive (propagated)** | no per-term version exposed |
| `obo` | audit-grade reproducibility; offline use | one OBO ontology per call | **immediate only** | YES — data-version embedded in file; downloaded bytes hashed |
| `ontobee` | SPARQL flexibility; cross-ontology queries | every OBO Foundry ontology loaded into OntoBee's triplestore | **mix of immediate + some transitive** (depends on what subClassOf assertions exist in the loaded graphs) | partial — "snapshot" but no clean version string |

Semantic differences matter when comparing results across sources. The `obo`
source is the most reproducible (the data-version is in the file, the file's
sha256 is in the meta), but you must accept its release date. The `ols` source
gives explicit immediate-only relations with a clear ontology version pinned.
`gemma` returns propagated relations (use only if you want that). `ontobee`
returns whatever the loaded graphs assert (use for SPARQL flexibility, not
for clean semantics).

## Output schema

Every operation writes a TSV with the standard columns:

| column | meaning |
|---|---|
| `term_id` | compact form (e.g. `GO:0006915`) |
| `term_uri` | full OBO URI (e.g. `http://purl.obolibrary.org/obo/GO_0006915`) |
| `term_label` | human-readable name (e.g. `apoptotic process`) |
| `ontology` | ontology slug (e.g. `go`, `mondo`) |
| `relation` | for parents/children: `is_a`, `part_of`, etc.; otherwise the operation name (`definition`, `search`) |
| `source` | which source produced this row (`ols`, `gemma`) |

The `definition` operation adds a `definition` column (the text definition).
The `search` operation adds a `score` column (source-specific relevance).

## Sidecar provenance — the `.meta.json`

Same contract as gene-set-fetch. Every TSV has a sidecar with:

```json
{
  "operation": "parents",
  "input_term_id": "GO:0006915",
  "input_term_uri": "http://purl.obolibrary.org/obo/GO_0006915",
  "ontology": "go",
  "source": "ols",
  "source_url": "https://www.ebi.ac.uk/ols4/api/ontologies/go/terms/.../parents",
  "source_version": "OLS4 (current); fetched 2026-05-16",
  "source_sha256": "...",
  "output_sha256": "...",
  "fetched_at": "2026-05-16T...",
  "n_rows": 3,
  "tool_version": "ontology-terms 0.1.0"
}
```

`source_sha256` hashes the raw upstream JSON response. `output_sha256` hashes
the TSV. Downstream consumers can verify both.

## Cache layout

```
~/.cache/ontology-terms/
├── parents__ols__GO_0006915__go.tsv
├── parents__ols__GO_0006915__go.meta.json
├── search__gemma__hippocampus__hp.tsv
├── search__gemma__hippocampus__hp.meta.json
└── …
```

Cache key includes the operation, source, term/query, and ontology — so a
query in a different ontology or against a different source goes to its own
cache file. `--refresh` forces re-fetch.

## Dependencies

- Python 3.9+
- `requests`, `pandas` (always)
- `obonet` (only when `--source obo`)
- `SPARQLWrapper` is installed but not strictly required (OntoBee source uses raw `requests`)

## Design contract (read before extending)

1. **Canonical, durable sources only.** OLS (EBI) and Gemma (Pavlab) are
   institutionally hosted and operationally stable. New sources must clear
   the same bar — well-documented REST API, institutional host, no JS-only
   download paths.
2. **No bundled data.** No committed term lists, no pickled hierarchy
   snapshots. Every operation hits the live source. Cache lives in the
   user's filesystem.
3. **Provenance on every artifact.** Sidecar `.meta.json` is mandatory.
   sha256 the raw upstream JSON AND the output TSV.
4. **Fail loud.** Network error, schema drift, ambiguous term ID, unknown
   ontology — all exit non-zero with a clear message naming the source
   module to inspect.
5. **The source scripts are the documentation.** Every source under
   `scripts/sources/` is short and readable end-to-end by a junior researcher.
   One file per upstream source.
6. **Term ID is the canonical key.** When composing across sources, join
   on `term_id` (compact form). The URI form is derived.
7. **Be nice to APIs.** Identify ourselves with a User-Agent. Cache aggressively.
   Honor 429 / Retry-After. Don't burst-retry.

## Adding a new source

1. Add `scripts/sources/<name>.py` with module-level functions
   `parents(term_id, ontology) → DataFrame`, `children(...)`,
   `definition(...)`, `search(query, ontology, limit)`.
2. Update the source registry in `scripts/ontology.py` so the new name is
   accepted on `--source`.
3. Update the source comparison table in this file and in `README.md`.
4. Add a known-term test in `tests/test_known_terms.py` (e.g. parents of
   `GO:0006915` from your source must include `GO:0012501` or another
   well-known parent).

## References

- OLS4 (EBI Ontology Lookup Service): https://www.ebi.ac.uk/ols4/
- OLS API docs: https://www.ebi.ac.uk/ols4/help
- Gemma REST API: https://gemma.msl.ubc.ca/rest/v2/
- OBO Foundry: http://www.obofoundry.org/
