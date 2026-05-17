"""Gemma annotations API — ontology term operations from the Pavlab Gemma server.

Endpoints used (all at https://gemma.msl.ubc.ca/rest/v2/):
- parents:  GET /annotations/parents?uri={uri}   — TRANSITIVE (see semantic note)
- children: GET /annotations/children?uri={uri}  — TRANSITIVE (see semantic note)
- search:   GET /annotations/search?query={query}

Definition: Gemma does NOT expose a term-definition endpoint in v0.1 of this
skill. Calling `definition` via this source fails loud with a pointer to OLS.

**Semantic note on parents/children (IMPORTANT):**
Gemma returns *propagated* relations — i.e. all transitive ancestors for
parents, all transitive descendants for children — rather than only the
immediate relations OLS returns. This reflects how Gemma uses these
hierarchies internally (to include datasets annotated with any descendant
term when querying a parent). Users who specifically need *immediate*
parents/children should prefer `--source ols`. The .meta.json records
`gemma_propagated: true` so downstream consumers know.

**Coverage:** Gemma only loads ontologies it uses for dataset curation —
typically MONDO, MP, CL, UBERON, EFO, parts of GO, and a few others.
Terms outside Gemma's loaded ontologies return a clean 404. Use OLS for
broader coverage.

**Search:** Gemma's annotation search is reportedly strong (full-text +
URI), and is one of the two situations where Gemma is preferable to OLS
(the other being lab-internal alignment with Gemma's curated view).
"""

from __future__ import annotations

import re
import urllib.parse

import pandas as pd

from ._common import (
    _ALL_PREFIXES,
    _NON_OBO_URIS,
    SourceInfo,
    TermFormatError,
    die,
    http_get,
    require_module,
    sha256_bytes,
    to_compact,
    to_uri,
)

SOURCE_NAME = "gemma"
GEMMA_BASE = "https://gemma.msl.ubc.ca/rest/v2"


def _uri_to_ontology_slug(uri: str) -> str:
    """Map a URI back to an ontology slug using the shared registry."""
    try:
        compact = to_compact(uri)
        prefix = compact.split(":")[0].upper()
        return _ALL_PREFIXES.get(prefix, prefix.lower())
    except TermFormatError:
        # Try to extract prefix from the URI path tail as a last resort.
        m = re.search(r"/([A-Za-z]+)[_:](\d+)$", uri or "")
        if m:
            prefix = m.group(1).upper()
            return _ALL_PREFIXES.get(prefix, prefix.lower())
        return ""


def _uri_to_compact_safe(uri: str) -> str:
    """URI -> compact ID, never raising. Uses the shared registry (handles EFO etc.)."""
    try:
        return to_compact(uri)
    except TermFormatError:
        m = re.search(r"/([A-Za-z]+)[_:](\d+)$", uri or "")
        if m:
            return f"{m.group(1).upper()}:{m.group(2)}"
        return uri or ""


def _get_json(url: str, requests) -> tuple[dict, bytes]:
    try:
        resp = http_get(url, requests, headers={"Accept": "application/json"}, timeout=30)
    except requests.RequestException as e:
        die(f"Gemma request failed: {url}\n  {e}", source=SOURCE_NAME)
    raw = resp.content
    if resp.status_code == 404:
        # Gemma returns a structured 404 with a useful message in the body.
        try:
            body = resp.json()
            msg = (body.get("error") or {}).get("message", "")
        except Exception:
            msg = resp.text[:200]
        die(
            f"Gemma 404: {msg}\n  url: {url}\n  Gemma only loads ontologies it uses; "
            f"try --source ols for broader coverage.",
            source=SOURCE_NAME,
        )
    if resp.status_code == 429:
        die(
            f"Gemma rate-limited (429). Back off and retry. URL: {url}",
            source=SOURCE_NAME,
        )
    if not resp.ok:
        die(
            f"Gemma returned HTTP {resp.status_code}: {url}\n  body: {resp.text[:300]}",
            source=SOURCE_NAME,
        )
    try:
        return resp.json(), raw
    except Exception as e:
        die(f"Gemma response is not JSON: {e}\n  body: {raw[:200]!r}", source=SOURCE_NAME)


def _data_rows(payload: dict) -> list[dict]:
    return payload.get("data") or []


def _row_from_annotation(entry: dict, relation: str) -> dict:
    uri = entry.get("valueUri", "") or ""
    return {
        "term_id": _uri_to_compact_safe(uri) if uri else "",
        "term_uri": uri,
        "term_label": entry.get("value", "") or "",
        "ontology": _uri_to_ontology_slug(uri),
        "relation": relation,
        "source": SOURCE_NAME,
    }


def _parents_or_children(operation: str, term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    uri = to_uri(term)
    encoded = urllib.parse.quote(uri, safe="")
    url = f"{GEMMA_BASE}/annotations/{operation}?uri={encoded}"
    payload, raw = _get_json(url, requests)
    entries = _data_rows(payload)
    df = pd.DataFrame(
        [_row_from_annotation(e, "is_a") for e in entries if e.get("valueUri")],
        columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source"],
    ).drop_duplicates(subset=["term_uri"]).reset_index(drop=True)
    return df, SourceInfo(
        url=url,
        version="Gemma REST v2 (current); fetched live; relations are TRANSITIVE (propagated)",
        sha256=sha256_bytes(raw),
    )


def parents(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    return _parents_or_children("parents", term, ontology)


def children(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    return _parents_or_children("children", term, ontology)


def definition(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    die(
        "Gemma does not expose a term-definition endpoint in v0.1 of this skill.\n"
        "  use `--source ols` for definitions, e.g.:\n"
        f"    python scripts/ontology.py definition {term} --source ols",
        source=SOURCE_NAME,
    )


def search(query: str, ontology: str | None, limit: int) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    encoded = urllib.parse.quote(query, safe="")
    url = f"{GEMMA_BASE}/annotations/search?query={encoded}"
    payload, raw = _get_json(url, requests)
    entries = _data_rows(payload)
    rows = []
    for entry in entries:
        uri = entry.get("valueUri") or ""
        if not uri:
            continue
        ont_slug = _uri_to_ontology_slug(uri)
        if ontology and ontology != "auto" and ont_slug and ont_slug != ontology.lower():
            continue  # filter to requested ontology if asked
        rows.append({
            "term_id": _uri_to_compact_safe(uri),
            "term_uri": uri,
            "term_label": entry.get("value", "") or "",
            "ontology": ont_slug,
            "relation": "search",
            "source": SOURCE_NAME,
            "score": float("nan"),  # Gemma does not expose a score
        })
        if len(rows) >= int(limit):
            break
    df = pd.DataFrame(
        rows,
        columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source", "score"],
    )
    return df, SourceInfo(
        url=url,
        version="Gemma REST v2 (current); annotation search; fetched live",
        sha256=sha256_bytes(raw),
    )
