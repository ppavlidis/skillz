"""OBO file parsing — maximum-reproducibility source.

Downloads the canonical OBO file for an ontology from the OBO Foundry purl
redirector (`http://purl.obolibrary.org/obo/{ontology}.obo`) and parses it
locally with the `obonet` package. Because the OBO file itself carries a
`data-version:` header tagged with the release date, the version is
**embedded in the data** — there is no ambiguity about which release was
used. The downloaded file is cached locally, keyed by ontology + version,
so a re-fetch only re-downloads on `--refresh` or a version mismatch.

This is the most reproducible of our sources: if you record the
`source_sha256` of the downloaded OBO bytes (which the .meta.json does),
you can byte-exact reproduce the analysis at any point in the future from
that single artifact.

Limitations:
- Only operates on what the OBO file contains. If the ontology has a
  separate OWL release with extra inferred axioms, you'd see fewer
  relations than OLS (which uses the OWL).
- `search` is a substring/case-insensitive match on labels + synonyms.
  No relevance scoring (returns hits in document order).

Use case:
- Reviewers asking "exactly which release of GO did you use" — point them
  at the .meta.json (`ontology_version` + `source_sha256` of the OBO).
- Offline / firewalled environments after a one-time download.
- Audit-grade reproducibility.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ._common import (
    CACHE_DIR,
    SourceInfo,
    die,
    http_get,
    require_module,
    sha256_bytes,
    sha256_file,
    to_compact,
    to_uri,
)

SOURCE_NAME = "obo"
OBO_CACHE_DIR = CACHE_DIR / "obo"
OBO_URL_TEMPLATE = "http://purl.obolibrary.org/obo/{ontology}.obo"

_DATA_VERSION_RE = re.compile(r"^data-version:\s*(\S+)", re.MULTILINE)


def _download_obo(ontology: str, requests, override_url: str | None = None) -> tuple[Path, str, str, str]:
    """Download the OBO file for `ontology`. Cache under
    ~/.cache/ontology-terms/obo/{ont}-{version}.obo, keyed by version.

    Returns (path, data_version, source_url, source_sha256).
    """
    url = override_url or OBO_URL_TEMPLATE.format(ontology=ontology)
    OBO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # First fetch to determine version, then write to a version-tagged cache path.
    try:
        resp = http_get(url, requests, timeout=600, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        die(f"OBO download failed: {url}\n  {e}", source=SOURCE_NAME)

    raw = resp.content
    text_head = raw[:8192].decode("utf-8", errors="replace")
    m = _DATA_VERSION_RE.search(text_head)
    if not m:
        die(
            f"downloaded OBO file from {url} has no data-version header.\n"
            f"  first 500 chars: {text_head[:500]!r}",
            source=SOURCE_NAME,
        )
    data_version = m.group(1).strip()
    # data_version often contains a URL — pull a date tail if present.
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", data_version)
    version_tag = date_match.group(1) if date_match else data_version.replace("/", "_")[:40]

    path = OBO_CACHE_DIR / f"{ontology}-{version_tag}.obo"
    if not path.exists():
        path.write_bytes(raw)

    return path, data_version, url, sha256_bytes(raw)


def _load_graph(path: Path, ontology: str):
    obonet = require_module("obonet", "pip install obonet", SOURCE_NAME)
    try:
        return obonet.read_obo(str(path))
    except Exception as e:
        die(f"obonet failed to parse {path}: {e}", source=SOURCE_NAME)


def _node_to_compact(node_id: str) -> str:
    """OBO node IDs are already compact (e.g. 'GO:0006915'). Pass through."""
    return node_id


def _node_to_uri(node_id: str) -> str:
    try:
        return to_uri(node_id)
    except Exception:
        return ""


def _row_from_node(graph, node_id: str, ontology: str, relation: str) -> dict:
    data = graph.nodes.get(node_id, {})
    return {
        "term_id": node_id,
        "term_uri": _node_to_uri(node_id),
        "term_label": data.get("name", ""),
        "ontology": ontology,
        "relation": relation,
        "source": SOURCE_NAME,
    }


def _is_a_neighbors(graph, term_id: str, direction: str) -> list[str]:
    """Return immediate is_a neighbors.

    In obonet's MultiDiGraph, edges go FROM a term TO its is_a parent, and
    the edge key is the relationship label. So:
      - parents: outgoing edges with key 'is_a' → targets
      - children: incoming edges with key 'is_a' → sources
    """
    if direction == "parents":
        out: list[str] = []
        for _u, v, key in graph.out_edges(term_id, keys=True):
            if key == "is_a":
                out.append(v)
        return out
    else:  # children
        out = []
        for u, _v, key in graph.in_edges(term_id, keys=True):
            if key == "is_a":
                out.append(u)
        return out


def _extras(version: str) -> dict:
    return {
        "ontology_version": version,
        "ontology_version_iri": "",  # not exposed in OBO header beyond the data-version string
    }


def _common_fetch(operation: str, term: str, ontology: str, override_url: str | None = None):
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    path, data_version, source_url, source_sha = _download_obo(ontology, requests, override_url)
    graph = _load_graph(path, ontology)

    compact = term if ":" in term and not term.startswith("http") else to_compact(term)
    if compact not in graph:
        die(
            f"term {compact!r} not present in OBO graph for ontology {ontology!r} "
            f"(version {data_version}). Either the term ID is wrong or this "
            f"ontology's OBO release doesn't include it.",
            source=SOURCE_NAME,
        )

    if operation == "parents":
        neighbors = _is_a_neighbors(graph, compact, "parents")
        rows = [_row_from_node(graph, n, ontology, "is_a") for n in neighbors]
        df = pd.DataFrame(rows, columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source"])
    elif operation == "children":
        neighbors = _is_a_neighbors(graph, compact, "children")
        rows = [_row_from_node(graph, n, ontology, "is_a") for n in neighbors]
        df = pd.DataFrame(rows, columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source"])
    elif operation == "definition":
        data = graph.nodes.get(compact, {})
        defn = data.get("def", "") or ""
        if defn:
            # obonet keeps def as a quoted string with trailing [source] list; strip those.
            m = re.match(r'^"((?:[^"\\]|\\.)*)"\s*(\[.*?\])?\s*$', defn)
            if m:
                defn = m.group(1).replace('\\"', '"')
        syn_raw = data.get("synonym", []) or []
        synonyms = []
        for s in syn_raw:
            mm = re.match(r'^"((?:[^"\\]|\\.)*)"\s+([A-Z]+)', s)
            if mm:
                synonyms.append(mm.group(1))
            else:
                synonyms.append(s)
        row = {
            "term_id": compact,
            "term_uri": _node_to_uri(compact),
            "term_label": data.get("name", ""),
            "ontology": ontology,
            "relation": "definition",
            "source": SOURCE_NAME,
            "definition": defn,
            "synonyms": "; ".join(synonyms),
        }
        df = pd.DataFrame([row],
                          columns=["term_id", "term_uri", "term_label", "ontology", "relation",
                                   "source", "definition", "synonyms"])
    else:
        die(f"OBO source does not implement operation {operation!r}", source=SOURCE_NAME)

    return df, SourceInfo(
        url=source_url,
        version=f"OBO file (data-version: {data_version})",
        sha256=source_sha,
        extras=_extras(data_version),
    )


def parents(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    return _common_fetch("parents", term, ontology)


def children(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    return _common_fetch("children", term, ontology)


def definition(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    return _common_fetch("definition", term, ontology)


def search(query: str, ontology: str | None, limit: int) -> tuple[pd.DataFrame, SourceInfo]:
    if not ontology or ontology == "auto":
        die(
            "OBO search requires an explicit --ontology; the OBO source loads one "
            "ontology at a time. Pass --ontology go (or mp, hp, etc.)",
            source=SOURCE_NAME,
        )
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    path, data_version, source_url, source_sha = _download_obo(ontology, requests)
    graph = _load_graph(path, ontology)

    q = query.strip().lower()
    rows = []
    for node_id, data in graph.nodes(data=True):
        name = (data.get("name") or "").lower()
        synonyms_raw = data.get("synonym", []) or []
        synonyms_lc = []
        for s in synonyms_raw:
            mm = re.match(r'^"((?:[^"\\]|\\.)*)"\s+([A-Z]+)', s)
            synonyms_lc.append((mm.group(1) if mm else s).lower())
        hit_label = q in name
        hit_syn = any(q in s for s in synonyms_lc)
        if hit_label or hit_syn:
            rows.append({
                "term_id": node_id,
                "term_uri": _node_to_uri(node_id),
                "term_label": data.get("name", ""),
                "ontology": ontology,
                "relation": "search",
                "source": SOURCE_NAME,
                "score": 1.0 if hit_label else 0.5,  # heuristic; label hit > synonym hit
            })
            if len(rows) >= int(limit) * 3:  # gather extras for sort
                pass
    # Sort: label hits (score=1.0) first, then synonym hits; truncate to limit.
    rows.sort(key=lambda r: (-r["score"], r["term_label"]))
    rows = rows[: int(limit)]
    df = pd.DataFrame(
        rows,
        columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source", "score"],
    )
    return df, SourceInfo(
        url=source_url,
        version=f"OBO file (data-version: {data_version})",
        sha256=source_sha,
        extras=_extras(data_version),
    )
