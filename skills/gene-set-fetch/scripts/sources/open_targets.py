"""Open Targets Platform — disease-gene associations.

Source: Open Targets Platform GraphQL API.
  https://platform.opentargets.org/api
  https://api.platform.opentargets.org/api/v4/graphql

Why Open Targets as the default disease-gene source:
- Free, no API key required.
- Aggregates evidence from GWAS Catalog, UniProt, ChEMBL, ClinVar, Reactome,
  Expression Atlas, and ~10 other databases into a single scored association
  per disease-target pair.
- Uses EFO / MONDO disease IDs (interoperable with ontology-terms skill).
- Returns Ensembl gene IDs natively — no remapping needed.
- Institutionally hosted (Wellcome Sanger / EMBL-EBI / GSK / Biogen consortium).

What this is NOT:
- Not a literature / text-mining search. Associations come from structured
  databases and curation pipelines. If a gene is associated with a disease
  only via PubMed text, it will not appear here unless one of the source
  databases picked it up.
- Not a definitive causal list. Scores aggregate evidence; they do not
  certify causality. Include score in output so the user can filter.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetchers._common import (
    SourceInfo,
    USER_AGENT,
    die,
    iso_now,
    require_module,
    sha256_bytes,
    write_artifact,
)

SOURCE_NAME = "open_targets"
GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"

_META_QUERY = """
query meta {
  meta {
    apiVersion { x y z }
    dataVersion { year month iteration }
  }
}
"""

_SEARCH_QUERY = """
query searchDisease($q: String!) {
  search(queryString: $q, entityNames: ["disease"]) {
    hits {
      id
      name
      entity
    }
  }
}
"""

_ASSOC_QUERY = """
query diseaseTargets($diseaseId: String!, $size: Int!) {
  disease(efoId: $diseaseId) {
    id
    name
    associatedTargets(page: {index: 0, size: $size}) {
      count
      rows {
        target {
          id
          approvedSymbol
          approvedName
        }
        score
      }
    }
  }
}
"""


def _gql(requests, query: str, variables: dict) -> dict:
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"Open Targets GraphQL request failed: {e}", fetcher=SOURCE_NAME)
    data = resp.json()
    if "errors" in data:
        die(f"Open Targets GraphQL errors: {data['errors']}", fetcher=SOURCE_NAME)
    return data["data"]


def _upstream_version(requests) -> dict:
    """Best-effort capture of the Open Targets data + API release backing these
    IDs. Never fails the fetch — returns {} if the meta query is unavailable.

    The Open Targets `dataVersion` (YY.MM) pins the underlying Ensembl gene
    build for the ENSG IDs we emit; recording it answers "which build did
    these IDs come from" without the caller having to guess.
    """
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": _META_QUERY},
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        meta = resp.json()["data"]["meta"]
    except Exception:
        return {}
    dv, av = meta.get("dataVersion") or {}, meta.get("apiVersion") or {}
    out: dict = {}
    if dv.get("year") and dv.get("month"):
        it = f".{dv['iteration']}" if dv.get("iteration") else ""
        out["ot_data_version"] = f"{dv['year']}.{dv['month']}{it}"
    if av.get("x"):
        out["ot_api_version"] = f"{av.get('x')}.{av.get('y')}.{av.get('z')}"
    return out


def _cache_key(disease_term: str, species: str, min_score: float) -> str:
    slug = disease_term.lower().replace(" ", "_").replace("/", "-")[:40]
    score_tag = f"score{int(min_score*100)}" if min_score > 0 else "all"
    return f"disease_genes__open_targets__{slug}__{species}__{score_tag}"


def query(
    disease_term: str,
    species: str,
    min_score: float,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
    max_genes: int = 3000,
) -> Path:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)

    cache_key = _cache_key(disease_term, species, min_score)
    tsv_path = out if out else (cache_dir / cache_key).with_suffix(".tsv")
    meta_path = tsv_path.with_suffix(".meta.json")

    if not refresh and tsv_path.exists() and meta_path.exists():
        return tsv_path

    # Step 1: resolve disease term → EFO/MONDO ID
    search_data = _gql(requests, _SEARCH_QUERY, {"q": disease_term})
    hits = search_data.get("search", {}).get("hits", [])
    disease_hits = [h for h in hits if h.get("entity") == "disease"]
    if not disease_hits:
        die(
            f"No disease found in Open Targets for query: '{disease_term}'\n"
            f"  Try a more specific term, or check https://platform.opentargets.org/",
            fetcher=SOURCE_NAME,
        )
    best = disease_hits[0]
    disease_id = best["id"]
    disease_name = best["name"]
    print(f"[open_targets] resolved '{disease_term}' → {disease_id} ({disease_name})", file=sys.stderr)

    # Step 2: fetch associated targets
    assoc_raw = json.dumps({"query": _ASSOC_QUERY, "variables": {"diseaseId": disease_id, "size": max_genes}}).encode()
    source_sha = sha256_bytes(assoc_raw)  # hash the request payload as a source fingerprint

    assoc_data = _gql(requests, _ASSOC_QUERY, {"diseaseId": disease_id, "size": max_genes})
    disease_node = assoc_data.get("disease")
    if not disease_node:
        die(f"Open Targets returned no disease node for ID: {disease_id}", fetcher=SOURCE_NAME)

    rows_raw = disease_node["associatedTargets"]["rows"]
    total_count = disease_node["associatedTargets"]["count"]
    if total_count > max_genes:
        print(
            f"[open_targets] WARNING: disease has {total_count} associated targets; "
            f"fetched top {max_genes} by score. Use --max-genes to raise the limit.",
            file=sys.stderr,
        )

    if not rows_raw:
        die(
            f"Open Targets returned zero associated targets for {disease_id} ({disease_name}).\n"
            f"  This disease exists but has no scored associations — check the platform UI.",
            fetcher=SOURCE_NAME,
        )

    # Step 3: build DataFrame
    records = []
    for row in rows_raw:
        score = row["score"]
        if score < min_score:
            continue
        target = row["target"]
        ensembl_id = target["id"]          # already Ensembl gene ID (ENSG...)
        symbol = target.get("approvedSymbol", "")
        records.append({
            "ensembl_id": ensembl_id,
            "symbol": symbol,
            "entrez_id": "",   # Open Targets doesn't return Entrez; leave blank
            "species": species,
            "source": SOURCE_NAME,
            "disease_id": disease_id,
            "disease_name": disease_name,
            "association_score": round(score, 6),
        })

    if not records:
        die(
            f"No genes passed the min_score={min_score} filter for {disease_id}.\n"
            f"  Lower --min-score or omit it to return all associations.",
            fetcher=SOURCE_NAME,
        )

    df = pd.DataFrame(records).drop_duplicates(subset=["ensembl_id"]).reset_index(drop=True)

    upstream = _upstream_version(requests)
    ver_tag = upstream.get("ot_data_version", "unknown-version")

    source = SourceInfo(
        url=GRAPHQL_URL,
        version=f"Open Targets Platform data {ver_tag} (fetched live); disease={disease_id}",
        sha256=source_sha,
        durability="Open Targets Platform is institutionally hosted (Wellcome Sanger / EMBL-EBI / GSK / Biogen)",
        notes=f"disease_term='{disease_term}'; resolved_id={disease_id}; resolved_name='{disease_name}'; total_associations={total_count}; returned={len(df)}; min_score={min_score}",
    )

    # Ad-hoc query artifacts are NOT pinned to a user-chosen Ensembl release
    # (Open Targets returns Ensembl IDs from its own build), so we hand-roll
    # the meta with `query_type` instead of routing through write_artifact.
    # See REQUIRED_META_FIELDS_QUERY in tests/test_artifact_format.py.
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(tsv_path, sep="\t", index=False)
    output_sha = hashlib.sha256(tsv_path.read_bytes()).hexdigest()

    meta = {
        "set": cache_key,
        "query_type": "disease",
        "disease_term": disease_term,
        "disease_id": disease_id,
        "disease_name": disease_name,
        "min_score": min_score,
        "species": species,
        "n_genes": len(df),
        "total_associations_in_db": total_count,
        "fetched_at": iso_now(),
        "source": SOURCE_NAME,
        "source_url": GRAPHQL_URL,
        "source_version": source.version,
        "source_sha256": source_sha,
        "output_sha256": output_sha,
        "tool_version": "gene-set-fetch 0.1.0",
        # Upstream release backing the emitted ENSG IDs (best-effort capture).
        "ot_data_version": upstream.get("ot_data_version"),
        "ot_api_version": upstream.get("ot_api_version"),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    print(f"[open_targets] {len(df)} genes written to {tsv_path}", file=sys.stderr)
    return tsv_path
