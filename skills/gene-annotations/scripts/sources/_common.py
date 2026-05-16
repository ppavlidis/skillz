"""Shared helpers for gene-annotations sources.

Same shape as ontology-terms / gene-set-fetch helpers: term ID conversion,
gene-input resolution to a typed ID, cache paths, sha256, atomic writes,
fail-loud die().
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

TOOL_VERSION = "0.1.0"
CACHE_DIR = Path.home() / ".cache" / "gene-annotations"

STANDARD_COLUMNS = [
    "gene_id", "gene_symbol", "gene_uniprot", "gene_entrez",
    "term_id", "term_label", "term_aspect",
    "evidence_code", "qualifier", "propagated",
    "species", "source",
]

USER_AGENT = (
    f"gene-annotations/{TOOL_VERSION} (https://github.com/ppavlidis/skillz; "
    f"+contact via repo issues)"
)

SPECIES_TAXON = {
    "human": 9606,
    "mouse": 10090,
}


# ---------------------------------------------------------------------------
# Term + gene ID handling
# ---------------------------------------------------------------------------

_COMPACT_RE = re.compile(r"^([A-Za-z]+):(\d+)$")
_GO_URI_RE = re.compile(r"^https?://purl\.obolibrary\.org/obo/GO_(\d+)$")

# Prefixes QuickGO recognizes natively as typed gene-product IDs. If the user
# passes one of these prefixes, we pass through without resolution.
_TYPED_GENE_PREFIXES = (
    "UniProtKB:", "ENSEMBL:", "ENSG", "ENSMUSG", "RNAcentral:",
    "MGI:", "FB:", "WB:", "ZFIN:", "RGD:", "TAIR:", "SGD:", "POMBASE:",
    "dictyBase:", "PomBase:", "NCBIProtein:", "Reactome:",
)


def normalize_go_term(term: str) -> str:
    """GO:0006915 or http://purl.obolibrary.org/obo/GO_0006915 -> GO:0006915."""
    m = _GO_URI_RE.match(term)
    if m:
        return f"GO:{m.group(1)}"
    if _COMPACT_RE.match(term):
        return term
    die(f"unparseable GO term: {term!r}; expected GO:0006915 or full OBO URI")


def classify_gene_input(text: str) -> str:
    """Return one of: 'uniprot_prefixed', 'ensembl', 'entrez', 'symbol', 'other_prefixed'."""
    if text.startswith("UniProtKB:"):
        return "uniprot_prefixed"
    if text.startswith("ENSG") or text.startswith("ENSMUSG") or text.startswith("ENSEMBL:"):
        return "ensembl"
    if text.isdigit():
        return "entrez"
    if any(text.startswith(p) for p in _TYPED_GENE_PREFIXES):
        return "other_prefixed"
    return "symbol"


# ---------------------------------------------------------------------------
# Provenance, cache, sha256, atomic writes
# ---------------------------------------------------------------------------


@dataclass
class SourceInfo:
    url: str
    version: str
    sha256: str
    extras: dict = field(default_factory=dict)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", s)[:120]


def cache_paths(
    operation: str,
    source: str,
    input_value: str,
    species: str,
    propagated: bool,
    out: Path | None = None,
) -> tuple[Path, Path]:
    if out is not None:
        tsv_path = Path(out)
        meta_path = tsv_path.with_suffix(".meta.json")
        return tsv_path, meta_path
    tag = "propagated" if propagated else "direct"
    stem = f"{operation}__{source}__{_sanitize(input_value)}__{species}__{tag}"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{stem}.tsv", CACHE_DIR / f"{stem}.meta.json"


def validate_schema(df: pd.DataFrame, op: str, source: str) -> None:
    missing = [c for c in STANDARD_COLUMNS if c not in df.columns]
    if missing:
        die(
            f"source {source!r} returned a DataFrame missing required columns "
            f"for operation {op!r}: {missing}\n  got: {list(df.columns)}"
        )


def is_fresh(tsv_path: Path, meta_path: Path) -> bool:
    if not (tsv_path.exists() and meta_path.exists()):
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return False
    return meta.get("output_sha256") == sha256_file(tsv_path)


def write_artifact(
    df: pd.DataFrame,
    operation: str,
    source: str,
    species: str,
    propagated: bool,
    input_value: str,
    input_resolved: str,
    source_info: SourceInfo,
    cache_dir: Path,
    out: Path | None,
    extra_meta: dict[str, Any] | None = None,
) -> Path:
    validate_schema(df, operation, source)
    tsv_path, meta_path = cache_paths(operation, source, input_value, species, propagated, out)
    tsv_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = tsv_path.with_suffix(tsv_path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(tsv_path)
    output_sha = sha256_file(tsv_path)

    meta = {
        "operation": operation,
        "source": source,
        "species": species,
        "taxon_id": SPECIES_TAXON.get(species, 0),
        "input": input_value,
        "input_resolved": input_resolved,
        "propagated": propagated,
        "n_rows": int(len(df)),
        "fetched_at": iso_now(),
        "source_url": source_info.url,
        "source_version": source_info.version,
        "source_sha256": source_info.sha256,
        "output_sha256": output_sha,
        "tool_version": TOOL_VERSION,
    }
    if source_info.extras:
        meta.update(source_info.extras)
    if extra_meta:
        meta.update(extra_meta)

    tmp_meta = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    tmp_meta.replace(meta_path)
    return tsv_path


# ---------------------------------------------------------------------------
# HTTP + fail-loud
# ---------------------------------------------------------------------------


def http_get(url: str, requests_module, **kwargs):
    headers = dict(kwargs.pop("headers", None) or {})
    headers.setdefault("User-Agent", USER_AGENT)
    return requests_module.get(url, headers=headers, **kwargs)


def die(msg: str, source: str | None = None) -> "NoReturn":  # type: ignore[name-defined]
    prefix = f"[gene-annotations:{source}] " if source else "[gene-annotations] "
    print(prefix + "ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def require_module(name: str, install_hint: str, source: str) -> Any:
    try:
        return __import__(name)
    except ImportError as e:
        die(
            f"required module '{name}' is not installed.\n"
            f"  install: {install_hint}\n  underlying error: {e}",
            source=source,
        )


# ---------------------------------------------------------------------------
# Gene-symbol resolution via UniProt REST
# ---------------------------------------------------------------------------


def resolve_symbol_to_uniprot(symbol: str, species: str, requests) -> tuple[str, dict]:
    """Resolve a gene symbol to a reviewed UniProt accession for the species.

    Returns (uniprot_accession, info_dict). Info contains gene_names and the
    raw matched record so downstream can populate the symbol/aliases.
    Calls UniProt's REST search; takes the first reviewed (Swiss-Prot) hit.
    """
    taxon = SPECIES_TAXON.get(species)
    if not taxon:
        die(f"unsupported species: {species}", source="resolve")
    url = "https://rest.uniprot.org/uniprotkb/search"
    params = {
        "query": f"gene_exact:{symbol} AND organism_id:{taxon} AND reviewed:true",
        "format": "json",
        "fields": "accession,id,gene_names,protein_name",
        "size": 5,
    }
    try:
        resp = http_get(url, requests, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"UniProt symbol resolution failed for {symbol!r}: {e}", source="resolve")

    payload = resp.json()
    hits = payload.get("results") or []
    if not hits:
        die(
            f"could not resolve gene symbol {symbol!r} to a reviewed UniProt entry "
            f"for {species} (taxon {taxon}). Try passing UniProtKB:ACCESSION or "
            f"the Ensembl gene ID instead.",
            source="resolve",
        )
    top = hits[0]
    accession = top.get("primaryAccession", "")
    return accession, {
        "matched_record": {
            "accession": accession,
            "id": top.get("uniProtkbId"),
            "protein_name": (top.get("proteinDescription") or {}).get("recommendedName", {}).get("fullName", {}).get("value", ""),
        },
        "alternates_considered": len(hits),
    }
