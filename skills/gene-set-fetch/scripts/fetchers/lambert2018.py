"""Lambert 2018 human transcription factors.

Source: the Hughes lab's actively-maintained "Human Transcription Factors"
database at humantfs.ccbr.utoronto.ca, currently v_1.01. This is the
authoritative, post-publication-curated version of the list from:

    Lambert, S.A., Jolma, A., Campitelli, L.F., Das, P.K., Yin, Y., Albu, M.,
    Chen, X., Taipale, J., Hughes, T.R., Weirauch, M.T.
    "The Human Transcription Factors." Cell 172, 650-665 (2018).
    DOI: 10.1016/j.cell.2018.01.029

Why this source (over the Cell supplementary file): the humantfs database is
maintained by the original authors, incorporates erratum corrections, and is
explicitly versioned (v_1.01). The Cell supplementary table is the
publication-of-record but is frozen at first submission. For reproducibility
we prefer the maintained, versioned authority; for citation, callers should
still cite the Cell paper plus the database version (both are recorded in
the .meta.json).

Durability: hosted on a university lab page, which has middling durability.
If this URL ever goes dark, alternates include the Cell mmc supp and the
authors' Hughes lab GitHub. Update both the URL constant and the
.meta.json `source_durability` note if you switch.
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

SOURCE_VERSION = "v_1.01"
SOURCE_URL = f"http://humantfs.ccbr.utoronto.ca/download/{SOURCE_VERSION}/DatabaseExtract_{SOURCE_VERSION}.csv"
SOURCE_CITATION = (
    f"Lambert et al. 2018 (Cell, DOI: 10.1016/j.cell.2018.01.029); "
    f"humantfs database {SOURCE_VERSION}"
)
SOURCE_DURABILITY = "university-hosted lab website (humantfs.ccbr.utoronto.ca); medium durability"

FETCHER_NAME = "lambert2018"


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
        die(f"Lambert 2018 is human-only; got species={species}", fetcher=FETCHER_NAME)

    tsv_path, meta_path = cache_paths(name, ensembl_release, SOURCE_VERSION, cache_dir, out)
    if not refresh and is_fresh(tsv_path, meta_path):
        return tsv_path

    requests = require_module("requests", "pip install requests", FETCHER_NAME)

    try:
        resp = http_get(SOURCE_URL, requests, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        die(
            f"failed to download Lambert TFs from {SOURCE_URL}\n"
            f"  {e}\n"
            f"  if humantfs.ccbr.utoronto.ca is reachable manually, the URL or version "
            f"may have changed — inspect scripts/fetchers/lambert2018.py to update.",
            fetcher=FETCHER_NAME,
        )

    raw = resp.content
    source_sha = sha256_bytes(raw)

    try:
        df_raw = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        die(
            f"could not parse Lambert CSV; upstream format may have changed.\n"
            f"  first 200 bytes: {raw[:200]!r}\n"
            f"  parse error: {e}",
            fetcher=FETCHER_NAME,
        )

    # Required columns in the humantfs CSV. If these names change upstream,
    # fail loud rather than silently misinterpret the file.
    needed_cols = {"Ensembl ID", "HGNC symbol", "Is TF?", "DBD"}
    missing = needed_cols - set(df_raw.columns)
    if missing:
        die(
            f"Lambert CSV is missing expected columns: {sorted(missing)}\n"
            f"  got columns: {list(df_raw.columns)}\n"
            f"  the humantfs schema may have changed.",
            fetcher=FETCHER_NAME,
        )

    # The humantfs CSV lists both confirmed TFs ("Yes") and considered-but-
    # rejected candidates ("No"). We want only the curated TFs.
    tfs = df_raw[df_raw["Is TF?"].str.strip().str.lower() == "yes"].copy()
    if len(tfs) == 0:
        die(
            f"Lambert CSV parsed but yielded zero TFs after filtering Is TF? == 'Yes'.\n"
            f"  unique Is TF? values: {df_raw['Is TF?'].unique().tolist()}",
            fetcher=FETCHER_NAME,
        )

    out_df = pd.DataFrame({
        "ensembl_id": tfs["Ensembl ID"].astype(str).str.strip(),
        "symbol": tfs["HGNC symbol"].astype(str).str.strip(),
        "entrez_id": pd.Series([pd.NA] * len(tfs), dtype="string"),
        "species": "human",
        "source": name,
        "dbd_family": tfs["DBD"].astype(str).str.strip(),
    })

    # Drop rows with no Ensembl ID — they can't participate in set algebra.
    pre_drop = len(out_df)
    out_df = out_df[out_df["ensembl_id"].str.startswith("ENSG", na=False)].reset_index(drop=True)
    dropped = pre_drop - len(out_df)
    notes = ""
    if dropped:
        notes = f"dropped {dropped} rows with non-ENSG ensembl_id values"

    source = SourceInfo(
        url=SOURCE_URL,
        version=SOURCE_CITATION,
        sha256=source_sha,
        durability=SOURCE_DURABILITY,
        notes=notes,
    )

    extra_meta = {
        "filters_applied": ["Is TF? == Yes", "ensembl_id startswith ENSG"],
        "source_columns_used": ["Ensembl ID", "HGNC symbol", "Is TF?", "DBD"],
        "notes": (
            "entrez_id is left NA in v0.1; downstream normalization to a "
            "specific Ensembl release (via gget.info) is a planned step."
        ),
    }

    return write_artifact(
        df=out_df,
        name=name,
        species="human",
        ensembl_release=ensembl_release,
        source=source,
        cache_dir=cache_dir,
        out=out,
        source_version_tag=SOURCE_VERSION,
        extra_meta=extra_meta,
    )
