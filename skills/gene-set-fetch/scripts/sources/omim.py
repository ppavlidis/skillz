"""OMIM — Online Mendelian Inheritance in Man, disease-gene associations.

Source: OMIM REST API.
  https://www.omim.org/api

Why OMIM for disease-gene:
- The gold standard for Mendelian (single-gene) disease-gene associations.
- Curated manually by OMIM editors — high precision for rare disease.
- Not suitable for complex traits / GWAS (use gwas_catalog or open_targets).

API key requirement:
  A free OMIM API key is required. Register at https://www.omim.org/api.
  The key is read from:
    1. OMIM_API_KEY environment variable (if set)
    2. macOS Keychain: tries service names 'OMIM_API_KEY', 'omim', 'omim-api-key'
       in order, using `security find-generic-password -s <name> -w`.
  To store your key:
    security add-generic-password -s OMIM_API_KEY -a <your-email> -w <your-key>

Gene coverage:
  OMIM returns the MIM number(s) for disease entries. We fetch the gene
  associated with each phenotype entry. Some OMIM entries list multiple genes
  (digenic) or no gene (phenotype only); those with no gene mapping are excluded.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetchers._common import USER_AGENT, die, iso_now, require_module, sha256_bytes

SOURCE_NAME = "omim"
BASE_URL = "https://api.omim.org/api"


def _get_api_key() -> str:
    key = os.environ.get("OMIM_API_KEY", "").strip()
    if key:
        return key
    for entry in ["OMIM_API_KEY", "omim", "omim-api-key"]:
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", entry, "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    die(
        "No OMIM API key found.\n"
        "  Register at https://www.omim.org/api and either:\n"
        "    - set the OMIM_API_KEY environment variable (any OS), or\n"
        "    - (macOS) store it in the Keychain:\n"
        "        security add-generic-password -s OMIM_API_KEY -a <email> -w <key>",
        fetcher=SOURCE_NAME,
    )


def _get(requests, endpoint: str, params: dict) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    params = dict(params)
    params["format"] = "json"
    params["apiKey"] = _get_api_key()
    try:
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"OMIM API request failed: {url}\n  {e}", fetcher=SOURCE_NAME)
    return resp.json()


def _cache_key(disease_term: str, species: str) -> str:
    slug = disease_term.lower().replace(" ", "_").replace("/", "-")[:40]
    return f"disease_genes__omim__{slug}__{species}"


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

    # Step 1: search for phenotype entries matching the term
    search_data = _get(requests, "entry/search", {
        "search": disease_term,
        "filter": "phenotype",
        "start": 0,
        "limit": 50,
    })

    entries = (
        search_data.get("omim", {})
        .get("searchResponse", {})
        .get("entryList", [])
    )
    if not entries:
        die(
            f"No OMIM entries found for: '{disease_term}'\n"
            f"  Try a more specific Mendelian disease name, or use --source open_targets\n"
            f"  for complex/multifactorial traits.",
            fetcher=SOURCE_NAME,
        )

    mim_numbers = [str(e["entry"]["mimNumber"]) for e in entries]
    print(f"[omim] found {len(mim_numbers)} phenotype entries for '{disease_term}'", file=sys.stderr)

    # Step 2: fetch gene-map entries for each MIM number
    # OMIM allows up to 20 MIM numbers per request
    all_raw: list[bytes] = []
    records = []
    batch_size = 20
    for i in range(0, len(mim_numbers), batch_size):
        batch = mim_numbers[i:i + batch_size]
        entry_data = _get(requests, "entry", {
            "mimNumber": ",".join(batch),
            "include": "geneMap",
        })
        raw_bytes = json.dumps(entry_data, sort_keys=True).encode()
        all_raw.append(raw_bytes)

        for item in entry_data.get("omim", {}).get("entryList", []):
            entry = item.get("entry", {})
            mim_num = entry.get("mimNumber", "")
            title = entry.get("titles", {}).get("preferredTitle", "")
            gene_map = entry.get("geneMap", {})
            gene_symbol = gene_map.get("geneSymbols", "").split(",")[0].strip()
            ensembl_id = ""  # OMIM doesn't return Ensembl IDs directly
            entrez_id = str(gene_map.get("ncbiGeneIds", [""])[0]) if gene_map.get("ncbiGeneIds") else ""

            if gene_symbol:
                records.append({
                    "ensembl_id": ensembl_id,
                    "symbol": gene_symbol,
                    "entrez_id": entrez_id,
                    "species": species,
                    "source": SOURCE_NAME,
                    "disease_id": f"OMIM:{mim_num}",
                    "disease_name": title,
                    "omim_mim_number": str(mim_num),
                })
        if i + batch_size < len(mim_numbers):
            time.sleep(0.5)  # be polite; OMIM rate limits at ~4 req/sec

    source_sha = sha256_bytes(b"".join(all_raw))

    if not records:
        die(
            f"OMIM returned no gene-map entries for {len(mim_numbers)} phenotype entries "
            f"matching '{disease_term}'. The phenotypes may be unlinked to a gene.",
            fetcher=SOURCE_NAME,
        )

    df = (
        pd.DataFrame(records)
        .drop_duplicates(subset=["symbol"])
        .reset_index(drop=True)
    )

    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(tsv_path, sep="\t", index=False)
    output_sha = hashlib.sha256(tsv_path.read_bytes()).hexdigest()

    meta = {
        "set": cache_key,
        "query_type": "disease",
        "source": SOURCE_NAME,
        "disease_term": disease_term,
        "n_omim_entries": len(mim_numbers),
        "n_genes": len(df),
        "species": species,
        "fetched_at": iso_now(),
        "source_url": f"{BASE_URL}/entry/search",
        "source_version": "OMIM (current; fetched live)",
        "source_sha256": source_sha,
        "output_sha256": output_sha,
        "tool_version": "gene-set-fetch 0.1.0",
        "notes": "ensembl_id is empty; entrez_id and symbol from OMIM gene map; deduplicated by symbol",
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    print(f"[omim] {len(df)} genes written to {tsv_path}", file=sys.stderr)
    return tsv_path
