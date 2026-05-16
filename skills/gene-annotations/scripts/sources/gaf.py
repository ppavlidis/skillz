"""GAF (GO Annotation File) source — per-species annotation files from the
GO Consortium.

Why this instead of NCBI's gene2go.gz: as of 2026, gene2go.gz has grown to
~1.3 GB compressed (3.3 GB uncompressed) — almost entirely from electronic
(IEA) annotations across all species. Downloading that for a "what GO
terms does this gene have" lookup is unreasonable. The GO Consortium
publishes per-species GAF files at https://current.geneontology.org/annotations/
that contain the same annotations curated per-species, sized 10-20 MB
compressed. Same data, sane size.

Files used:
- human: https://current.geneontology.org/annotations/goa_human.gaf.gz
- mouse: https://current.geneontology.org/annotations/mgi.gaf.gz

GAF v2.2 columns (positional, see http://geneontology.org/docs/go-annotation-file-gaf-format-2.2/):
  1. DB                  e.g. "UniProtKB" (human) or "MGI" (mouse)
  2. DB Object ID        the accession in that DB
  3. DB Object Symbol    gene symbol
  4. Qualifier           e.g. "involved_in", "enables", "NOT|involved_in"
  5. GO ID               GO term
  6. DB:Reference        evidence reference(s)
  7. Evidence Code       IEA, IDA, EXP, etc.
  8. With (or) From      supporting IDs
  9. Aspect              F (MF), P (BP), C (CC)
 10. DB Object Name      gene description
 11. DB Object Synonym   pipe-separated aliases
 12. DB Object Type      "protein", "gene_product", etc.
 13. Taxon               taxon:9606, optionally taxon:9606|taxon:11676
 14. Date                YYYYMMDD
 15. Assigned By         curator
 16. Annotation Extension
 17. Gene Product Form ID

The GAF file does NOT carry GO term labels — those come from the GO ontology
itself. We load go-basic.obo via obonet (once, cached) to get labels and to
compute ancestors/descendants for propagation.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from ._common import (
    CACHE_DIR,
    SPECIES_TAXON,
    SourceInfo,
    classify_gene_input,
    die,
    http_get,
    iso_now,
    require_module,
    sha256_bytes,
)

SOURCE_NAME = "gaf"
REFS_DIR = CACHE_DIR / "refs"

GAF_URL = {
    "human": "https://current.geneontology.org/annotations/goa_human.gaf.gz",
    "mouse": "https://current.geneontology.org/annotations/mgi.gaf.gz",
}
GO_OBO_URL = "http://purl.obolibrary.org/obo/go.obo"

ASPECT_LONG = {"F": "molecular_function", "P": "biological_process", "C": "cellular_component"}

_DATA_VERSION_RE = re.compile(r"^data-version:\s*(\S+)", re.MULTILINE)
_GAF_DATE_RE = re.compile(rb"^!date-generated:\s*(\S+)", re.MULTILINE)


def _download_to_cache(url: str, cache_subpath: str, requests) -> tuple[Path, str]:
    """Download `url` to ~/.cache/gene-annotations/refs/<cache_subpath> if not
    already there. Returns (path, sha256 of bytes)."""
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REFS_DIR / cache_subpath
    if out_path.exists() and out_path.stat().st_size > 0:
        # Trust the existing file; recompute sha256 for provenance.
        return out_path, _sha256_of_path(out_path)
    try:
        resp = http_get(url, requests, timeout=600, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"download failed: {url}\n  {e}", source=SOURCE_NAME)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    h = __import__("hashlib").sha256()
    with tmp.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                h.update(chunk)
    tmp.replace(out_path)
    return out_path, h.hexdigest()


def _sha256_of_path(path: Path) -> str:
    h = __import__("hashlib").sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_gaf_cached(species: str, requests) -> tuple[Path, str, str]:
    """Ensure the per-species GAF is cached. Returns (path, sha256, date_generated)."""
    url = GAF_URL.get(species)
    if url is None:
        die(f"unsupported species: {species}", source=SOURCE_NAME)
    name = "goa_human.gaf.gz" if species == "human" else "mgi.gaf.gz"
    path, sha = _download_to_cache(url, name, requests)
    # Pull date-generated from the GAF header.
    date = ""
    try:
        with gzip.open(path, "rb") as f:
            head = f.read(8192)
        m = _GAF_DATE_RE.search(head)
        if m:
            date = m.group(1).decode("utf-8", errors="replace").strip()
    except Exception:
        pass
    return path, sha, date


def _ensure_obo_cached(requests) -> tuple[Path, str, str]:
    """Ensure go-basic.obo is cached. Returns (path, sha256, data_version)."""
    path, sha = _download_to_cache(GO_OBO_URL, "go.obo", requests)
    version = ""
    try:
        with path.open("rb") as f:
            head = f.read(8192)
        m = _DATA_VERSION_RE.search(head.decode("utf-8", errors="replace"))
        if m:
            version = m.group(1).strip()
    except Exception:
        pass
    return path, sha, version


# ---------------------------------------------------------------------------
# GAF parsing
# ---------------------------------------------------------------------------


def _iter_gaf_rows(path: Path) -> Iterable[list[str]]:
    """Yield tab-split GAF rows, skipping comment lines (starting with '!')."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line or line.startswith("!"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 15:
                continue
            yield cols


def _gaf_to_df(path: Path) -> pd.DataFrame:
    """Load the GAF into a DataFrame with our standard column names."""
    records = []
    for cols in _iter_gaf_rows(path):
        # Defensive: pad short rows.
        cols = cols + [""] * (17 - len(cols))
        records.append({
            "db": cols[0],
            "db_id": cols[1],
            "symbol": cols[2],
            "qualifier": cols[3],
            "go_id": cols[4],
            "evidence_code": cols[6],
            "aspect": cols[8],
            "synonyms": cols[10],
            "taxon": cols[12],
        })
    return pd.DataFrame.from_records(records)


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def _build_obo_graph(obo_path: Path):
    obonet = require_module("obonet", "pip install obonet", SOURCE_NAME)
    return obonet.read_obo(str(obo_path))


def _descendants(graph, term: str) -> set[str]:
    """Return all terms whose ancestor (via is_a) includes `term`. Inclusive of self."""
    # obonet edges: u --is_a--> v means u is_a v. So descendants of `term`
    # are nodes with `term` in their successor closure.
    import networkx as nx
    out = {term}
    if term not in graph:
        return out
    # Reverse direction: for descendants, we want nodes from which `term`
    # is reachable via outgoing is_a edges → predecessors in the standard
    # obonet DiGraph orientation.
    for n in nx.ancestors(graph.reverse(copy=False), term):
        out.add(n)
    return out


def _ancestors(graph, term: str) -> set[str]:
    """Return all is_a ancestors of `term`. Inclusive of self."""
    import networkx as nx
    out = {term}
    if term not in graph:
        return out
    for n in nx.descendants(graph.reverse(copy=False), term):
        # ^^^ same trick: ancestors in our directed graph are nx-descendants
        # of the reversed graph. Wait — actually obonet edges point TERM -> PARENT
        # so ancestors of TERM are nx.descendants(graph, term).
        pass
    out.update(nx.descendants(graph, term))
    return out


def _term_labels(graph, terms: Iterable[str]) -> dict[str, dict]:
    out = {}
    for t in terms:
        d = graph.nodes.get(t, {})
        out[t] = {
            "name": d.get("name", ""),
            "namespace": d.get("namespace", ""),
        }
    return out


def _aspect_long(short: str) -> str:
    return ASPECT_LONG.get(short, short)


def _make_row(record: dict, term_id: str, propagated: bool, propagated_from: str, species: str, labels: dict) -> dict:
    db = record["db"]
    db_id = record["db_id"]
    uniprot = db_id if db == "UniProtKB" else ""
    return {
        "gene_id": f"{db}:{db_id}" if db_id else "",
        "gene_symbol": record["symbol"],
        "gene_uniprot": uniprot,
        "gene_entrez": "",
        "term_id": term_id,
        "term_label": labels.get(term_id, {}).get("name", ""),
        "term_aspect": _aspect_long(record["aspect"]),
        "evidence_code": record["evidence_code"],
        "qualifier": record["qualifier"],
        "propagated": propagated,
        "species": species,
        "source": SOURCE_NAME,
        "propagated_from_term_id": propagated_from,
    }


def genes_with_annotation(go_term: str, species: str, direct: bool):
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    gaf_path, gaf_sha, gaf_date = _ensure_gaf_cached(species, requests)
    obo_path, obo_sha, obo_version = _ensure_obo_cached(requests)
    graph = _build_obo_graph(obo_path)

    target_set: set[str] = {go_term} if direct else _descendants(graph, go_term)
    labels = _term_labels(graph, target_set)

    rows = []
    for cols in _iter_gaf_rows(gaf_path):
        if cols[4] not in target_set:
            continue
        record = {
            "db": cols[0], "db_id": cols[1], "symbol": cols[2],
            "qualifier": cols[3], "evidence_code": cols[6], "aspect": cols[8],
        }
        is_direct = cols[4] == go_term
        rows.append(_make_row(
            record, term_id=cols[4],
            propagated=(not is_direct),
            propagated_from=("" if is_direct else cols[4]),
            species=species, labels=labels,
        ))

    df = pd.DataFrame(rows, columns=[
        "gene_id", "gene_symbol", "gene_uniprot", "gene_entrez",
        "term_id", "term_label", "term_aspect",
        "evidence_code", "qualifier", "propagated",
        "species", "source", "propagated_from_term_id",
    ])
    return df, SourceInfo(
        url=f"{GAF_URL[species]} + {GO_OBO_URL}",
        version=f"GAF (date-generated: {gaf_date}); GO OBO (data-version: {obo_version})",
        sha256=sha256_bytes((gaf_sha + "|" + obo_sha).encode()),
        extras={
            "gaf_sha256": gaf_sha,
            "gaf_date_generated": gaf_date,
            "obo_sha256": obo_sha,
            "obo_data_version": obo_version,
            "term_set_size": len(target_set),
        },
    )


def annotations_of_gene(gene_input: str, species: str, direct: bool):
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    gaf_path, gaf_sha, gaf_date = _ensure_gaf_cached(species, requests)
    obo_path, obo_sha, obo_version = _ensure_obo_cached(requests)

    # Resolve gene_input. Strategy:
    # - if it looks like DB:ID (e.g. UniProtKB:P04637 or MGI:88037), match db_id
    # - if it's a bare ID prefixed with the species' GAF db, match
    # - else treat as a symbol and match the Symbol column (case-insensitive)
    target_db = "UniProtKB" if species == "human" else "MGI"
    cls = classify_gene_input(gene_input)
    db_id_match = ""
    symbol_match = ""
    if cls in ("uniprot_prefixed", "other_prefixed") and ":" in gene_input:
        db_id_match = gene_input
    elif cls == "ensembl":
        # No direct match in GAF — fall back to symbol matching using gene_info.
        # For v0.1 we punt: ensembl IDs aren't well-supported in GAF; tell user.
        die(
            f"GAF source doesn't index by Ensembl ID directly. Pass the gene "
            f"symbol or {target_db}:ACCESSION instead. (Future v0.2 could add "
            f"cross-walk via NCBI gene_info or Ensembl xrefs.)",
            source=SOURCE_NAME,
        )
    elif cls == "entrez":
        die(
            f"GAF source isn't keyed by Entrez. Pass the gene symbol or "
            f"{target_db}:ACCESSION instead.",
            source=SOURCE_NAME,
        )
    else:  # symbol
        symbol_match = gene_input.upper()

    # Walk the GAF for matching gene rows. The file is ~15MB; one pass is fine.
    matched_records: list[dict] = []
    for cols in _iter_gaf_rows(gaf_path):
        if symbol_match and cols[2].upper() != symbol_match:
            continue
        if db_id_match:
            full_id = f"{cols[0]}:{cols[1]}"
            if full_id != db_id_match:
                continue
        matched_records.append({
            "db": cols[0], "db_id": cols[1], "symbol": cols[2],
            "qualifier": cols[3], "go_id": cols[4],
            "evidence_code": cols[6], "aspect": cols[8],
        })

    if not matched_records:
        die(
            f"no GAF rows found for {gene_input!r} (species {species}). "
            f"If you passed a symbol, check it's the official one for the "
            f"species ({target_db} keying); if a DB ID, ensure prefix.",
            source=SOURCE_NAME,
        )

    direct_term_ids = sorted({r["go_id"] for r in matched_records})

    graph = _build_obo_graph(obo_path)
    # Pre-compute ancestor sets for direct terms.
    anc_map: dict[str, set[str]] = {}
    all_terms_in_play: set[str] = set(direct_term_ids)
    if not direct:
        for tid in direct_term_ids:
            ancs = _ancestors(graph, tid)
            anc_map[tid] = ancs
            all_terms_in_play.update(ancs)

    labels = _term_labels(graph, all_terms_in_play)

    rows: list[dict] = []
    # Direct annotations.
    for r in matched_records:
        rows.append(_make_row(r, term_id=r["go_id"], propagated=False, propagated_from="", species=species, labels=labels))

    # Propagated annotations.
    if not direct:
        seen_keys: set[tuple] = set(
            (r["gene_id"], r["term_id"], r["evidence_code"], r["qualifier"])
            for r in rows
        )
        for r in matched_records:
            tid = r["go_id"]
            for anc in anc_map.get(tid, set()) - {tid}:
                row = _make_row(r, term_id=anc, propagated=True, propagated_from=tid, species=species, labels=labels)
                key = (row["gene_id"], row["term_id"], row["evidence_code"], row["qualifier"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(row)

    df = pd.DataFrame(rows, columns=[
        "gene_id", "gene_symbol", "gene_uniprot", "gene_entrez",
        "term_id", "term_label", "term_aspect",
        "evidence_code", "qualifier", "propagated",
        "species", "source", "propagated_from_term_id",
    ])
    return df, SourceInfo(
        url=f"{GAF_URL[species]} + {GO_OBO_URL}",
        version=f"GAF (date-generated: {gaf_date}); GO OBO (data-version: {obo_version})",
        sha256=sha256_bytes((gaf_sha + "|" + obo_sha).encode()),
        extras={
            "gaf_sha256": gaf_sha,
            "gaf_date_generated": gaf_date,
            "obo_sha256": obo_sha,
            "obo_data_version": obo_version,
            "n_direct_annotations": len([r for r in rows if not r["propagated"]]),
            "n_total_rows": len(rows),
        },
    )
