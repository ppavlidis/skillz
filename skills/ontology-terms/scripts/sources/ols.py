"""OLS4 (EBI Ontology Lookup Service) — REST API source.

OLS is the EBI-hosted authoritative service for OBO biomedical ontologies.
It exposes a stable, well-documented REST API at
https://www.ebi.ac.uk/ols4/api/.

Endpoints used:
- parents:    /api/ontologies/{ont}/terms/{double-encoded-IRI}/parents
- children:   /api/ontologies/{ont}/terms/{double-encoded-IRI}/children
- definition: /api/ontologies/{ont}/terms/{double-encoded-IRI}
- search:     /api/search?q={query}&ontology={ont}&type=class&rows={limit}

NOTE on the double encoding: OLS expects the term IRI as a URL path component
that is itself URL-encoded. So `http://purl.obolibrary.org/obo/GO_0006915`
gets URL-encoded once to `http%3A%2F%2Fpurl.obolibrary.org%2Fobo%2FGO_0006915`,
then the resulting `%` characters get encoded again when embedded in the URL
path. requests' params= doesn't do this; we encode manually.

Canonicality: OLS is run by EMBL-EBI and has been the canonical ontology
service in the field for ~15 years. Durability is excellent.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import pandas as pd

from ._common import (
    SourceInfo,
    TermFormatError,
    die,
    http_get,
    require_module,
    sha256_bytes,
    to_compact,
    to_uri,
)


def _safe_compact(uri: str) -> str:
    try:
        return to_compact(uri) if uri else ""
    except TermFormatError:
        return uri  # non-OBO URI; pass through

SOURCE_NAME = "ols"
OLS_BASE = "https://www.ebi.ac.uk/ols4/api"

# Cache ontology metadata per-process so a single fetch of, say, "parents" +
# "children" + "definition" for one ontology only probes OLS once for version.
_ONT_META_CACHE: dict[str, dict] = {}


def _double_encode_iri(uri: str) -> str:
    return urllib.parse.quote(urllib.parse.quote(uri, safe=""), safe="")


def _term_endpoint(ontology: str, term_uri: str, suffix: str = "") -> str:
    encoded = _double_encode_iri(term_uri)
    url = f"{OLS_BASE}/ontologies/{ontology}/terms/{encoded}"
    if suffix:
        url = f"{url}/{suffix}"
    return url


def _get_json(url: str, requests, **params) -> tuple[dict, bytes]:
    try:
        resp = http_get(url, requests, params=params, headers={"Accept": "application/json"}, timeout=30)
    except requests.RequestException as e:
        die(f"OLS request failed: {url}\n  {e}", source=SOURCE_NAME)
    if resp.status_code == 404:
        die(
            f"OLS returned 404 for: {url}\n  the term may not exist in this ontology, "
            f"or the ontology slug may be wrong (try --ontology auto or check the OLS docs)",
            source=SOURCE_NAME,
        )
    if resp.status_code == 429:
        die(
            f"OLS rate-limited the request (429). Back off and retry later. URL: {url}",
            source=SOURCE_NAME,
        )
    if not resp.ok:
        die(
            f"OLS returned HTTP {resp.status_code}: {url}\n  body (first 300 chars): {resp.text[:300]}",
            source=SOURCE_NAME,
        )
    raw = resp.content
    try:
        return resp.json(), raw
    except Exception as e:
        die(f"OLS response is not JSON: {e}\n  url: {url}\n  body: {raw[:200]!r}", source=SOURCE_NAME)


def _ontology_metadata(ontology: str, requests) -> dict:
    """Fetch ontology metadata (version, version IRI, last_modified) once per
    process. Records this on every artifact's meta JSON so a reviewer can
    pin reproducibility to a specific ontology release."""
    if ontology in _ONT_META_CACHE:
        return _ONT_META_CACHE[ontology]
    url = f"{OLS_BASE}/ontologies/{ontology}"
    try:
        resp = http_get(url, requests, headers={"Accept": "application/json"}, timeout=15)
        if not resp.ok:
            _ONT_META_CACHE[ontology] = {}
            return {}
        payload = resp.json()
    except Exception:
        _ONT_META_CACHE[ontology] = {}
        return {}
    cfg = payload.get("config") or {}
    meta = {
        "ontology_version": cfg.get("version", "") or "",
        "ontology_version_iri": cfg.get("versionIri", "") or "",
        "ontology_title": cfg.get("title", "") or "",
        "ontology_last_modified": payload.get("updated") or payload.get("loaded") or "",
    }
    _ONT_META_CACHE[ontology] = meta
    return meta


def _synonyms_from_term(term: dict) -> str:
    """OLS exposes synonyms in several fields depending on the ontology.
    Collect everything we can find and emit a semicolon-joined string."""
    seen: list[str] = []
    seen_lc: set[str] = set()
    for key in ("synonyms", "obo_synonym"):
        for entry in term.get(key) or []:
            if isinstance(entry, str):
                v = entry
            elif isinstance(entry, dict):
                v = entry.get("name") or entry.get("synonym") or ""
            else:
                continue
            v = (v or "").strip()
            if v and v.lower() not in seen_lc:
                seen.append(v)
                seen_lc.add(v.lower())
    return "; ".join(seen)


def _embedded_terms(payload: dict) -> list[dict]:
    """OLS pages results under _embedded.terms. Walk all pages."""
    return (payload.get("_embedded") or {}).get("terms") or []


def _term_to_row(term: dict, ontology: str, relation: str) -> dict:
    iri = term.get("iri") or term.get("uri") or ""
    return {
        "term_id": _safe_compact(iri),
        "term_uri": iri,
        "term_label": term.get("label", ""),
        "ontology": ontology,
        "relation": relation,
        "source": SOURCE_NAME,
    }


def _paged_fetch(url: str, requests) -> tuple[list[dict], bytes]:
    """Walk OLS HAL pagination, accumulating all _embedded.terms entries."""
    all_terms: list[dict] = []
    raw_concat = bytearray()
    next_url: str | None = url
    page_size = 100
    while next_url:
        payload, raw = _get_json(next_url, requests, size=page_size)
        raw_concat.extend(raw)
        all_terms.extend(_embedded_terms(payload))
        next_link = (payload.get("_links") or {}).get("next") or {}
        next_url = next_link.get("href")
        # Avoid double-passing size param via params= when the next URL
        # already contains it.
        if next_url:
            page_size = None  # type: ignore[assignment]
    return all_terms, bytes(raw_concat)


def parents(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    uri = to_uri(term)
    url = _term_endpoint(ontology, uri, suffix="parents")
    terms, raw = _paged_fetch(url, requests)
    df = pd.DataFrame([_term_to_row(t, ontology, "is_a") for t in terms],
                      columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source"])
    return df, SourceInfo(
        url=url, version="OLS4 (current); fetched live", sha256=sha256_bytes(raw),
        extras=_ontology_metadata(ontology, requests),
    )


def children(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    uri = to_uri(term)
    url = _term_endpoint(ontology, uri, suffix="children")
    terms, raw = _paged_fetch(url, requests)
    df = pd.DataFrame([_term_to_row(t, ontology, "is_a") for t in terms],
                      columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source"])
    return df, SourceInfo(
        url=url, version="OLS4 (current); fetched live", sha256=sha256_bytes(raw),
        extras=_ontology_metadata(ontology, requests),
    )


def definition(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    uri = to_uri(term)
    url = _term_endpoint(ontology, uri)
    payload, raw = _get_json(url, requests)

    # OLS sometimes returns a list of "matches" under _embedded.terms; pick the
    # one whose iri matches the requested URI.
    candidates = _embedded_terms(payload)
    chosen: dict[str, Any] | None
    if candidates:
        chosen = next((t for t in candidates if t.get("iri") == uri), candidates[0])
    else:
        # Single-term response shape (older OLS, or direct lookup).
        chosen = payload if "iri" in payload else None

    if chosen is None:
        die(f"OLS returned no usable term record for {uri} in {ontology!r}", source=SOURCE_NAME)

    defn_field = chosen.get("description") or chosen.get("definition") or []
    defn = "; ".join(defn_field) if isinstance(defn_field, list) else str(defn_field or "")
    synonyms = _synonyms_from_term(chosen)

    row = _term_to_row(chosen, ontology, "definition")
    row["definition"] = defn
    row["synonyms"] = synonyms
    df = pd.DataFrame(
        [row],
        columns=["term_id", "term_uri", "term_label", "ontology", "relation",
                 "source", "definition", "synonyms"],
    )
    return df, SourceInfo(
        url=url, version="OLS4 (current); fetched live", sha256=sha256_bytes(raw),
        extras=_ontology_metadata(ontology, requests),
    )


def search(query: str, ontology: str | None, limit: int) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    url = f"{OLS_BASE}/search"
    params = {"q": query, "type": "class", "rows": max(1, min(int(limit), 500))}
    if ontology and ontology != "auto":
        params["ontology"] = ontology
    payload, raw = _get_json(url, requests, **params)
    docs = (payload.get("response") or {}).get("docs") or []

    rows = []
    for doc in docs:
        iri = doc.get("iri") or ""
        rows.append({
            "term_id": _safe_compact(iri) if iri.startswith("http") else iri,
            "term_uri": iri,
            "term_label": doc.get("label", ""),
            "ontology": (doc.get("ontology_name") or ontology or "").lower(),
            "relation": "search",
            "source": SOURCE_NAME,
            "score": float(doc.get("score", 0.0)),
        })
    df = pd.DataFrame(
        rows,
        columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source", "score"],
    )
    extras = _ontology_metadata(ontology, requests) if ontology and ontology != "auto" else {}
    return df, SourceInfo(
        url=url, version="OLS4 (current); fetched live", sha256=sha256_bytes(raw),
        extras=extras,
    )
