"""Ensembl BioMart — genomic structural feature queries.

Source: Ensembl BioMart REST endpoint.
  https://www.ensembl.org/biomart/

Supported features:

  head_to_head (bidirectionally-transcribed gene pairs):
    Two protein-coding genes on opposite strands whose transcription start
    sites (TSSs) are within --max-distance bp of each other. These are also
    called "divergently transcribed gene pairs" or "bidirectional promoter
    pairs". They often share regulatory elements.

    Reference: Trinklein et al. (2004) Genome Res 14(1):62-66.
      "An abundance of bidirectional promoters in the human genome."
    Definition of TSS used here: for + strand, TSS = start of gene locus;
    for - strand, TSS = end of gene locus. Standard Ensembl convention.

    Output schema adds:
      chromosome, strand, tss, partner_ensembl_id, partner_symbol, tss_distance
    Each gene in a head-to-head pair gets one row per partner (pairs are
    listed twice: once for each member, so downstream tools can filter to
    a gene of interest).
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetchers._common import USER_AGENT, die, iso_now, require_module, sha256_bytes

SOURCE_NAME = "ensembl_genomic"
BIOMART_URL = "https://www.ensembl.org/biomart/martservice"

SPECIES_DATASET = {
    "human": "hsapiens_gene_ensembl",
    "mouse": "mmusculus_gene_ensembl",
}


def _biomart_query_xml(dataset: str, chromosome: str | None) -> str:
    chr_filter = (
        f'<Filter name="chromosome_name" value="{chromosome}"/>'
        if chromosome else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE Query>'
        '<Query virtualSchemaName="default" formatter="TSV" header="1" uniqueRows="1" count="" datasetConfigVersion="0.6">'
        f'<Dataset name="{dataset}" interface="default">'
        '<Filter name="biotype" value="protein_coding"/>'
        f'{chr_filter}'
        '<Attribute name="ensembl_gene_id"/>'
        '<Attribute name="external_gene_name"/>'
        '<Attribute name="chromosome_name"/>'
        '<Attribute name="strand"/>'
        '<Attribute name="start_position"/>'
        '<Attribute name="end_position"/>'
        '</Dataset>'
        '</Query>'
    )


def _fetch_gene_coords(requests, species: str, chromosome: str | None) -> tuple[pd.DataFrame, bytes]:
    dataset = SPECIES_DATASET[species]
    xml = _biomart_query_xml(dataset, chromosome)
    try:
        resp = requests.get(
            BIOMART_URL,
            params={"query": xml},
            headers={"User-Agent": USER_AGENT},
            timeout=180,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"BioMart request failed: {e}", fetcher=SOURCE_NAME)

    raw = resp.content
    if raw.lstrip().startswith(b"Query ERROR") or b"<html" in raw[:200].lower():
        die(f"BioMart returned error/HTML: {raw[:400]!r}", fetcher=SOURCE_NAME)

    df = pd.read_csv(io.BytesIO(raw), sep="\t")
    # Normalize column names
    rename: dict[str, str] = {}
    for col in df.columns:
        lc = col.lower()
        if "gene stable id" in lc or "ensembl_gene_id" in lc:
            rename[col] = "ensembl_id"
        elif "gene name" in lc or "external_gene_name" in lc:
            rename[col] = "symbol"
        elif "chromosome" in lc:
            rename[col] = "chromosome"
        elif "strand" in lc:
            rename[col] = "strand"
        elif "start" in lc:
            rename[col] = "start"
        elif "end" in lc:
            rename[col] = "end"
    df = df.rename(columns=rename)
    needed = {"ensembl_id", "symbol", "chromosome", "strand", "start", "end"}
    missing = needed - set(df.columns)
    if missing:
        die(f"BioMart TSV missing columns after rename: {sorted(missing)}\n  got: {list(df.columns)}", fetcher=SOURCE_NAME)

    df["tss"] = df.apply(lambda r: r["start"] if r["strand"] == 1 else r["end"], axis=1)
    return df, raw


def query_head_to_head(
    species: str,
    chromosome: str | None,
    max_distance: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)

    chr_tag = f"chr{chromosome}" if chromosome else "allchr"
    cache_key = f"genomic__head_to_head__{species}__{chr_tag}__d{max_distance}"
    tsv_path = out if out else (cache_dir / cache_key).with_suffix(".tsv")
    meta_path = tsv_path.with_suffix(".meta.json")

    if not refresh and tsv_path.exists() and meta_path.exists():
        return tsv_path

    print(f"[ensembl_genomic] fetching protein-coding gene coordinates ({species}, chr={chromosome or 'all'}) ...", file=sys.stderr)
    genes_df, raw_bytes = _fetch_gene_coords(requests, species, chromosome)
    source_sha = sha256_bytes(raw_bytes)
    print(f"[ensembl_genomic] {len(genes_df)} genes fetched", file=sys.stderr)

    # Compute head-to-head pairs:
    # For each chromosome, find + strand genes and - strand genes.
    # A pair (A, B) is head-to-head if:
    #   A is on + strand (TSS = start), B is on - strand (TSS = end)
    #   |A.tss - B.tss| <= max_distance
    #   They are on the same chromosome.
    records = []
    for chrom, chrom_df in genes_df.groupby("chromosome"):
        plus = chrom_df[chrom_df["strand"] == 1].copy()
        minus = chrom_df[chrom_df["strand"] == -1].copy()
        if plus.empty or minus.empty:
            continue

        # Sort both by TSS for efficient nearest-neighbor search
        plus_sorted = plus.sort_values("tss").reset_index(drop=True)
        minus_sorted = minus.sort_values("tss").reset_index(drop=True)

        # For each + gene, find all - genes with |tss_plus - tss_minus| <= max_distance
        # Use a two-pointer approach: O(n log n) sort + O(n) sweep.
        j_lo = 0
        for _, pg in plus_sorted.iterrows():
            # Advance j_lo past genes too far to the left
            while j_lo < len(minus_sorted) and minus_sorted.loc[j_lo, "tss"] < pg["tss"] - max_distance:
                j_lo += 1
            j = j_lo
            while j < len(minus_sorted) and minus_sorted.loc[j, "tss"] <= pg["tss"] + max_distance:
                mg = minus_sorted.loc[j]
                dist = abs(int(pg["tss"]) - int(mg["tss"]))
                # Emit both directions (so either gene can be the query gene)
                for a, b in [(pg, mg), (mg, pg)]:
                    records.append({
                        "ensembl_id": a["ensembl_id"],
                        "symbol": a["symbol"],
                        "entrez_id": "",
                        "species": species,
                        "source": SOURCE_NAME,
                        "chromosome": str(chrom),
                        "strand": int(a["strand"]),
                        "tss": int(a["tss"]),
                        "partner_ensembl_id": b["ensembl_id"],
                        "partner_symbol": b["symbol"],
                        "tss_distance": dist,
                    })
                j += 1

    if not records:
        die(
            f"No head-to-head pairs found within {max_distance} bp "
            f"(species={species}, chromosome={chromosome or 'all'}).\n"
            f"  Try increasing --max-distance (default is 1000 bp).",
            fetcher=SOURCE_NAME,
        )

    df = pd.DataFrame(records).drop_duplicates(subset=["ensembl_id", "partner_ensembl_id"]).reset_index(drop=True)
    # Unique genes in the pairs
    n_unique_genes = df["ensembl_id"].nunique()

    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(tsv_path, sep="\t", index=False)
    output_sha = hashlib.sha256(tsv_path.read_bytes()).hexdigest()

    meta = {
        "set": cache_key,
        "query_type": "genomic",
        "feature": "head_to_head",
        "species": species,
        "chromosome": chromosome,
        "max_distance_bp": max_distance,
        "n_pairs": len(df) // 2,
        "n_unique_genes": n_unique_genes,
        "n_rows": len(df),
        "fetched_at": iso_now(),
        "source": SOURCE_NAME,
        "source_url": BIOMART_URL,
        "source_version": "Ensembl BioMart (current release; fetched live); protein_coding biotype filter",
        "source_sha256": source_sha,
        "output_sha256": output_sha,
        "tool_version": "gene-set-fetch 0.1.0",
        "reference": "Trinklein et al. (2004) Genome Res 14(1):62-66 — bidirectional promoters in human genome",
        "notes": (
            "Each gene in a pair appears twice (once as query, once as partner). "
            "TSS defined as: start_position for + strand, end_position for - strand. "
            "Only protein-coding genes included."
        ),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    print(f"[ensembl_genomic] {n_unique_genes} unique genes in {len(df)//2} head-to-head pairs → {tsv_path}", file=sys.stderr)
    return tsv_path
