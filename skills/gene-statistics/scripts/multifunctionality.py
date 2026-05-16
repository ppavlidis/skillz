#!/usr/bin/env python3
"""Per-gene multifunctionality score (Gillis & Pavlidis 2011).

For each gene g annotated (true-path-propagated) to GO BP terms G_g:

    MF(g) = Σᵢ∈G_g  1 / (nᵢ · (N − nᵢ))

where nᵢ = number of genes annotated to term i, N = annotated universe
size. Output is the per-gene ranking; raw scores are not directly
interpretable but their order is.

Defaults:
- aspect: BP only (P in GAF)
- evidence codes: ALL (IEA included — not lower quality per user policy)
- annotations: propagated (true-path) via locally cached go.obo
- background: annotated universe (every gene with >=1 BP annotation)
- source: GAF (GO Consortium per-species file)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

# Sibling-skill path: skillz/skills/gene-set-fetch/. The whole skill ecosystem
# assumes this layout. If gene-set-fetch is missing, --background-set will
# fail loud with instructions.
SKILLZ_ROOT = Path(__file__).resolve().parent.parent.parent
GENE_SET_FETCH = SKILLZ_ROOT / "gene-set-fetch" / "scripts" / "fetch.py"
GENE_SET_FETCH_VENV = SKILLZ_ROOT / "gene-set-fetch" / ".venv" / "bin" / "python"

TOOL_VERSION = "0.1.0"
CACHE_DIR = Path.home() / ".cache" / "gene-statistics"
REFS_DIR = CACHE_DIR / "refs"

USER_AGENT = (
    f"gene-statistics/{TOOL_VERSION} (https://github.com/ppavlidis/skillz; "
    f"+contact via repo issues)"
)

GAF_URL = {
    "human": "https://current.geneontology.org/annotations/goa_human.gaf.gz",
    "mouse": "https://current.geneontology.org/annotations/mgi.gaf.gz",
}
GO_OBO_URL = "http://purl.obolibrary.org/obo/go.obo"

ASPECT_TO_GAF = {"BP": "P", "MF": "F", "CC": "C"}
ASPECT_TO_NAMESPACE = {
    "BP": "biological_process",
    "MF": "molecular_function",
    "CC": "cellular_component",
}

_GAF_DATE_RE = re.compile(rb"^!date-generated:\s*(\S+)", re.MULTILINE)
_DATA_VERSION_RE = re.compile(r"^data-version:\s*(\S+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers (fail-loud, http, sha256, cache)
# ---------------------------------------------------------------------------


def die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print("[gene-statistics:multifunctionality] ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def _iso_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> str:
    import requests
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=600, stream=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"download failed: {url}\n  {e}")
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    h = hashlib.sha256()
    with tmp.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                h.update(chunk)
    tmp.replace(dest)
    return h.hexdigest()


def _ensure_refs(species: str) -> dict:
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    gaf_name = "goa_human.gaf.gz" if species == "human" else "mgi.gaf.gz"
    gaf_path = REFS_DIR / gaf_name
    obo_path = REFS_DIR / "go.obo"

    if not gaf_path.exists() or gaf_path.stat().st_size == 0:
        _download(GAF_URL[species], gaf_path)
    if not obo_path.exists() or obo_path.stat().st_size == 0:
        _download(GO_OBO_URL, obo_path)

    gaf_sha = _sha256_path(gaf_path)
    obo_sha = _sha256_path(obo_path)

    # Pull date-generated from GAF header.
    gaf_date = ""
    try:
        with gzip.open(gaf_path, "rb") as f:
            head = f.read(8192)
        m = _GAF_DATE_RE.search(head)
        if m:
            gaf_date = m.group(1).decode("utf-8", errors="replace").strip()
    except Exception:
        pass

    # Pull data-version from OBO header.
    obo_version = ""
    try:
        with obo_path.open("rb") as f:
            head = f.read(8192)
        m = _DATA_VERSION_RE.search(head.decode("utf-8", errors="replace"))
        if m:
            obo_version = m.group(1).strip()
    except Exception:
        pass

    return {
        "gaf_path": gaf_path, "gaf_sha256": gaf_sha, "gaf_date_generated": gaf_date,
        "obo_path": obo_path, "obo_sha256": obo_sha, "obo_data_version": obo_version,
    }


# ---------------------------------------------------------------------------
# GAF parsing + propagation
# ---------------------------------------------------------------------------


def _iter_gaf_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line or line.startswith("!"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 15:
                continue
            yield cols


def _load_direct_annotations(gaf_path: Path, gaf_aspect_code: str,
                             evidence_codes: set | None,
                             symbol_whitelist: set | None):
    """Return:
       - gene_meta: dict[gene_id, dict(symbol, uniprot)]
       - direct: dict[gene_id, set[term_id]] — only terms in the chosen aspect.

    symbol_whitelist (if provided): an uppercase set of gene symbols. Only
    GAF rows whose Symbol column matches will be included. Used to restrict
    the MF computation to a specific background (e.g. protein-coding).
    """
    gene_meta: dict[str, dict] = {}
    direct: dict[str, set] = defaultdict(set)
    for cols in _iter_gaf_rows(gaf_path):
        if cols[8] != gaf_aspect_code:
            continue
        ev = cols[6]
        if evidence_codes and ev not in evidence_codes:
            continue
        symbol = cols[2]
        if symbol_whitelist is not None and symbol.upper() not in symbol_whitelist:
            continue
        db = cols[0]
        db_id = cols[1]
        gene_id = f"{db}:{db_id}" if db_id else ""
        if not gene_id:
            continue
        uniprot = db_id if db == "UniProtKB" else ""
        if gene_id not in gene_meta:
            gene_meta[gene_id] = {"symbol": symbol, "uniprot": uniprot}
        direct[gene_id].add(cols[4])
    return gene_meta, direct


def _resolve_background(species: str, background_set: str | None,
                        background_tsv: Path | None) -> tuple[set | None, dict]:
    """Resolve the background restriction. Returns (symbol_whitelist, provenance).

    If both background_set and background_tsv are None, returns (None, {})
    meaning "no restriction; full annotated universe".

    background_set: invoke gene-set-fetch as a subprocess to obtain the set.
    background_tsv: read a user-supplied TSV directly. Must have a 'symbol'
                    column.
    """
    if background_set is None and background_tsv is None:
        return None, {"background_kind": "annotated_universe"}

    if background_tsv is not None:
        tsv_path = Path(background_tsv)
        if not tsv_path.exists():
            die(f"--background-tsv path does not exist: {tsv_path}")
        provenance = {
            "background_kind": "user_supplied_tsv",
            "background_tsv_path": str(tsv_path),
            "background_tsv_sha256": _sha256_path(tsv_path),
        }
    else:  # background_set
        if not GENE_SET_FETCH.exists():
            die(
                f"gene-set-fetch sibling skill not found at {GENE_SET_FETCH}.\n"
                f"  install it under {SKILLZ_ROOT}/gene-set-fetch/ so this skill "
                f"can call it for --background-set, OR pass --background-tsv with "
                f"a pre-fetched gene list."
            )
        python = str(GENE_SET_FETCH_VENV) if GENE_SET_FETCH_VENV.exists() else sys.executable
        try:
            res = subprocess.run(
                [python, str(GENE_SET_FETCH), background_set],
                check=True, capture_output=True, text=True, timeout=600,
            )
        except subprocess.CalledProcessError as e:
            die(
                f"gene-set-fetch failed to produce '{background_set}'.\n"
                f"  stderr: {e.stderr[:500]}"
            )
        except FileNotFoundError as e:
            die(f"python invocation failed for gene-set-fetch: {e}")
        tsv_path_str = (res.stdout or "").strip().splitlines()[-1] if res.stdout else ""
        tsv_path = Path(tsv_path_str)
        if not tsv_path.exists():
            die(
                f"gene-set-fetch printed a path that doesn't exist: {tsv_path_str!r}\n"
                f"  stdout: {res.stdout[:300]}\n  stderr: {res.stderr[:300]}"
            )
        provenance = {
            "background_kind": "gene_set_fetch",
            "background_set_name": background_set,
            "background_tsv_path": str(tsv_path),
            "background_tsv_sha256": _sha256_path(tsv_path),
        }

    df = pd.read_csv(tsv_path, sep="\t", dtype="string", low_memory=False)
    if "symbol" not in df.columns:
        die(
            f"background TSV at {tsv_path} has no 'symbol' column "
            f"(got: {list(df.columns)}); cannot cross-walk to GAF Symbol."
        )
    whitelist = {s.upper() for s in df["symbol"].dropna() if s}
    if not whitelist:
        die(f"background TSV at {tsv_path} produced an empty symbol set")
    provenance["background_symbol_count"] = len(whitelist)
    return whitelist, provenance


def _propagate(direct: dict, graph, namespace: str) -> tuple[dict, dict]:
    """Apply the GO true-path rule. Returns:
       - gene_terms: dict[gene_id, frozenset[term_id]] propagated, restricted to namespace
       - term_genes: dict[term_id, set[gene_id]] inverse mapping (for n_i)
    """
    import networkx as nx

    # Pre-compute ancestor closure for every term mentioned in direct annotations.
    # obonet edges: term -> parent (is_a), so ancestors = nx.descendants in this DiGraph.
    all_direct_terms = set()
    for terms in direct.values():
        all_direct_terms.update(terms)

    anc_cache: dict[str, set] = {}
    for t in all_direct_terms:
        if t not in graph:
            anc_cache[t] = set()
            continue
        ancs = nx.descendants(graph, t)
        # Restrict to terms in the requested namespace.
        ancs_ns = {a for a in ancs if graph.nodes.get(a, {}).get("namespace") == namespace}
        # Include the term itself if it's in the right namespace.
        if graph.nodes.get(t, {}).get("namespace") == namespace:
            ancs_ns.add(t)
        anc_cache[t] = ancs_ns

    gene_terms: dict[str, frozenset] = {}
    term_genes: dict[str, set] = defaultdict(set)
    for g, terms in direct.items():
        propagated = set()
        for t in terms:
            propagated.update(anc_cache.get(t, set()))
        if propagated:
            gene_terms[g] = frozenset(propagated)
            for t in propagated:
                term_genes[t].add(g)
    return gene_terms, dict(term_genes)


# ---------------------------------------------------------------------------
# MF computation
# ---------------------------------------------------------------------------


def _compute_mf(gene_terms: dict, term_genes: dict, N: int) -> tuple[dict, dict, int]:
    """Compute MF(g) per gene. Returns (mf_per_gene, term_weight, n_terms_used)."""
    if N <= 1:
        die(f"annotated universe has only {N} gene(s); MF is undefined")
    term_weight: dict[str, float] = {}
    for t, gs in term_genes.items():
        n_i = len(gs)
        if 1 <= n_i < N:
            term_weight[t] = 1.0 / (n_i * (N - n_i))
        # else: degenerate (n_i == 0 or n_i == N), skip
    mf: dict[str, float] = {}
    for g, terms in gene_terms.items():
        mf[g] = sum(term_weight.get(t, 0.0) for t in terms)
    return mf, term_weight, len(term_weight)


def _rank_and_percentile(mf: dict) -> tuple[dict, dict]:
    """Higher MF = better rank (rank 1 = most multifunctional)."""
    items = sorted(mf.items(), key=lambda kv: (-kv[1], kv[0]))  # tiebreak by gene_id for stability
    ranks: dict[str, int] = {}
    percentiles: dict[str, float] = {}
    N = len(items)
    for i, (g, _v) in enumerate(items, start=1):
        ranks[g] = i
        percentiles[g] = (N - i + 1) / N
    return ranks, percentiles


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cache_paths(species: str, aspect: str, evidence_tag: str, source: str,
                 background_tag: str, out: Path | None):
    if out is not None:
        tsv_path = Path(out)
        meta_path = tsv_path.with_suffix(".meta.json")
        return tsv_path, meta_path
    stem = f"multifunctionality__{source}__{species}__{aspect}__{evidence_tag}__{background_tag}"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{stem}.tsv", CACHE_DIR / f"{stem}.meta.json"


def _is_fresh(tsv_path: Path, meta_path: Path) -> bool:
    if not (tsv_path.exists() and meta_path.exists()):
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return False
    return meta.get("output_sha256") == _sha256_path(tsv_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-gene multifunctionality (Gillis & Pavlidis 2011).")
    parser.add_argument("--species", choices=["human", "mouse"], default="human")
    parser.add_argument("--source", choices=["gaf"], default="gaf",
                        help="annotation source (only gaf in v0.1)")
    parser.add_argument("--aspect", choices=["BP", "MF", "CC"], default="BP",
                        help="GO aspect (default BP; MF across aspects is not meaningful)")
    parser.add_argument("--evidence-codes", default="all",
                        help="comma-separated list of GO evidence codes to include, "
                             "or 'all' (default; do NOT exclude IEA — it isn't lower quality)")
    parser.add_argument("--background-set", default=None,
                        help="restrict the MF computation to genes in a gene-set-fetch set "
                             "(default: protein_coding_<species>_strict; pass 'annotated' to "
                             "use the full annotated universe). Cross-walks via symbol.")
    parser.add_argument("--background-tsv", default=None, type=Path,
                        help="restrict to a user-supplied TSV (must have a 'symbol' column)")
    parser.add_argument("--refresh", action="store_true", help="re-fetch and recompute even if cached")
    parser.add_argument("--out", type=Path, default=None, help="output TSV path (default: cache)")
    args = parser.parse_args()

    # Default --background-set per user policy ("we usually only do this for
    # protein-coding genes"). Pass --background-set annotated to opt out.
    if args.background_set is None and args.background_tsv is None:
        args.background_set = f"protein_coding_{args.species}_strict"
    if args.background_set == "annotated":
        args.background_set = None  # i.e. no restriction

    evidence_tag = args.evidence_codes
    evidence_filter: set | None = None
    if args.evidence_codes != "all":
        evidence_filter = {c.strip() for c in args.evidence_codes.split(",") if c.strip()}
        evidence_tag = "+".join(sorted(evidence_filter))

    # Background tag for cache key.
    if args.background_tsv is not None:
        background_tag = f"bgtsv-{args.background_tsv.stem}"
    elif args.background_set is not None:
        background_tag = f"bg-{args.background_set}"
    else:
        background_tag = "bg-annotated"

    tsv_path, meta_path = _cache_paths(args.species, args.aspect, evidence_tag,
                                       args.source, background_tag, args.out)
    if not args.refresh and _is_fresh(tsv_path, meta_path):
        print(tsv_path)
        return 0

    # Resolve background BEFORE downloading large files — if it fails, fail fast.
    symbol_whitelist, bg_provenance = _resolve_background(
        args.species, args.background_set, args.background_tsv,
    )

    refs = _ensure_refs(args.species)
    namespace = ASPECT_TO_NAMESPACE[args.aspect]
    gaf_aspect = ASPECT_TO_GAF[args.aspect]

    gene_meta, direct = _load_direct_annotations(
        refs["gaf_path"], gaf_aspect, evidence_filter, symbol_whitelist,
    )
    if not direct:
        die(
            f"zero gene annotations found in GAF after aspect={args.aspect} + "
            f"evidence filter ({args.evidence_codes}) + background "
            f"({bg_provenance.get('background_kind')}). Check filters."
        )

    try:
        import obonet
    except ImportError as e:
        die(f"obonet not installed; pip install obonet ({e})")
    graph = obonet.read_obo(str(refs["obo_path"]))

    gene_terms, term_genes = _propagate(direct, graph, namespace)
    N = len(gene_terms)
    if N == 0:
        die(f"after propagation + namespace filter ({namespace}), zero genes remained")

    mf, term_weight, n_terms_used = _compute_mf(gene_terms, term_genes, N)
    ranks, percentiles = _rank_and_percentile(mf)

    # Sort genes by rank for output.
    rows = []
    for g in sorted(mf.keys(), key=lambda gg: ranks[gg]):
        meta = gene_meta.get(g, {})
        rows.append({
            "gene_id": g,
            "gene_symbol": meta.get("symbol", ""),
            "gene_uniprot": meta.get("uniprot", ""),
            "n_annotations": len(gene_terms[g]),
            "mf_score": mf[g],
            "mf_rank": ranks[g],
            "mf_percentile": percentiles[g],
            "species": args.species,
            "source": args.source,
        })

    df = pd.DataFrame(rows, columns=[
        "gene_id", "gene_symbol", "gene_uniprot", "n_annotations",
        "mf_score", "mf_rank", "mf_percentile", "species", "source",
    ])

    # Atomic write.
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tsv_path.with_suffix(tsv_path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(tsv_path)
    output_sha = _sha256_path(tsv_path)

    meta_payload = {
        "operation": "multifunctionality",
        "source": args.source,
        "species": args.species,
        "aspect": args.aspect,
        "namespace": namespace,
        "evidence_codes_filter": "all" if evidence_filter is None else sorted(evidence_filter),
        "propagated": True,
        "n_genes_in_background": N,
        "n_terms_used_in_calculation": n_terms_used,
        "n_terms_excluded_degenerate": len(term_genes) - n_terms_used,
        "fetched_at": _iso_now(),
        "gaf_url": GAF_URL[args.species],
        "gaf_sha256": refs["gaf_sha256"],
        "gaf_date_generated": refs["gaf_date_generated"],
        "obo_url": GO_OBO_URL,
        "obo_sha256": refs["obo_sha256"],
        "obo_data_version": refs["obo_data_version"],
        "output_sha256": output_sha,
        "tool_version": TOOL_VERSION,
        "formula": "MF(g) = sum_{i in G_g} 1/(n_i * (N - n_i)); rank-normalized to percentile",
        "reference": "Gillis J, Pavlidis P (2011) PLoS ONE 6(2):e17258",
    }
    meta_payload.update(bg_provenance)
    tmp_meta = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp_meta.write_text(json.dumps(meta_payload, indent=2, sort_keys=True) + "\n")
    tmp_meta.replace(meta_path)

    print(tsv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
