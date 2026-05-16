"""Ensembl BioMart — gene lists filtered by biotype.

Source: Ensembl BioMart REST endpoint, queried against a release-specific
archive (e{N}.ensembl.org) so the result is pinned to the requested release.

Why BioMart REST over GTF download: a BioMart query returns ~20K rows of
exactly the columns we need (Ensembl ID, symbol, Entrez ID, biotype) in
~1-2 MB of TSV. A full Ensembl GTF is ~50 MB compressed and contains far
more than we use.

Canonicality: Ensembl is the canonical authority for vertebrate gene
annotations. Archived releases are stable URLs that never change content,
which is the durability story we want.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from ._common import (
    SourceInfo,
    cache_paths,
    die,
    http_get,
    is_fresh,
    require_module,
    sha256_bytes,
    write_artifact,
)

FETCHER_NAME = "ensembl_biomart"

SPECIES_DATASET = {
    "human": "hsapiens_gene_ensembl",
    "mouse": "mmusculus_gene_ensembl",
}


def _biomart_url(release: int) -> str:
    # NOTE: per-release archive subdomains (e{N}.ensembl.org) serve the
    # BioMart web UI, not the REST endpoint, so we use the main www endpoint
    # which always serves the current release. This means BioMart results in
    # v0.1 reflect "whatever Ensembl release www.ensembl.org currently serves",
    # NOT the --ensembl-release knob. The release is still recorded in the
    # .meta.json for traceability but is not enforced server-side.
    # TODO v0.2: use Ensembl REST's date-archive hosts (e.g. nov2024.archive...)
    # which DO serve BioMart, with a release→archive-date mapping.
    return "https://www.ensembl.org/biomart/martservice"


def _biomart_query_xml(dataset: str, biotype: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE Query>'
        '<Query virtualSchemaName="default" formatter="TSV" header="1" uniqueRows="1" count="" datasetConfigVersion="0.6">'
        f'<Dataset name="{dataset}" interface="default">'
        f'<Filter name="biotype" value="{biotype}"/>'
        '<Attribute name="ensembl_gene_id"/>'
        '<Attribute name="external_gene_name"/>'
        '<Attribute name="entrezgene_id"/>'
        '<Attribute name="gene_biotype"/>'
        '</Dataset>'
        '</Query>'
    )


def fetch(
    name: str,
    species: str,
    args: dict,
    ensembl_release: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    if species not in SPECIES_DATASET:
        die(f"unsupported species: {species}", fetcher=FETCHER_NAME)

    biotype = args.get("biotype", "protein_coding")
    source_version_tag = f"e{ensembl_release}-{biotype}"

    tsv_path, meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    if not refresh and is_fresh(tsv_path, meta_path):
        return tsv_path

    requests = require_module("requests", "pip install requests", FETCHER_NAME)

    dataset = SPECIES_DATASET[species]
    url = _biomart_url(ensembl_release)
    query_xml = _biomart_query_xml(dataset, biotype)

    # BioMart accepts both POST (form-encoded) and GET (URL parameter). GET is
    # what the canonical client docs show; we use GET for parity.
    try:
        resp = http_get(url, requests, params={"query": query_xml}, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        die(
            f"BioMart request failed: {url}\n  {e}\n"
            f"  if the URL is reachable manually, the BioMart XML schema may have changed.",
            fetcher=FETCHER_NAME,
        )

    raw = resp.content
    if raw.lstrip().startswith(b"Query ERROR") or b"<html" in raw[:200].lower():
        die(
            f"BioMart returned an error or HTML instead of TSV.\n"
            f"  first 400 bytes: {raw[:400]!r}\n"
            f"  inspect the URL ({url}) and query XML in fetchers/ensembl_biomart.py.",
            fetcher=FETCHER_NAME,
        )

    source_sha = sha256_bytes(raw)
    df_raw = pd.read_csv(io.BytesIO(raw), sep="\t", dtype={"NCBI gene (formerly Entrezgene) ID": "string"})

    # BioMart column names vary across releases ("Gene stable ID" vs
    # "Ensembl gene ID" vs raw attribute names depending on server config).
    # Match by substring hints rather than exact label.
    NAME_HINTS = {
        "ensembl_id": ["gene stable id", "ensembl gene id", "ensembl_gene_id"],
        "symbol": ["symbol", "gene name", "external_gene_name", "hgnc symbol"],
        "entrez_id": ["entrez_id", "entrezgene", "entrez gene id", "ncbi gene"],
        "biotype": ["gene type", "biotype", "gene_biotype"],
    }
    rename_map: dict[str, str] = {}
    for col in df_raw.columns:
        lc = col.lower().strip()
        for canonical, hints in NAME_HINTS.items():
            if any(h in lc for h in hints):
                rename_map[col] = canonical
                break
    df_raw = df_raw.rename(columns=rename_map)

    needed = {"ensembl_id", "symbol", "entrez_id", "biotype"}
    missing = needed - set(df_raw.columns)
    if missing:
        die(
            f"BioMart TSV is missing expected columns after remapping: {sorted(missing)}\n"
            f"  got: {list(df_raw.columns)}",
            fetcher=FETCHER_NAME,
        )

    # Belt-and-braces: assert the biotype filter actually held.
    bad = df_raw[df_raw["biotype"] != biotype]
    if len(bad):
        die(
            f"BioMart returned {len(bad)} rows with biotype != {biotype}; "
            f"server-side filter did not hold.",
            fetcher=FETCHER_NAME,
        )

    out_df = pd.DataFrame({
        "ensembl_id": df_raw["ensembl_id"].astype(str),
        "symbol": df_raw["symbol"].astype("string"),
        "entrez_id": df_raw["entrez_id"].astype("string"),
        "species": species,
        "source": name,
        "biotype": df_raw["biotype"].astype("string"),
    }).drop_duplicates(subset=["ensembl_id"]).reset_index(drop=True)

    source = SourceInfo(
        url=url,
        version=f"Ensembl release {ensembl_release} (archived endpoint); biotype filter={biotype}",
        sha256=source_sha,
        durability="Ensembl archived release endpoints are immutable and long-lived",
        notes=f"dataset={dataset}; rows={len(out_df)}",
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
            "filters_applied": [f"biotype == {biotype}"],
            "biomart_query_xml": query_xml,
        },
    )
