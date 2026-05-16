"""MGI — Mouse Genome Informatics gene catalog.

To call something "a protein-coding gene per MGI" we need MGI's `Feature Type`
attribute. That field lives in **MRK_List2.rpt** (the full marker list), not
in MGI_Gene_Model_Coord.rpt. MGI_Gene_Model_Coord is the file that maps MGI
IDs to Ensembl gene IDs, but it only has `Marker Type` (broader: "Gene",
"Pseudogene", "QTL", etc.) and not `Feature Type` ("protein coding gene",
"lncRNA gene", "miRNA gene", etc.).

So this fetcher does a two-file join:

1. Download MRK_List2.rpt — get `MGI Accession ID` + `Feature Type`
2. Download MGI_Gene_Model_Coord.rpt — get `MGI accession id` + `Ensembl Gene ID`
3. Inner-join on MGI ID, keep rows where Feature Type matches the request.

The MGI files use a quirky header format where column names are prefixed with
their column number (e.g. "1. MGI Accession ID"). We strip the "N. " prefix
before matching.

Canonicality: MGI is the canonical authority for mouse gene nomenclature
and is hosted by The Jackson Laboratory (informatics.jax.org).
"""

from __future__ import annotations

import io
import re
import time
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

FETCHER_NAME = "mgi"

MRK_LIST_URL = "https://www.informatics.jax.org/downloads/reports/MRK_List2.rpt"
GENE_MODEL_COORD_URL = "https://www.informatics.jax.org/downloads/reports/MGI_Gene_Model_Coord.rpt"

FEATURE_TYPE_MAP = {
    "protein_coding_gene": "protein coding gene",
}

_COL_NUM_PREFIX_RE = re.compile(r"^\s*\d+\s*\.\s*")


def _normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Strip "N. " column-number prefix and lowercase/underscore the rest."""
    cleaned = []
    for c in df.columns:
        c = _COL_NUM_PREFIX_RE.sub("", c).strip()
        cleaned.append(c.lower().replace(" ", "_"))
    df = df.copy()
    df.columns = cleaned
    return df


def _fetch_rpt(url: str, requests, timeout: int = 120) -> bytes:
    try:
        resp = http_get(url, requests, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"MGI download failed: {url}\n  {e}", fetcher=FETCHER_NAME)
    return resp.content


def fetch(
    name: str,
    species: str,
    args: dict,
    ensembl_release: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    if species != "mouse":
        die(f"MGI is mouse-only; got species={species}", fetcher=FETCHER_NAME)

    feature_arg = args.get("feature_type", "protein_coding_gene")
    feature_value = FEATURE_TYPE_MAP.get(feature_arg, feature_arg)

    today = iso_now().split("T")[0]
    source_version_tag = f"mgi-{today}-{feature_arg}"

    tsv_path, meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    if not refresh and is_fresh(tsv_path, meta_path):
        return tsv_path

    requests = require_module("requests", "pip install requests", FETCHER_NAME)

    # MRK_List2: MGI ID + Feature Type (and many other cols we don't use)
    raw_mrk = _fetch_rpt(MRK_LIST_URL, requests, timeout=120)
    # Sleep between calls — same host, no need to burst.
    time.sleep(0.5)
    raw_coord = _fetch_rpt(GENE_MODEL_COORD_URL, requests, timeout=120)

    # MGI .rpt files have a trailing tab on each data row, making data rows
    # one field wider than the header. Without index_col=False pandas auto-
    # promotes the first data field to a row index, silently shifting every
    # column left by one — a horrible silent-misalignment bug. Lock it down.
    try:
        mrk = pd.read_csv(io.BytesIO(raw_mrk), sep="\t", dtype="string", low_memory=False, index_col=False)
        coord = pd.read_csv(io.BytesIO(raw_coord), sep="\t", dtype="string", low_memory=False, index_col=False)
    except Exception as e:
        die(f"MGI parse failed: {e}", fetcher=FETCHER_NAME)

    mrk = _normalize_cols(mrk)
    coord = _normalize_cols(coord)

    # Required columns after normalization.
    if "mgi_accession_id" not in mrk.columns or "feature_type" not in mrk.columns:
        die(
            f"MRK_List2 missing expected columns after remap.\n"
            f"  got: {list(mrk.columns)}",
            fetcher=FETCHER_NAME,
        )
    if "mgi_accession_id" not in coord.columns or "ensembl_gene_id" not in coord.columns:
        die(
            f"MGI_Gene_Model_Coord missing expected columns after remap.\n"
            f"  got: {list(coord.columns)}",
            fetcher=FETCHER_NAME,
        )

    # Filter MRK to the requested feature_type before joining.
    mrk_f = mrk[mrk["feature_type"] == feature_value][["mgi_accession_id", "marker_symbol", "feature_type"]].copy()
    if len(mrk_f) == 0:
        die(
            f"MRK_List2 filter feature_type=={feature_value!r} matched zero rows.\n"
            f"  available feature_types: {mrk['feature_type'].dropna().unique().tolist()[:20]}",
            fetcher=FETCHER_NAME,
        )

    # Keep only the columns we need from coord to avoid noise.
    entrez_col = "entrez_gene_id" if "entrez_gene_id" in coord.columns else None
    coord_cols = ["mgi_accession_id", "ensembl_gene_id"] + ([entrez_col] if entrez_col else [])
    coord_f = coord[coord_cols].copy()

    merged = mrk_f.merge(coord_f, on="mgi_accession_id", how="inner")
    if len(merged) == 0:
        die(
            "MGI two-file join produced zero rows. Likely a column-shift bug "
            "or upstream schema change. Re-read the file structure and rerun.",
            fetcher=FETCHER_NAME,
        )
    pre = len(merged)
    merged = merged[merged["ensembl_gene_id"].notna() & (merged["ensembl_gene_id"] != "")]
    dropped = pre - len(merged)
    if len(merged) == 0:
        die(
            f"MGI: all {pre} merged rows had empty ensembl_gene_id; nothing left "
            "to emit. Inspect MGI_Gene_Model_Coord upstream — ensembl_gene_id "
            "column may have shifted.",
            fetcher=FETCHER_NAME,
        )

    entrez_series = (
        merged[entrez_col].astype("string")
        if entrez_col
        else pd.Series([pd.NA] * len(merged), dtype="string")
    )

    out_df = pd.DataFrame({
        "ensembl_id": merged["ensembl_gene_id"].astype(str),
        "symbol": merged["marker_symbol"].astype("string"),
        "entrez_id": entrez_series,
        "species": "mouse",
        "source": name,
        "mgi_id": merged["mgi_accession_id"].astype("string"),
        "feature_type": merged["feature_type"].astype("string"),
    }).drop_duplicates(subset=["ensembl_id"]).reset_index(drop=True)

    source = SourceInfo(
        url=f"{MRK_LIST_URL} + {GENE_MODEL_COORD_URL} (joined on MGI ID)",
        version=f"MGI MRK_List2 + Gene_Model_Coord as of {today} (UTC)",
        sha256=sha256_bytes(raw_mrk + b"\n--JOIN--\n" + raw_coord),
        durability="JAX-hosted; MGI updates these files in place — version handle is fetch date",
        notes=(
            f"feature_type filter={feature_value!r} on MRK_List2; "
            f"inner-joined to MGI_Gene_Model_Coord on mgi_accession_id; "
            f"dropped {dropped} rows missing ensembl_gene_id after join"
        ),
    )

    return write_artifact(
        df=out_df,
        name=name,
        species="mouse",
        ensembl_release=ensembl_release,
        source=source,
        cache_dir=cache_dir,
        out=out,
        source_version_tag=source_version_tag,
        extra_meta={
            "filters_applied": [
                f"MRK_List2.feature_type == {feature_value!r}",
                "inner join with MGI_Gene_Model_Coord on mgi_accession_id",
                "ensembl_gene_id non-empty",
            ],
            "rows_dropped_missing_ensembl_id": dropped,
            "mrk_list_url": MRK_LIST_URL,
            "gene_model_coord_url": GENE_MODEL_COORD_URL,
        },
    )
