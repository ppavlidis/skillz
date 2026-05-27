#!/usr/bin/env python3
"""Over-Representation Analysis (ORA) — hit-list enrichment.

For each gene set S in the library:
    p = P(X >= k) under Hypergeometric(N, K, n)
where:
    N = background size (genes in the universe)
    K = |S ∩ background|
    n = |hit list ∩ background|
    k = |hit list ∩ S|

Equivalent to a one-tailed Fisher's exact test for enrichment.

MF-baseline correction: in parallel, run ORA using the top-n most
*multifunctional* genes as a synthetic hit list (same size). Sets where
the user hit list is significant but the MF baseline is not are
specifically enriched beyond the MF expectation. Sets where the MF
baseline alone produces strong enrichment are suspect.

CLI:
    python ora.py --hits <tsv> [--gene-col symbol] [--library go-bp | gmt:<path>] [...]
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

import numpy as np
import pandas as pd
from scipy.stats import hypergeom

TOOL_VERSION = "0.1.0"
CACHE_DIR = Path.home() / ".cache" / "enrichment"
REFS_DIR = CACHE_DIR / "refs"

USER_AGENT = (
    f"enrichment/{TOOL_VERSION} (https://github.com/ppavlidis/skillz; "
    f"+contact via repo issues)"
)

SKILLZ_ROOT = Path(__file__).resolve().parent.parent.parent
GENE_SET_FETCH = SKILLZ_ROOT / "gene-set-fetch" / "scripts" / "fetch.py"
GENE_SET_FETCH_VENV = SKILLZ_ROOT / "gene-set-fetch" / ".venv" / "bin" / "python"
GENE_STATISTICS = SKILLZ_ROOT / "gene-statistics" / "scripts" / "multifunctionality.py"
GENE_STATISTICS_VENV = SKILLZ_ROOT / "gene-statistics" / ".venv" / "bin" / "python"

GAF_URL = {
    "human": "https://current.geneontology.org/annotations/goa_human.gaf.gz",
    "mouse": "https://current.geneontology.org/annotations/mgi.gaf.gz",
}
GO_OBO_URL = "http://purl.obolibrary.org/obo/go.obo"

_GAF_DATE_RE = re.compile(rb"^!date-generated:\s*(\S+)", re.MULTILINE)
_DATA_VERSION_RE = re.compile(r"^data-version:\s*(\S+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print("[enrichment:ora] ERROR: " + msg, file=sys.stderr)
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


def _subprocess_skill(skill_python: Path, skill_script: Path, args_list: list[str]) -> str:
    if not skill_script.exists():
        die(f"sibling skill not found: {skill_script}")
    py = str(skill_python) if skill_python.exists() else sys.executable
    try:
        res = subprocess.run(
            [py, str(skill_script)] + args_list,
            check=True, capture_output=True, text=True, timeout=1800,
        )
    except subprocess.CalledProcessError as e:
        die(f"sibling skill failed: {skill_script.name} {args_list}\n  stderr: {e.stderr[:500]}")
    return (res.stdout or "").strip().splitlines()[-1] if res.stdout else ""


def _ensure_refs(species: str) -> dict:
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    gaf_name = "goa_human.gaf.gz" if species == "human" else "mgi.gaf.gz"
    gaf_path = REFS_DIR / gaf_name
    obo_path = REFS_DIR / "go.obo"
    if not gaf_path.exists() or gaf_path.stat().st_size == 0:
        _download(GAF_URL[species], gaf_path)
    if not obo_path.exists() or obo_path.stat().st_size == 0:
        _download(GO_OBO_URL, obo_path)
    gaf_date = ""
    try:
        with gzip.open(gaf_path, "rb") as f:
            m = _GAF_DATE_RE.search(f.read(8192))
        if m:
            gaf_date = m.group(1).decode("utf-8", errors="replace").strip()
    except Exception:
        pass
    obo_version = ""
    try:
        with obo_path.open("rb") as f:
            m = _DATA_VERSION_RE.search(f.read(8192).decode("utf-8", errors="replace"))
        if m:
            obo_version = m.group(1).strip()
    except Exception:
        pass
    return {
        "gaf_path": gaf_path, "gaf_sha256": _sha256_path(gaf_path),
        "gaf_date_generated": gaf_date,
        "obo_path": obo_path, "obo_sha256": _sha256_path(obo_path),
        "obo_data_version": obo_version,
    }


def _iter_gaf_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line or line.startswith("!"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 15:
                continue
            yield cols


def _load_library_go_bp(species: str) -> tuple[dict, dict]:
    refs = _ensure_refs(species)
    direct: dict[str, set] = defaultdict(set)
    for cols in _iter_gaf_rows(refs["gaf_path"]):
        if cols[8] != "P":
            continue
        sym = cols[2].upper()
        if sym:
            direct[sym].add(cols[4])

    import obonet
    import networkx as nx
    graph = obonet.read_obo(str(refs["obo_path"]))

    term_id_to_name = {
        nid: ndata.get("name", "")
        for nid, ndata in graph.nodes(data=True)
        if ndata.get("namespace") == "biological_process"
    }

    direct_terms = set()
    for terms in direct.values():
        direct_terms.update(terms)
    anc_cache: dict[str, set] = {}
    for t in direct_terms:
        if t not in graph:
            anc_cache[t] = set()
            continue
        ancs = nx.descendants(graph, t)
        ancs_ns = {a for a in ancs if graph.nodes.get(a, {}).get("namespace") == "biological_process"}
        if graph.nodes.get(t, {}).get("namespace") == "biological_process":
            ancs_ns.add(t)
        anc_cache[t] = ancs_ns

    term_genes: dict[str, set] = defaultdict(set)
    for sym, terms in direct.items():
        for t in terms:
            for anc in anc_cache.get(t, set()):
                term_genes[anc].add(sym)

    library = {
        tid: {"name": term_id_to_name.get(tid, ""), "members": gs}
        for tid, gs in term_genes.items()
    }
    return library, {
        "library_kind": "go-bp",
        "library_source_files": {
            "gaf_url": GAF_URL[species], "gaf_sha256": refs["gaf_sha256"],
            "gaf_date_generated": refs["gaf_date_generated"],
            "obo_url": GO_OBO_URL, "obo_sha256": refs["obo_sha256"],
            "obo_data_version": refs["obo_data_version"],
        },
    }


def _load_library_gmt(gmt_path: Path) -> tuple[dict, dict]:
    if not gmt_path.exists():
        die(f"GMT file not found: {gmt_path}")
    library: dict[str, dict] = {}
    opener = gzip.open if str(gmt_path).endswith(".gz") else open
    with opener(gmt_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3:
                continue
            sid, name = cols[0], cols[1]
            members = {g.upper() for g in cols[2:] if g}
            if members:
                library[sid] = {"name": name, "members": members}
    return library, {
        "library_kind": "gmt",
        "library_source_files": {
            "gmt_path": str(gmt_path),
            "gmt_sha256": _sha256_path(gmt_path),
        },
    }


def _resolve_background(species: str, background_set: str | None) -> tuple[set, dict]:
    if background_set == "annotated":
        return set(), {"background_kind": "annotated_universe"}
    if not GENE_SET_FETCH.exists():
        die(f"gene-set-fetch sibling not found at {GENE_SET_FETCH}")
    tsv_path_str = _subprocess_skill(GENE_SET_FETCH_VENV, GENE_SET_FETCH, [background_set])
    tsv_path = Path(tsv_path_str)
    if not tsv_path.exists():
        die(f"gene-set-fetch returned non-existent path: {tsv_path_str}")
    df = pd.read_csv(tsv_path, sep="\t", dtype="string", low_memory=False)
    if "symbol" not in df.columns:
        die(f"background TSV {tsv_path} missing 'symbol' column")
    syms = {s.upper() for s in df["symbol"].dropna() if s}
    return syms, {
        "background_kind": "gene_set_fetch",
        "background_set_name": background_set,
        "background_tsv_path": str(tsv_path),
        "background_tsv_sha256": _sha256_path(tsv_path),
        "background_symbol_count": len(syms),
    }


def _resolve_mf(species: str, background_set: str | None) -> tuple[pd.DataFrame, dict]:
    args = ["--species", species]
    if background_set and background_set != "annotated":
        args += ["--background-set", background_set]
    else:
        args += ["--background-set", "annotated"]
    path_str = _subprocess_skill(GENE_STATISTICS_VENV, GENE_STATISTICS, args)
    mf_path = Path(path_str)
    if not mf_path.exists():
        die(f"gene-statistics returned non-existent path: {path_str}")
    df = pd.read_csv(mf_path, sep="\t", dtype={"gene_symbol": "string"})
    return df, {
        "mf_artifact_path": str(mf_path),
        "mf_artifact_sha256": _sha256_path(mf_path),
    }


# ---------------------------------------------------------------------------
# Hit list parsing
# ---------------------------------------------------------------------------


def _load_hit_list(path: Path, gene_col: str) -> set[str]:
    """Accept either a TSV with a `gene_col` column, OR a plain-text file with
    one symbol per line.
    """
    with path.open(encoding="utf-8") as f:
        first = f.readline()
    if "\t" in first or (gene_col != "symbol" and "," in first):
        # Treat as a TSV.
        df = pd.read_csv(path, sep="\t", dtype="string")
        if gene_col not in df.columns:
            die(
                f"hit-list file {path} has no '{gene_col}' column; "
                f"got: {list(df.columns)}"
            )
        return {s.upper() for s in df[gene_col].dropna() if s}
    # Plain-text, one symbol per line. Allow leading hashes / blank lines.
    syms: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            syms.add(line.upper().split()[0])
    return syms


# ---------------------------------------------------------------------------
# ORA per-set computation
# ---------------------------------------------------------------------------


def _ora_pvalue(N: int, K: int, n: int, k: int) -> float:
    """One-tailed hypergeometric p-value: P(X >= k) under Hypergeometric(N, K, n).
    Uses scipy.stats.hypergeom.sf(k-1, N, K, n).
    Edge case: k == 0 → p = 1.0.
    """
    if k <= 0 or K <= 0 or n <= 0:
        return 1.0
    return float(hypergeom.sf(k - 1, N, K, n))


def _bh_qvalues(pvals: np.ndarray) -> np.ndarray:
    n = len(pvals)
    order = np.argsort(pvals)
    ranked = pvals[order]
    q = ranked * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    out = np.zeros(n, dtype=np.float64)
    out[order] = q
    return out


def _cache_paths(hits_stem: str, library_tag: str, species: str,
                 background_tag: str, out: Path | None):
    if out is not None:
        tsv_path = Path(out)
        meta_path = tsv_path.with_suffix(".meta.json")
        return tsv_path, meta_path
    stem = f"ora__{hits_stem}__{library_tag}__{species}__{background_tag}"
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
    parser = argparse.ArgumentParser(description="ORA / hit-list enrichment (hypergeometric).")
    parser.add_argument("--hits", type=Path, required=True,
                        help="hit list: TSV with --gene-col column, OR plain-text one symbol per line")
    parser.add_argument("--gene-col", default="symbol",
                        help="column name in --hits TSV (ignored for plain-text)")
    parser.add_argument("--library", default="go-bp",
                        help="library source: 'go-bp' (default) or 'gmt:<path>'")
    parser.add_argument("--species", choices=["human", "mouse"], default="human")
    parser.add_argument("--background-set", default=None,
                        help="default protein_coding_<species>_strict; 'annotated' to opt out")
    parser.add_argument("--min-set-size", type=int, default=5)
    parser.add_argument("--max-set-size", type=int, default=200)
    parser.add_argument("--mf-correction", dest="mf_correction", action="store_true", default=True)
    parser.add_argument("--no-mf-correction", dest="mf_correction", action="store_false")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if not args.hits.exists():
        die(f"hits file not found: {args.hits}")

    if args.background_set is None:
        args.background_set = f"protein_coding_{args.species}_strict"

    library_tag = args.library.replace(":", "-").replace("/", "_")
    background_tag = f"bg-{args.background_set}"
    hits_stem = args.hits.stem

    tsv_path, meta_path = _cache_paths(hits_stem, library_tag, args.species,
                                        background_tag, args.out)
    if not args.refresh and _is_fresh(tsv_path, meta_path):
        print(tsv_path)
        return 0

    # --- Hit list ---
    hits = _load_hit_list(args.hits, args.gene_col)
    if not hits:
        die(f"hit list at {args.hits} is empty")
    hits_sha = _sha256_path(args.hits)

    # --- Background ---
    bg_syms, bg_prov = _resolve_background(args.species, args.background_set)
    if bg_syms:
        hits_in_bg = hits & bg_syms
        background = bg_syms
    else:
        # "annotated" mode — universe = symbols seen in library
        hits_in_bg = hits  # will be intersected with library universe below
        background = set()  # to be filled from library

    # --- Library ---
    if args.library == "go-bp":
        library, lib_prov = _load_library_go_bp(args.species)
    elif args.library.startswith("gmt:"):
        gmt_path = Path(args.library.split(":", 1)[1])
        library, lib_prov = _load_library_gmt(gmt_path)
    else:
        die(f"unknown library source: {args.library!r}")

    if not background:
        # Build universe from library.
        for info in library.values():
            background.update(info["members"])
        hits_in_bg = hits & background

    if not hits_in_bg:
        die(
            f"zero overlap between hit list ({len(hits)} symbols) and background "
            f"({len(background)} symbols). Check that your gene symbols match the "
            f"background's case/format (we uppercase everything)."
        )

    N = len(background)
    n = len(hits_in_bg)

    # Filter library: restrict members to background, apply size filter.
    filtered: dict[str, dict] = {}
    for sid, info in library.items():
        restricted = info["members"] & background
        if args.min_set_size <= len(restricted) <= args.max_set_size:
            filtered[sid] = {
                "name": info["name"],
                "members": restricted,
                "original_size": len(info["members"]),
            }
    if not filtered:
        die(
            f"after size filtering ({args.min_set_size}-{args.max_set_size}) and "
            f"restriction to background ({N} genes), zero sets remain"
        )

    # --- MF baseline hit list ---
    mf_prov: dict = {}
    mf_baseline_hits: set[str] | None = None
    if args.mf_correction:
        mf_df, mf_prov = _resolve_mf(args.species, args.background_set)
        if "mf_percentile" not in mf_df.columns:
            die(f"MF artifact missing 'mf_percentile' column")
        mf_df["gene_symbol"] = mf_df["gene_symbol"].astype("string").str.upper()
        # Take the top |hits_in_bg| most multifunctional genes in background as the MF baseline hit list.
        # Restrict to background first.
        mf_in_bg = mf_df[mf_df["gene_symbol"].isin(background)].copy()
        mf_in_bg = mf_in_bg.sort_values("mf_percentile", ascending=False).head(n)
        mf_baseline_hits = set(mf_in_bg["gene_symbol"].tolist())

    # --- Per-set ORA ---
    set_ids = list(filtered.keys())
    n_sets = len(set_ids)
    pvals = np.zeros(n_sets, dtype=np.float64)
    set_sizes = np.zeros(n_sets, dtype=np.int64)
    n_hits_in_set = np.zeros(n_sets, dtype=np.int64)
    expected_hits = np.zeros(n_sets, dtype=np.float64)
    fold_enrich = np.zeros(n_sets, dtype=np.float64)
    mf_pvals = np.full(n_sets, np.nan)
    mf_hits_in_set = np.full(n_sets, np.nan)

    for i, sid in enumerate(set_ids):
        members = filtered[sid]["members"]
        K = len(members)
        k = len(hits_in_bg & members)
        set_sizes[i] = K
        n_hits_in_set[i] = k
        expected_hits[i] = K * n / N if N > 0 else 0.0
        fold_enrich[i] = (k / expected_hits[i]) if expected_hits[i] > 0 else float("nan")
        pvals[i] = _ora_pvalue(N, K, n, k)
        if mf_baseline_hits is not None:
            k_mf = len(mf_baseline_hits & members)
            mf_hits_in_set[i] = k_mf
            mf_pvals[i] = _ora_pvalue(N, K, len(mf_baseline_hits), k_mf)

    qvals = _bh_qvalues(pvals)
    if args.mf_correction:
        mf_qvals = _bh_qvalues(np.where(np.isnan(mf_pvals), 1.0, mf_pvals))
    else:
        mf_qvals = np.full(n_sets, np.nan)

    rows = []
    for i, sid in enumerate(set_ids):
        info = filtered[sid]
        rows.append({
            "set_id": sid,
            "set_name": info["name"],
            "set_size": int(info["original_size"]),
            "set_size_after_filter": int(set_sizes[i]),
            "n_hits_in_set": int(n_hits_in_set[i]),
            "expected_hits": float(expected_hits[i]),
            "fold_enrichment": (float(fold_enrich[i]) if not np.isnan(fold_enrich[i]) else None),
            "pvalue": float(pvals[i]),
            "qvalue": float(qvals[i]),
            "mf_baseline_n_hits_in_set": (int(mf_hits_in_set[i]) if not np.isnan(mf_hits_in_set[i]) else None),
            "mf_baseline_pvalue": (float(mf_pvals[i]) if not np.isnan(mf_pvals[i]) else None),
            "mf_baseline_qvalue": (float(mf_qvals[i]) if not np.isnan(mf_qvals[i]) else None),
            "library_source": args.library,
            "species": args.species,
            "background_kind": bg_prov.get("background_kind"),
        })
    df = pd.DataFrame(rows).sort_values("pvalue").reset_index(drop=True)

    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tsv_path.with_suffix(tsv_path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(tsv_path)
    output_sha = _sha256_path(tsv_path)

    meta_payload = {
        "operation": "ora",
        "tool_version": TOOL_VERSION,
        "fetched_at": _iso_now(),
        "hits_input_path": str(args.hits),
        "hits_input_sha256": hits_sha,
        "hits_input_n_symbols": len(hits),
        "hits_in_background": int(n),
        "gene_col": args.gene_col,
        "species": args.species,
        "library": args.library,
        "min_set_size": args.min_set_size,
        "max_set_size": args.max_set_size,
        "mf_correction": args.mf_correction,
        "n_genes_in_background": int(N),
        "n_sets_tested": int(n_sets),
        "output_sha256": output_sha,
        "reference": "ermineJ ORA mode; hypergeometric one-tailed test",
    }
    meta_payload.update(bg_prov)
    meta_payload.update(lib_prov)
    if mf_prov:
        meta_payload.update(mf_prov)

    tmp_meta = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp_meta.write_text(json.dumps(meta_payload, indent=2, sort_keys=True) + "\n")
    tmp_meta.replace(meta_path)

    print(tsv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
