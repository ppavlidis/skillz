"""GENCODE — annotation-based gene biotype source.

Source: GENCODE annotation GTF (basic subset). For each release GENCODE
publishes a stable annotation file at a versioned URL on EBI's FTP. We
download it, stream-parse the gene-level records, and emit the rows
matching the requested `gene_type` (default: protein_coding).

Why this matters: Ensembl/HGNC/MGI and GENCODE all call slightly different
sets "protein-coding". A `protein_coding_*_strict` set is the intersection
of all three, which is the most defensible call when the choice of
authority would otherwise be arbitrary.

GENCODE release ↔ Ensembl release mapping (human): GENCODE vN tracks Ensembl
release N+11 (vague historical alignment); we let the caller specify the
GENCODE release explicitly via args.release if they need precision, else
pick a recent stable release per species.
"""

from __future__ import annotations

import gzip
import re
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

FETCHER_NAME = "gencode"

# Defaults chosen for v0.1. Bump these as GENCODE releases.
DEFAULT_RELEASE = {
    "human": "45",
    "mouse": "M34",
}


def _gencode_url(species: str, release: str) -> str:
    if species == "human":
        return (
            f"https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/"
            f"release_{release}/gencode.v{release}.basic.annotation.gtf.gz"
        )
    if species == "mouse":
        return (
            f"https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_mouse/"
            f"release_{release}/gencode.v{release}.basic.annotation.gtf.gz"
        )
    die(f"unsupported species: {species}", fetcher=FETCHER_NAME)


_GENE_ID_RE = re.compile(r'gene_id\s+"([^"]+)"')
_GENE_TYPE_RE = re.compile(r'gene_type\s+"([^"]+)"')
_GENE_NAME_RE = re.compile(r'gene_name\s+"([^"]+)"')


def _parse_gtf_gz(raw: bytes, want_gene_type: str) -> pd.DataFrame:
    """Stream-parse GENCODE GTF for gene-level records of the wanted gene_type."""
    rows = []
    with gzip.GzipFile(fileobj=__import__("io").BytesIO(raw)) as gz:
        for line_bytes in gz:
            if line_bytes.startswith(b"#"):
                continue
            line = line_bytes.decode("utf-8", errors="replace")
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 9 or parts[2] != "gene":
                continue
            attrs = parts[8]
            gt_m = _GENE_TYPE_RE.search(attrs)
            if gt_m is None or gt_m.group(1) != want_gene_type:
                continue
            id_m = _GENE_ID_RE.search(attrs)
            name_m = _GENE_NAME_RE.search(attrs)
            if id_m is None:
                continue
            ensembl_id_with_version = id_m.group(1)
            # Strip version suffix: ENSG00000123456.7 -> ENSG00000123456
            ensembl_id = ensembl_id_with_version.split(".")[0]
            rows.append({
                "ensembl_id": ensembl_id,
                "symbol": name_m.group(1) if name_m else None,
                "gene_type": gt_m.group(1),
            })
    return pd.DataFrame(rows)


def fetch(
    name: str,
    species: str,
    args: dict,
    ensembl_release: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    if species not in DEFAULT_RELEASE:
        die(f"unsupported species: {species}", fetcher=FETCHER_NAME)

    gene_type = args.get("gene_type", "protein_coding")
    release = args.get("release", DEFAULT_RELEASE[species])
    source_version_tag = f"gencode-{release}-{gene_type}"

    tsv_path, meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    if not refresh and is_fresh(tsv_path, meta_path):
        return tsv_path

    requests = require_module("requests", "pip install requests", FETCHER_NAME)

    url = _gencode_url(species, release)
    try:
        resp = http_get(url, requests, timeout=600)  # generous: the GTF is large
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"GENCODE download failed: {url}\n  {e}", fetcher=FETCHER_NAME)

    raw = resp.content
    source_sha = sha256_bytes(raw)

    parsed = _parse_gtf_gz(raw, want_gene_type=gene_type)
    if len(parsed) == 0:
        die(
            f"GENCODE GTF parsed but yielded zero gene records with gene_type={gene_type!r}\n"
            f"  upstream format may have changed; inspect first lines of the GTF.",
            fetcher=FETCHER_NAME,
        )

    out_df = pd.DataFrame({
        "ensembl_id": parsed["ensembl_id"].astype(str),
        "symbol": parsed["symbol"].astype("string"),
        "entrez_id": pd.Series([pd.NA] * len(parsed), dtype="string"),
        "species": species,
        "source": name,
        "gene_type": parsed["gene_type"].astype("string"),
    }).drop_duplicates(subset=["ensembl_id"]).reset_index(drop=True)

    source = SourceInfo(
        url=url,
        version=f"GENCODE release {release} ({species}), gene_type filter={gene_type}",
        sha256=source_sha,
        durability="EBI-hosted; GENCODE release URLs are immutable per release",
        notes=f"parsed {len(parsed)} gene records of type {gene_type}",
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
            "gencode_release": release,
            "filters_applied": [f"feature == gene", f"gene_type == {gene_type!r}"],
        },
    )
