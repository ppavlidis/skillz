"""JASPAR CORE — genes that have a sequence-specific DNA-binding motif.

Source: the JASPAR REST API (https://jaspar.elixir.no/api/v1/). JASPAR is the
open, curated, non-redundant database of TF binding profiles (position
frequency matrices). This fetcher produces the set of *genes* that have at
least one JASPAR CORE profile for a given taxon — i.e. "transcription factors
with a known motif".

Why this is its own set (and not a filter): JASPAR is a distinct authority on
what counts as a motif-backed TF, complementary to Lambert 2018 and AnimalTFDB.
Per the skill's multi-authority contract, it ships as a first-class named set
(`tfs_{species}_jaspar`), and "TFs which have a JASPAR motif" is then just the
*intersection* of a curated TF set with this one — handled by compose.py, no
special-case code.

How the gene list is built:
  1. Page the `matrix/` endpoint with collection=CORE, version=latest, and the
     taxon's tax_id. Each record carries a `name` (the TF gene symbol; hetero-
     dimers use the `A::B` convention).
  2. Split dimer names on `::` into their component genes. (We do NOT split on
     `-`: real gene symbols contain hyphens, e.g. NKX2-5, NKX3-1. Fusion names
     like `EWSR1-FLI1` are left whole and simply won't map — recorded below.)
  3. Map the resulting symbols to Ensembl gene IDs via the Ensembl REST batch
     `lookup/symbol` endpoint (case-insensitive; the canonical join key for
     this skill is `ensembl_id`). Symbols that don't resolve are recorded in
     the meta under `unmapped_jaspar_names`, never silently dropped.

Motif coverage note: JASPAR CORE is taxon-tagged. Human (tax 9606) is well
covered; the mouse (10090) and rat (10116) CORE collections are much smaller,
because most vertebrate profiles are annotated to the species they were
experimentally derived in. A mouse TF whose human ortholog has a motif will
NOT appear in `tfs_mouse_jaspar` unless a mouse-tagged profile exists. For
cross-species "has a motif" analyses you almost certainly want the human
JASPAR set mapped through orthology, not the sparse rodent CORE sets. This is
called out in SKILL.md.

Durability: JASPAR is an ELIXIR-hosted, versioned, widely-cited community
resource with a stable REST API. The cache key encodes the detected active
release (year + number), so a JASPAR release bump produces a new artifact
alongside the old.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from ._common import (
    SourceInfo,
    cache_paths,
    die,
    http_get,
    http_post,
    is_fresh,
    require_module,
    sha256_bytes,
    write_artifact,
)

FETCHER_NAME = "jaspar"

JASPAR_API = "https://jaspar.elixir.no/api/v1"
ENSEMBL_REST = "https://rest.ensembl.org"

# JASPAR / Ensembl taxon identifiers, keyed by the skill's species labels.
SPECIES_TAXID = {"human": 9606, "mouse": 10090, "rat": 10116}
SPECIES_REST_NAME = {
    "human": "homo_sapiens",
    "mouse": "mus_musculus",
    "rat": "rattus_norvegicus",
}

# Be nice to the APIs. JASPAR and Ensembl REST are free community services.
RATE_LIMIT_SLEEP = 0.1          # between paged JASPAR / Ensembl calls
LOOKUP_CHUNK = 900             # Ensembl lookup/symbol POST cap is 1000 symbols
MATRIX_PAGE_SIZE = 1000


def _latest_active_release(requests) -> tuple[str, int]:
    """Return (year, release_number) of the newest active JASPAR release.

    Used only to tag the cache key so a JASPAR release bump lands in a new
    file. Fails loud if the endpoint can't be read — we refuse to emit an
    artifact we can't version.
    """
    url = f"{JASPAR_API}/releases/"
    try:
        resp = http_get(url, requests, params={"page_size": 100, "format": "json"}, timeout=60)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except (requests.RequestException, ValueError) as e:
        die(
            f"could not read JASPAR releases from {url} to pin the cache key\n  {e}",
            fetcher=FETCHER_NAME,
        )
    active = [r for r in results if str(r.get("active", "")).lower() == "yes"]
    if not active:
        die(f"JASPAR releases endpoint returned no active release: {url}", fetcher=FETCHER_NAME)
    newest = max(active, key=lambda r: int(r["release_number"]))
    return str(newest.get("year", "unknown")), int(newest["release_number"])


def _fetch_core_matrices(requests, tax_id: int) -> list[dict]:
    """Page the JASPAR CORE matrix list for a taxon; return [{matrix_id, name}]."""
    records: list[dict] = []
    url: str | None = f"{JASPAR_API}/matrix/"
    params: dict | None = {
        "collection": "CORE",
        "tax_id": tax_id,
        "version": "latest",   # one row per base matrix (its current version)
        "page_size": MATRIX_PAGE_SIZE,
        "format": "json",
    }
    while url:
        try:
            resp = http_get(url, requests, params=params, timeout=90)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as e:
            die(
                f"JASPAR matrix listing failed for tax_id={tax_id}\n  url: {url}\n  {e}",
                fetcher=FETCHER_NAME,
            )
        for r in payload.get("results", []):
            mid, nm = r.get("matrix_id"), r.get("name")
            if mid and nm:
                records.append({"matrix_id": mid, "name": nm})
        url = payload.get("next")   # absolute URL; params already baked in
        params = None
        if url:
            time.sleep(RATE_LIMIT_SLEEP)
    if not records:
        die(
            f"JASPAR returned zero CORE matrices for tax_id={tax_id}. "
            f"Upstream schema or taxon coverage may have changed.",
            fetcher=FETCHER_NAME,
        )
    return records


def _lookup_symbols(requests, rest_species: str, symbols: list[str]) -> dict[str, dict]:
    """Batch-map gene symbols to Ensembl gene records via lookup/symbol POST.

    Returns {input_symbol: gene_object} for symbols Ensembl resolved to a gene.
    Case-insensitive server-side, so JASPAR's uppercase names resolve against
    mouse/rat Title-case symbols too.
    """
    url = f"{ENSEMBL_REST}/lookup/symbol/{rest_species}"
    resolved: dict[str, dict] = {}
    for i in range(0, len(symbols), LOOKUP_CHUNK):
        chunk = symbols[i : i + LOOKUP_CHUNK]
        body = json.dumps({"symbols": chunk})
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            resp = http_post(url, requests, data=body, headers=headers, timeout=90)
        except requests.RequestException as e:
            die(f"Ensembl lookup/symbol POST failed: {url}\n  {e}", fetcher=FETCHER_NAME)
        if resp.status_code == 429:
            try:
                wait = float(resp.headers.get("Retry-After", "2"))
            except ValueError:
                wait = 2.0
            time.sleep(max(wait, 2.0))
            resp = http_post(url, requests, data=body, headers=headers, timeout=90)
        if not resp.ok:
            die(
                f"Ensembl lookup/symbol returned HTTP {resp.status_code}\n  body: {resp.text[:300]}",
                fetcher=FETCHER_NAME,
            )
        for sym, obj in resp.json().items():
            if isinstance(obj, dict) and obj.get("object_type") == "Gene":
                gid = str(obj.get("id", ""))
                if gid.startswith("ENS"):
                    resolved[sym] = obj
        time.sleep(RATE_LIMIT_SLEEP)
    return resolved


def fetch(
    name: str,
    species: str,
    args: dict,
    ensembl_release: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    if species not in SPECIES_TAXID:
        die(f"unsupported species: {species} (expected human/mouse/rat)", fetcher=FETCHER_NAME)
    tax_id = int(args.get("tax_id", SPECIES_TAXID[species]))
    rest_species = SPECIES_REST_NAME[species]

    requests = require_module("requests", "pip install requests", FETCHER_NAME)

    year, release_number = _latest_active_release(requests)
    source_version_tag = f"jaspar{year}r{release_number}"

    tsv_path, meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    if not refresh and is_fresh(tsv_path, meta_path):
        return tsv_path

    matrices = _fetch_core_matrices(requests, tax_id)

    # Deterministic hash of the raw upstream content — detects silent drift
    # even when the release tag hasn't moved.
    canon = "\n".join(sorted(f"{m['matrix_id']}\t{m['name']}" for m in matrices)).encode()
    source_sha = sha256_bytes(canon)

    # Split heterodimer names (A::B) into component genes; keep every matrix a
    # component participates in.
    name_to_matrices: dict[str, set[str]] = {}
    for m in matrices:
        for comp in str(m["name"]).split("::"):
            comp = comp.strip()
            if comp:
                name_to_matrices.setdefault(comp, set()).add(m["matrix_id"])

    jaspar_names = sorted(name_to_matrices)
    resolved = _lookup_symbols(requests, rest_species, jaspar_names)
    unmapped = sorted(n for n in jaspar_names if n not in resolved)

    # Group by Ensembl gene: one output row per gene, unioning the JASPAR
    # names and matrix IDs that landed on it.
    by_gene: dict[str, dict] = {}
    for jn in jaspar_names:
        obj = resolved.get(jn)
        if obj is None:
            continue
        gid = str(obj["id"])
        rec = by_gene.setdefault(
            gid,
            {"symbol": obj.get("display_name") or jn, "names": set(), "matrix_ids": set()},
        )
        rec["names"].add(jn)
        rec["matrix_ids"].update(name_to_matrices[jn])

    if not by_gene:
        die(
            f"JASPAR CORE for tax_id={tax_id} produced {len(matrices)} matrices but none "
            f"mapped to an Ensembl gene. Ensembl lookup or JASPAR naming may have changed.",
            fetcher=FETCHER_NAME,
        )

    rows = []
    for gid, rec in by_gene.items():
        rows.append({
            "ensembl_id": gid,
            "symbol": rec["symbol"],
            "entrez_id": pd.NA,
            "species": species,
            "source": name,
            "jaspar_names": ";".join(sorted(rec["names"])),
            "jaspar_matrix_ids": ";".join(sorted(rec["matrix_ids"])),
            "n_jaspar_motifs": len(rec["matrix_ids"]),
        })
    out_df = (
        pd.DataFrame(rows)
        .astype({"entrez_id": "string"})
        .sort_values("ensembl_id")
        .drop_duplicates(subset=["ensembl_id"])
        .reset_index(drop=True)
    )

    source = SourceInfo(
        url=f"{JASPAR_API}/matrix/?collection=CORE&tax_id={tax_id}&version=latest",
        version=f"JASPAR {year} (release {release_number}), CORE collection, latest matrix versions",
        sha256=source_sha,
        durability="ELIXIR-hosted, versioned, widely-cited; stable REST API",
        notes=(
            f"tax_id={tax_id}; {len(matrices)} CORE matrices → {len(jaspar_names)} unique "
            f"gene names → {len(out_df)} Ensembl genes; {len(unmapped)} names unmapped"
        ),
    )

    return write_artifact(
        df=out_df,
        name=name,
        species=species,
        ensembl_release=ensembl_release,
        source=source,
        cache_dir=cache_dir,
        out=out,
        source_version_tag=source_version_tag,
        extra_meta={
            "jaspar_release_year": year,
            "jaspar_release_number": release_number,
            "tax_id": tax_id,
            "n_core_matrices": len(matrices),
            "n_unique_jaspar_names": len(jaspar_names),
            "n_symbols_mapped": len(resolved),
            "n_symbols_unmapped": len(unmapped),
            "unmapped_jaspar_names": unmapped,
            "symbol_mapping": (
                "JASPAR names split on '::' then resolved to Ensembl gene IDs via "
                "rest.ensembl.org lookup/symbol (current release, case-insensitive)"
            ),
        },
    )
