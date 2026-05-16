#!/usr/bin/env python3
"""Precision-Recall AUC gene-set enrichment (Ballouz et al. 2017).

For each gene set in the library, computes the PR-AUC of "is gene in set"
walking the user's ranked score list, plus a permutation p-value and an
MF-corrected p-value.

The PR-AUC is the area under precision-recall, where at rank k:
    precision = (members-of-set seen so far) / k
    recall    = (members-of-set seen so far) / |set|

For a perfect ranking (all set members at the top), PR-AUC ≈ 1.
For a random ranking against a small set, PR-AUC ≈ |set| / N.

MF correction: a sibling enrichment is computed against gene
multifunctionality percentile as the "score". If a set has high PR-AUC
both against the user score AND against MF, the apparent enrichment is
likely driven by which-genes-are-multifunctional rather than the user's
specific biology.
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

ASPECT_TO_GAF = {"BP": "P", "MF": "F", "CC": "C"}
ASPECT_TO_NAMESPACE = {
    "BP": "biological_process",
    "MF": "molecular_function",
    "CC": "cellular_component",
}

_GAF_DATE_RE = re.compile(rb"^!date-generated:\s*(\S+)", re.MULTILINE)
_DATA_VERSION_RE = re.compile(r"^data-version:\s*(\S+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print("[enrichment:pr_enrichment] ERROR: " + msg, file=sys.stderr)
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
    """Run a sibling skill via subprocess, return stdout's last line (a path)."""
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


# ---------------------------------------------------------------------------
# Reference data fetching (shared with gene-statistics)
# ---------------------------------------------------------------------------


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
        "gaf_path": gaf_path, "gaf_sha256": gaf_sha, "gaf_date_generated": gaf_date,
        "obo_path": obo_path, "obo_sha256": obo_sha, "obo_data_version": obo_version,
    }


# ---------------------------------------------------------------------------
# Library loaders — each returns dict[set_id, {name, members: set[str]}]
# Members are gene SYMBOLS (uppercase).
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


def _load_library_go_bp(species: str) -> tuple[dict, dict]:
    """Returns (library_dict, provenance_dict).

    Library values: {name, members: set[uppercase symbol]}.
    Uses GAF + go.obo with true-path propagation, BP only, all evidence codes.
    """
    refs = _ensure_refs(species)
    namespace = "biological_process"

    # Direct annotations (symbol -> direct BP term IDs).
    direct: dict[str, set] = defaultdict(set)
    term_id_to_name: dict[str, str] = {}
    for cols in _iter_gaf_rows(refs["gaf_path"]):
        if cols[8] != "P":  # BP only
            continue
        sym = cols[2].upper()
        if sym:
            direct[sym].add(cols[4])

    # Propagate via go.obo.
    try:
        import obonet
    except ImportError as e:
        die(f"obonet not installed: {e}")
    import networkx as nx
    graph = obonet.read_obo(str(refs["obo_path"]))
    for nid, ndata in graph.nodes(data=True):
        if ndata.get("namespace") == namespace:
            term_id_to_name[nid] = ndata.get("name", "")

    # term_genes (after propagation, restricted to BP).
    term_genes: dict[str, set] = defaultdict(set)
    anc_cache: dict[str, set] = {}
    direct_terms = set()
    for terms in direct.values():
        direct_terms.update(terms)
    for t in direct_terms:
        if t not in graph:
            anc_cache[t] = set()
            continue
        ancs = nx.descendants(graph, t)
        ancs_ns = {a for a in ancs if graph.nodes.get(a, {}).get("namespace") == namespace}
        if graph.nodes.get(t, {}).get("namespace") == namespace:
            ancs_ns.add(t)
        anc_cache[t] = ancs_ns

    for sym, terms in direct.items():
        propagated = set()
        for t in terms:
            propagated.update(anc_cache.get(t, set()))
        for t in propagated:
            term_genes[t].add(sym)

    library = {
        tid: {"name": term_id_to_name.get(tid, ""), "members": gs}
        for tid, gs in term_genes.items()
    }

    provenance = {
        "library_kind": "go-bp",
        "library_source_files": {
            "gaf_url": GAF_URL[species],
            "gaf_sha256": refs["gaf_sha256"],
            "gaf_date_generated": refs["gaf_date_generated"],
            "obo_url": GO_OBO_URL,
            "obo_sha256": refs["obo_sha256"],
            "obo_data_version": refs["obo_data_version"],
        },
    }
    return library, provenance


def _load_library_gmt(gmt_path: Path) -> tuple[dict, dict]:
    """Load a GMT file (Broad/MSigDB format).

    Each line: set_name <TAB> description <TAB> gene1 <TAB> gene2 ...
    """
    if not gmt_path.exists():
        die(f"GMT file not found: {gmt_path}")
    library: dict[str, dict] = {}
    opener = gzip.open if str(gmt_path).endswith(".gz") else open
    with opener(gmt_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3:
                continue
            sid = cols[0]
            name = cols[1]
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


# ---------------------------------------------------------------------------
# Background resolution (same pattern as gene-statistics)
# ---------------------------------------------------------------------------


def _resolve_background(species: str, background_set: str | None) -> tuple[set, dict]:
    """Resolve background to (uppercase symbol set, provenance).

    background_set: "annotated" -> no restriction (returns universe = None proxy);
                    other -> subprocess to gene-set-fetch.
    """
    if background_set == "annotated":
        return set(), {"background_kind": "annotated_universe"}

    if not GENE_SET_FETCH.exists():
        die(
            f"gene-set-fetch sibling not found at {GENE_SET_FETCH}; install it "
            f"under {SKILLZ_ROOT}/gene-set-fetch/ or pass --background-set annotated"
        )
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


# ---------------------------------------------------------------------------
# MF artifact (auto-fetch if missing)
# ---------------------------------------------------------------------------


def _resolve_mf(species: str, background_set: str | None) -> tuple[pd.DataFrame, dict]:
    """Fetch or compute per-gene MF percentiles via the gene-statistics skill."""
    args = ["--species", species]
    if background_set and background_set != "annotated":
        args += ["--background-set", background_set]
    else:
        args += ["--background-set", "annotated"]
    if not GENE_STATISTICS.exists():
        die(f"gene-statistics sibling not found at {GENE_STATISTICS}")
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
# PR-AUC computation
# ---------------------------------------------------------------------------


def _pr_auc_for_set(set_membership: np.ndarray) -> float:
    """Compute PR-AUC given a binary membership vector ranked by score
    (descending; index 0 is the top-ranked gene).

    Walks the ranking, computing precision and recall at each step, then
    integrates by trapezoid rule over recall.
    """
    n_set = int(set_membership.sum())
    if n_set == 0:
        return 0.0
    n = len(set_membership)
    # Cumulative TP at each rank.
    cumtp = np.cumsum(set_membership)
    k = np.arange(1, n + 1)
    precision = cumtp / k
    recall = cumtp / n_set
    # Integrate precision over recall (recall is monotonic non-decreasing).
    # AUC = sum over steps of average-precision * delta-recall.
    # When membership[i] == 0, recall doesn't change; contribution is 0.
    # Equivalent to: AUC = sum of precision values at positions where
    # membership == 1, divided by n_set. This is the standard
    # "average precision" definition.
    return float(precision[set_membership == 1].sum() / n_set)


def _pr_auc_permutation_null(
    n_genes: int, n_set: int, n_perm: int, rng: np.random.Generator
) -> np.ndarray:
    """Generate `n_perm` null PR-AUC values for a set of size n_set
    against a background of n_genes. The null assumes the set members are
    randomly placed in the ranking."""
    nulls = np.zeros(n_perm, dtype=np.float64)
    # Pre-allocate membership vector reused across permutations.
    base = np.zeros(n_genes, dtype=np.int8)
    indices = np.arange(n_genes)
    for i in range(n_perm):
        rng.shuffle(indices)
        m = base.copy()
        m[indices[:n_set]] = 1
        nulls[i] = _pr_auc_for_set(m)
    return nulls


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def _bh_qvalues(pvals: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values."""
    n = len(pvals)
    order = np.argsort(pvals)
    ranked = pvals[order]
    # q_i = p_i * n / rank, capped at 1, monotonically nondecreasing from top.
    q = ranked * n / (np.arange(n) + 1)
    # Enforce monotonicity from the top down.
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    out = np.zeros(n, dtype=np.float64)
    out[order] = q
    return out


def _cache_paths(input_stem: str, library_tag: str, species: str,
                 background_tag: str, perm: int, out: Path | None):
    if out is not None:
        tsv_path = Path(out)
        meta_path = tsv_path.with_suffix(".meta.json")
        return tsv_path, meta_path
    stem = f"pr_enrichment__{input_stem}__{library_tag}__{species}__{background_tag}__perm{perm}"
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
    parser = argparse.ArgumentParser(description="PR-AUC gene-set enrichment (Ballouz et al. 2017).")
    parser.add_argument("--scores", type=Path, required=True, help="TSV of gene scores")
    parser.add_argument("--gene-col", default="symbol")
    parser.add_argument("--score-col", default="score")
    parser.add_argument("--score-direction", choices=["higher", "lower"], default="higher",
                        help="which end of the score axis is 'interesting'")
    parser.add_argument("--library", default="go-bp",
                        help="library source: 'go-bp' (default) or 'gmt:<path>'")
    parser.add_argument("--species", choices=["human", "mouse"], default="human")
    parser.add_argument("--background-set", default=None,
                        help="restrict background (default protein_coding_<species>_strict; "
                             "'annotated' to use full universe)")
    parser.add_argument("--min-set-size", type=int, default=5)
    parser.add_argument("--max-set-size", type=int, default=200)
    parser.add_argument("--permutations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mf-correction", dest="mf_correction", action="store_true", default=True)
    parser.add_argument("--no-mf-correction", dest="mf_correction", action="store_false")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if not args.scores.exists():
        die(f"scores file not found: {args.scores}")

    # Default --background-set: protein-coding strict, matches gene-statistics.
    if args.background_set is None:
        args.background_set = f"protein_coding_{args.species}_strict"

    library_tag = args.library.replace(":", "-").replace("/", "_")
    background_tag = f"bg-{args.background_set}"
    input_stem = args.scores.stem

    tsv_path, meta_path = _cache_paths(
        input_stem, library_tag, args.species, background_tag,
        args.permutations, args.out,
    )
    if not args.refresh and _is_fresh(tsv_path, meta_path):
        print(tsv_path)
        return 0

    # --- Load scores ---
    scores_df = pd.read_csv(args.scores, sep="\t", dtype={args.gene_col: "string"})
    if args.gene_col not in scores_df.columns or args.score_col not in scores_df.columns:
        die(
            f"scores file missing required columns: gene-col={args.gene_col!r} "
            f"and/or score-col={args.score_col!r}. got: {list(scores_df.columns)}"
        )
    scores_df[args.gene_col] = scores_df[args.gene_col].astype("string").str.upper()
    scores_df = scores_df.dropna(subset=[args.gene_col, args.score_col]).copy()
    if scores_df.empty:
        die("scores file is empty after dropping NaN gene/score rows")
    scores_df = scores_df.drop_duplicates(subset=[args.gene_col])
    scores_sha = _sha256_path(args.scores)

    # --- Resolve background ---
    bg_syms, bg_prov = _resolve_background(args.species, args.background_set)
    if bg_syms:
        scores_df = scores_df[scores_df[args.gene_col].isin(bg_syms)].copy()
    if scores_df.empty:
        die(
            "after restricting scores to background, zero genes remain. Either "
            "your gene symbols don't match the background, or the background set is empty."
        )

    # Sort genes by score, descending = higher-is-better.
    ascending = args.score_direction == "lower"
    scores_df = scores_df.sort_values(args.score_col, ascending=ascending).reset_index(drop=True)
    ranked_symbols = scores_df[args.gene_col].tolist()
    rank_index = {s: i for i, s in enumerate(ranked_symbols)}
    n_genes = len(ranked_symbols)

    # --- Load library ---
    if args.library == "go-bp":
        library, lib_prov = _load_library_go_bp(args.species)
    elif args.library.startswith("gmt:"):
        gmt_path = Path(args.library.split(":", 1)[1])
        library, lib_prov = _load_library_gmt(gmt_path)
    else:
        die(f"unknown library source: {args.library!r}")

    # Restrict each set to the scored gene list AND apply size filter on the restricted size.
    filtered_library: dict[str, dict] = {}
    for sid, info in library.items():
        restricted = info["members"] & set(ranked_symbols)
        if args.min_set_size <= len(restricted) <= args.max_set_size:
            filtered_library[sid] = {
                "name": info["name"],
                "restricted_members": restricted,
                "original_size": len(info["members"]),
            }
    if not filtered_library:
        die(
            f"after size filtering ({args.min_set_size}-{args.max_set_size}) and "
            f"restriction to the ranked input ({n_genes} genes), zero sets remain"
        )

    # --- Compute observed PR-AUC per set ---
    rng = np.random.default_rng(args.seed)
    set_ids = list(filtered_library.keys())
    n_sets = len(set_ids)

    observed = np.zeros(n_sets, dtype=np.float64)
    set_sizes = np.zeros(n_sets, dtype=np.int64)
    n_in_input = np.zeros(n_sets, dtype=np.int64)
    for i, sid in enumerate(set_ids):
        members = filtered_library[sid]["restricted_members"]
        membership = np.zeros(n_genes, dtype=np.int8)
        for sym in members:
            ix = rank_index.get(sym)
            if ix is not None:
                membership[ix] = 1
        set_sizes[i] = len(members)
        n_in_input[i] = int(membership.sum())
        observed[i] = _pr_auc_for_set(membership)

    # --- Permutation null per unique set size ---
    # PR-AUC null depends only on set size and n_genes; cache by size.
    unique_sizes = sorted(set(int(s) for s in set_sizes))
    null_cache: dict[int, np.ndarray] = {}
    for sz in unique_sizes:
        null_cache[sz] = _pr_auc_permutation_null(n_genes, sz, args.permutations, rng)

    # Empirical p-values.
    pvals = np.zeros(n_sets, dtype=np.float64)
    for i, sz in enumerate(set_sizes):
        null = null_cache[int(sz)]
        # one-sided: P(null >= observed)
        n_ge = int(np.sum(null >= observed[i]))
        pvals[i] = (n_ge + 1) / (args.permutations + 1)
    qvals = _bh_qvalues(pvals)

    # --- MF correction ---
    mf_prov: dict = {}
    mf_pr_auc = np.full(n_sets, np.nan)
    mf_pvals = np.full(n_sets, np.nan)
    mf_qvals = np.full(n_sets, np.nan)
    if args.mf_correction:
        mf_df, mf_prov = _resolve_mf(args.species, args.background_set)
        if "mf_percentile" not in mf_df.columns or "gene_symbol" not in mf_df.columns:
            die(f"MF artifact missing expected columns; got {list(mf_df.columns)}")
        mf_df["gene_symbol"] = mf_df["gene_symbol"].astype("string").str.upper()
        # Build the MF-ranked symbol order, restricted to the same scored
        # gene universe (so the comparison is apples-to-apples).
        mf_in_scored = mf_df[mf_df["gene_symbol"].isin(ranked_symbols)].copy()
        # Higher MF percentile = "more interesting" by the MF baseline.
        mf_in_scored = mf_in_scored.sort_values("mf_percentile", ascending=False).reset_index(drop=True)
        mf_ranked = mf_in_scored["gene_symbol"].tolist()
        # Any scored gene without an MF score appended at the bottom (low MF assumption).
        missing = [s for s in ranked_symbols if s not in set(mf_ranked)]
        mf_ranked = mf_ranked + missing
        mf_rank_index = {s: i for i, s in enumerate(mf_ranked)}

        for i, sid in enumerate(set_ids):
            members = filtered_library[sid]["restricted_members"]
            membership = np.zeros(n_genes, dtype=np.int8)
            for sym in members:
                ix = mf_rank_index.get(sym)
                if ix is not None:
                    membership[ix] = 1
            mf_pr_auc[i] = _pr_auc_for_set(membership)
            # corrected p-value: observed PR-AUC against the MF-only null
            # produced by the same permutation procedure but with set membership
            # in the MF-ranking. Equivalent (under random permutation) to
            # comparing observed_pr_auc to the MF baseline distribution
            # of PR-AUC values across permuted sets.
            null = null_cache[int(set_sizes[i])]
            # The MF baseline expected PR-AUC for this set size is mf_pr_auc[i];
            # corrected p-value: P(observed - mf_pr_auc >= null - mean(null)).
            # Equivalent to comparing observed against null shifted by
            # (mf_pr_auc - mean(null)), i.e. observed_corrected = observed - mf_pr_auc + mean(null).
            shift = mf_pr_auc[i] - float(null.mean())
            observed_corrected = observed[i] - shift
            n_ge = int(np.sum(null >= observed_corrected))
            mf_pvals[i] = (n_ge + 1) / (args.permutations + 1)
        mf_qvals = _bh_qvalues(mf_pvals)

    # --- Assemble output ---
    rows = []
    for i, sid in enumerate(set_ids):
        info = filtered_library[sid]
        rows.append({
            "set_id": sid,
            "set_name": info["name"],
            "set_size": int(info["original_size"]),
            "set_size_after_filter": int(set_sizes[i]),
            "n_genes_in_input": int(n_in_input[i]),
            "pr_auc": float(observed[i]),
            "pvalue": float(pvals[i]),
            "qvalue": float(qvals[i]),
            "mf_pr_auc": (float(mf_pr_auc[i]) if not np.isnan(mf_pr_auc[i]) else None),
            "mf_corrected_pvalue": (float(mf_pvals[i]) if not np.isnan(mf_pvals[i]) else None),
            "mf_corrected_qvalue": (float(mf_qvals[i]) if not np.isnan(mf_qvals[i]) else None),
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
        "operation": "pr_enrichment",
        "tool_version": TOOL_VERSION,
        "fetched_at": _iso_now(),
        "scores_input_path": str(args.scores),
        "scores_input_sha256": scores_sha,
        "scores_input_n_genes": int(n_genes),
        "gene_col": args.gene_col,
        "score_col": args.score_col,
        "score_direction": args.score_direction,
        "species": args.species,
        "library": args.library,
        "min_set_size": args.min_set_size,
        "max_set_size": args.max_set_size,
        "permutations": args.permutations,
        "seed": args.seed,
        "mf_correction": args.mf_correction,
        "n_sets_tested": int(n_sets),
        "output_sha256": output_sha,
        "reference": "Ballouz S, Pavlidis P, Gillis J (2017) NAR 45(4):e20 doi:10.1093/nar/gkw957",
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
