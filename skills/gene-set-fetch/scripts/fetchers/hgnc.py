"""HGNC — HUGO Gene Nomenclature Committee complete gene set.

Source: hgnc_complete_set.txt, served from EBI's FTP mirror. This is the
canonical, versioned-by-date snapshot of HGNC's full gene set. Updated
weekly upstream; we record the fetch date as the version.

Why this file: it's the single official "everything HGNC knows" dump, with
`locus_type` available for filtering (e.g. "gene with protein product"),
plus cross-references to Ensembl and Entrez. The web UI's "Custom downloads"
builder is for ad-hoc queries; the complete-set TSV is the durable choice.
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
    iso_now,
    require_module,
    sha256_bytes,
    write_artifact,
)

FETCHER_NAME = "hgnc"
# HGNC's complete_set is canonically served from their Google Cloud Storage
# bucket. The historical EBI FTP mirror was retired; the GCS bucket is what
# the official genenames.org "Statistics & download files" page points at.
SOURCE_URL = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"

LOCUS_TYPE_MAP = {
    # registry args -> HGNC locus_type values
    "gene_with_protein_product": "gene with protein product",
}


def fetch(
    name: str,
    species: str,
    args: dict,
    ensembl_release: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    if species != "human":
        die(f"HGNC is human-only; got species={species}", fetcher=FETCHER_NAME)

    locus_arg = args.get("locus_type", "gene_with_protein_product")
    locus_value = LOCUS_TYPE_MAP.get(locus_arg, locus_arg)

    # Source version: HGNC updates the file in place, so the only honest
    # version handle is the fetch date. Cache key uses today's date.
    today = iso_now().split("T")[0]
    source_version_tag = f"hgnc-{today}-{locus_arg}"

    tsv_path, meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    if not refresh and is_fresh(tsv_path, meta_path):
        return tsv_path

    requests = require_module("requests", "pip install requests", FETCHER_NAME)

    try:
        resp = http_get(SOURCE_URL, requests, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"HGNC download failed: {SOURCE_URL}\n  {e}", fetcher=FETCHER_NAME)

    raw = resp.content
    source_sha = sha256_bytes(raw)

    df_raw = pd.read_csv(io.BytesIO(raw), sep="\t", dtype="string", low_memory=False)

    needed = {"symbol", "entrez_id", "ensembl_gene_id", "locus_type"}
    missing = needed - set(df_raw.columns)
    if missing:
        die(
            f"HGNC TSV is missing expected columns: {sorted(missing)}\n"
            f"  got: {list(df_raw.columns)[:20]}...",
            fetcher=FETCHER_NAME,
        )

    filtered = df_raw[df_raw["locus_type"] == locus_value].copy()
    if len(filtered) == 0:
        die(
            f"HGNC filter locus_type=={locus_value!r} matched zero rows.\n"
            f"  available locus_types: {df_raw['locus_type'].dropna().unique().tolist()[:20]}",
            fetcher=FETCHER_NAME,
        )

    # HGNC rows can have empty ensembl_gene_id; drop those — they can't
    # participate in set algebra on the ensembl_id key.
    pre_drop = len(filtered)
    filtered = filtered[filtered["ensembl_gene_id"].notna() & (filtered["ensembl_gene_id"] != "")]
    dropped = pre_drop - len(filtered)

    out_df = pd.DataFrame({
        "ensembl_id": filtered["ensembl_gene_id"].astype(str),
        "symbol": filtered["symbol"].astype("string"),
        "entrez_id": filtered["entrez_id"].astype("string"),
        "species": "human",
        "source": name,
        "hgnc_id": filtered.get("hgnc_id", pd.Series(dtype="string")).astype("string"),
        "locus_type": filtered["locus_type"].astype("string"),
    }).drop_duplicates(subset=["ensembl_id"]).reset_index(drop=True)

    source = SourceInfo(
        url=SOURCE_URL,
        version=f"HGNC complete_set as of {today} (UTC)",
        sha256=source_sha,
        durability="EBI-hosted; HGNC updates the file in place — version handle is fetch date",
        notes=f"locus_type filter={locus_value!r}; dropped {dropped} rows with empty ensembl_gene_id",
    )

    return write_artifact(
        df=out_df,
        name=name,
        species="human",
        ensembl_release=ensembl_release,
        source=source,
        cache_dir=cache_dir,
        out=out,
        source_version_tag=source_version_tag,
        extra_meta={
            "filters_applied": [f"locus_type == {locus_value!r}", "ensembl_gene_id non-empty"],
            "rows_dropped_missing_ensembl_id": dropped,
        },
    )
