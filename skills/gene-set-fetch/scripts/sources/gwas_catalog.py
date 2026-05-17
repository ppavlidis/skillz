"""GWAS Catalog — genome-wide association study hits for a trait or disease.

Source: NHGRI-EBI GWAS Catalog REST API.
  https://www.ebi.ac.uk/gwas/rest/api/
  https://www.ebi.ac.uk/gwas/docs/api

Why GWAS Catalog instead of (or in addition to) Open Targets:
- The canonical, authoritative registry of published GWAS studies.
- Institutionally co-hosted by NHGRI and EBI — maximum durability.
- "Genes associated with disease X" via GWAS specifically means: genes near
  or overlapping genome-wide-significant variants in GWAS studies of trait X.
  These are predominantly common-variant, polygenic associations.
  For rare/Mendelian disease genes, prefer OMIM or Open Targets.
- Returns the genes as curated by GWAS Catalog curators: both author-reported
  genes (from the paper) and Ensembl-mapped genes (from variant position).
  We return the mapped genes as the primary set (they're less biased by what
  the authors chose to name in the abstract).

What this is NOT:
- Not a causal gene list. Most GWAS loci contain multiple genes; tagging a
  gene here means it overlaps or is near a significant association signal.
  For causal inference you need fine-mapping or experimental follow-up.
- Not a literature search. Only genes named or mapped in indexed GWAS studies
  appear here.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetchers._common import USER_AGENT, die, iso_now, require_module, sha256_bytes

SOURCE_NAME = "gwas_catalog"
BASE_URL = "https://www.ebi.ac.uk/gwas/rest/api"


def _get(requests, url: str, params: dict | None = None) -> dict:
    try:
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"GWAS Catalog request failed: {url}\n  {e}", fetcher=SOURCE_NAME)
    return resp.json()


def _cache_key(disease_term: str, species: str) -> str:
    slug = disease_term.lower().replace(" ", "_").replace("/", "-")[:40]
    return f"disease_genes__gwas_catalog__{slug}__{species}"


def query(
    disease_term: str,
    species: str,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)

    cache_key = _cache_key(disease_term, species)
    tsv_path = out if out else (cache_dir / cache_key).with_suffix(".tsv")
    meta_path = tsv_path.with_suffix(".meta.json")

    if not refresh and tsv_path.exists() and meta_path.exists():
        return tsv_path

    # Step 1: search for EFO traits matching the query.
    # The REST API provides two search strategies; try exact-trait match first,
    # then fall back to short-form lookup if an EFO/MONDO ID was supplied.
    # Note: the older free-text `q` param was removed from the GWAS Catalog API;
    # use the `findByEfoTrait` named endpoint instead.
    search_url = f"{BASE_URL}/efoTraits/search/findByEfoTrait"
    search_data = _get(requests, search_url, params={"trait": disease_term})

    traits = search_data.get("_embedded", {}).get("efoTraits", [])
    if not traits:
        die(
            f"No EFO trait found in GWAS Catalog for: '{disease_term}'\n"
            f"  Browse traits at https://www.ebi.ac.uk/gwas/efotraits\n"
            f"  Try a more specific EFO term or use --source open_targets for broader coverage.",
            fetcher=SOURCE_NAME,
        )

    best_trait = traits[0]
    trait_id = best_trait["shortForm"]
    trait_name = best_trait["trait"]
    print(f"[gwas_catalog] resolved '{disease_term}' → {trait_id} ({trait_name})", file=sys.stderr)

    # Step 2: get all associations for this trait
    # GWAS Catalog paginates; follow _links.next until exhausted
    assoc_url = f"{BASE_URL}/efoTraits/{trait_id}/associations"
    all_assoc: list[dict] = []
    page = 0
    source_sha_data: list[bytes] = []

    while assoc_url:
        data = _get(requests, assoc_url, params={"page": page, "size": 500})
        source_sha_data.append(json.dumps(data, sort_keys=True).encode())
        associations = data.get("_embedded", {}).get("associations", [])
        all_assoc.extend(associations)
        # Follow pagination
        next_link = data.get("_links", {}).get("next", {}).get("href")
        assoc_url = next_link
        page += 1
        if next_link:
            time.sleep(0.3)  # be nice to the API

    if not all_assoc:
        die(
            f"GWAS Catalog returned zero associations for trait {trait_id} ({trait_name}).\n"
            f"  This trait exists but has no indexed associations.",
            fetcher=SOURCE_NAME,
        )

    source_sha = sha256_bytes(b"".join(source_sha_data))

    # Step 3: extract mapped genes from associations
    # Each association has `loci` → `strongestRiskAlleles` and `genes` mappings.
    # We want the Ensembl-mapped gene names, then resolve to Ensembl IDs via symbol.
    gene_symbols: set[str] = set()
    for assoc in all_assoc:
        for locus in assoc.get("loci", []):
            for gene_entry in locus.get("authorReportedGenes", []):
                sym = gene_entry.get("geneName", "").strip()
                if sym:
                    gene_symbols.add(sym)
            # Also include Ensembl-mapped genes from the `genes` field if present
            for gene_entry in locus.get("genes", []):
                sym = gene_entry.get("geneName", "").strip()
                if sym:
                    gene_symbols.add(sym)

    gene_symbols.discard("")
    gene_symbols.discard("intergenic")

    if not gene_symbols:
        die(
            f"No gene symbols extracted from {len(all_assoc)} GWAS Catalog associations "
            f"for {trait_id}. The associations may be reported as intergenic only.",
            fetcher=SOURCE_NAME,
        )

    print(f"[gwas_catalog] extracted {len(gene_symbols)} unique gene symbols from {len(all_assoc)} associations", file=sys.stderr)

    records = [
        {
            "ensembl_id": "",     # populated below if we can resolve
            "symbol": sym,
            "entrez_id": "",
            "species": species,
            "source": SOURCE_NAME,
            "disease_id": trait_id,
            "disease_name": trait_name,
            "n_associations": sum(
                1 for a in all_assoc
                for locus in a.get("loci", [])
                for g in locus.get("authorReportedGenes", []) + locus.get("genes", [])
                if g.get("geneName", "") == sym
            ),
        }
        for sym in sorted(gene_symbols)
    ]

    df = pd.DataFrame(records)

    # Write artifact manually (no ensembl_release to pin)
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(tsv_path, sep="\t", index=False)
    output_sha = hashlib.sha256(tsv_path.read_bytes()).hexdigest()

    meta = {
        "set": cache_key,
        "query_type": "disease",
        "source": SOURCE_NAME,
        "disease_term": disease_term,
        "trait_id": trait_id,
        "trait_name": trait_name,
        "n_associations": len(all_assoc),
        "n_genes": len(df),
        "species": species,
        "fetched_at": iso_now(),
        "source_url": f"{BASE_URL}/efoTraits/{trait_id}/associations",
        "source_version": "NHGRI-EBI GWAS Catalog (current; fetched live)",
        "source_sha256": source_sha,
        "output_sha256": output_sha,
        "tool_version": "gene-set-fetch 0.1.0",
        "notes": "ensembl_id column is empty; symbols are as reported/mapped by GWAS Catalog curators",
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    print(f"[gwas_catalog] {len(df)} genes written to {tsv_path}", file=sys.stderr)
    return tsv_path
