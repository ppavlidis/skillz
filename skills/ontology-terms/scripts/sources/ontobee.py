"""OntoBee SPARQL source.

OntoBee (https://www.ontobee.org/) hosts a SPARQL endpoint over the OBO
Foundry ontologies at https://sparql.hegroup.org/sparql. We query for
immediate parents / children / definition using standard RDFS / OBO terms.

**Caveats** (matters for picking between sources):
- OntoBee loads each ontology's RDF/OWL form; results can include multiple
  duplicate rows per relation due to the same triple appearing in different
  loaded graphs (e.g. GO core + GO-plus). We deduplicate client-side.
- OntoBee's snapshot of each ontology may lag a few weeks behind the
  current OLS / OBO release. Recorded `ontology_version` is "ontobee
  snapshot (unknown date)" — OntoBee does not expose a clean version
  string per ontology via SPARQL.
- For exact-release pinning, prefer the `obo` source.
- For broadest coverage with explicit version, prefer the `ols` source.
- For SPARQL flexibility (e.g. cross-ontology queries), this is the option.

**Search:** uses SPARQL `FILTER(CONTAINS(LCASE(?l), "query"))` on rdfs:label.
Slower than OLS's pre-indexed search but works for any ontology OntoBee
hosts. No scoring; returns matches in arbitrary SPARQL order.
"""

from __future__ import annotations

import re

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

SOURCE_NAME = "ontobee"
SPARQL_ENDPOINT = "https://sparql.hegroup.org/sparql"

# Ontology slug → graph IRI used by OntoBee. Most OBO ontologies live at
# http://purl.obolibrary.org/obo/merged/<UPPERCASE> in OntoBee's loaded
# graphs. We don't strictly need this for the basic queries below (which
# match across all graphs and dedupe), but it's useful when you want to
# pin to one specific loaded ontology.
def _graph_iri_for(ontology: str) -> str:
    return f"http://purl.obolibrary.org/obo/merged/{ontology.upper()}"


def _run_sparql(query: str, requests) -> tuple[dict, bytes]:
    try:
        resp = http_get(
            SPARQL_ENDPOINT,
            requests,
            params={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=60,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        die(f"OntoBee SPARQL request failed: {e}", source=SOURCE_NAME)
    if resp.status_code == 429:
        die("OntoBee SPARQL rate-limited (429); back off and retry", source=SOURCE_NAME)
    if not resp.ok:
        die(
            f"OntoBee SPARQL returned HTTP {resp.status_code}: {resp.text[:300]}",
            source=SOURCE_NAME,
        )
    raw = resp.content
    try:
        return resp.json(), raw
    except Exception as e:
        die(f"OntoBee response is not JSON: {e}\n  body: {raw[:300]!r}", source=SOURCE_NAME)


def _safe_compact(uri: str) -> str:
    try:
        return to_compact(uri) if uri else ""
    except TermFormatError:
        m = re.search(r"/([A-Za-z]+)[_:](\d+)$", uri or "")
        if m:
            return f"{m.group(1).upper()}:{m.group(2)}"
        return uri or ""


def _bindings(payload: dict) -> list[dict]:
    return ((payload.get("results") or {}).get("bindings") or [])


def _v(binding: dict, key: str) -> str:
    return (binding.get(key) or {}).get("value", "") or ""


def _extras() -> dict:
    return {
        "ontology_version": "ontobee snapshot (release date not exposed via SPARQL)",
        "ontology_version_iri": "",
    }


def _parents_or_children(operation: str, term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    uri = to_uri(term)
    if operation == "parents":
        triple = f"<{uri}> rdfs:subClassOf ?t"
    else:
        triple = f"?t rdfs:subClassOf <{uri}>"
    query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?t ?l WHERE {{
          {triple} .
          OPTIONAL {{ ?t rdfs:label ?l . }}
          FILTER(!isBlank(?t) && ?t != owl:Thing)
        }}
        LIMIT 500
    """
    payload, raw = _run_sparql(query, requests)
    seen = set()
    rows = []
    for b in _bindings(payload):
        t_uri = _v(b, "t")
        if not t_uri or t_uri in seen:
            continue
        seen.add(t_uri)
        rows.append({
            "term_id": _safe_compact(t_uri),
            "term_uri": t_uri,
            "term_label": _v(b, "l"),
            "ontology": ontology,
            "relation": "is_a",
            "source": SOURCE_NAME,
        })
    df = pd.DataFrame(rows, columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source"])
    return df, SourceInfo(
        url=f"{SPARQL_ENDPOINT}?query=<{operation}-of-{term}>",
        version="OntoBee SPARQL (current snapshot)",
        sha256=sha256_bytes(raw),
        extras=_extras(),
    )


def parents(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    return _parents_or_children("parents", term, ontology)


def children(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    return _parents_or_children("children", term, ontology)


def definition(term: str, ontology: str) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    uri = to_uri(term)
    # IAO_0000115 is the OBO Foundry "definition" property; we also collect
    # rdfs:label and (oboInOwl) synonyms.
    query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX iao: <http://purl.obolibrary.org/obo/>
        PREFIX oboInOwl: <http://www.geneontology.org/formats/oboInOwl#>
        SELECT DISTINCT ?l ?d ?syn WHERE {{
          OPTIONAL {{ <{uri}> rdfs:label ?l . }}
          OPTIONAL {{ <{uri}> iao:IAO_0000115 ?d . }}
          OPTIONAL {{ <{uri}> oboInOwl:hasExactSynonym ?syn . }}
        }}
        LIMIT 200
    """
    payload, raw = _run_sparql(query, requests)
    bindings = _bindings(payload)

    label = ""
    defn = ""
    synonyms: list[str] = []
    seen_syn = set()
    for b in bindings:
        if not label:
            label = _v(b, "l")
        if not defn:
            defn = _v(b, "d")
        syn = _v(b, "syn")
        if syn and syn.lower() not in seen_syn:
            synonyms.append(syn)
            seen_syn.add(syn.lower())

    if not (label or defn or synonyms):
        die(
            f"OntoBee returned no label/definition for {uri}. The term may not "
            f"be in OntoBee's loaded graphs.",
            source=SOURCE_NAME,
        )

    row = {
        "term_id": _safe_compact(uri),
        "term_uri": uri,
        "term_label": label,
        "ontology": ontology,
        "relation": "definition",
        "source": SOURCE_NAME,
        "definition": defn,
        "synonyms": "; ".join(synonyms),
    }
    df = pd.DataFrame(
        [row],
        columns=["term_id", "term_uri", "term_label", "ontology", "relation",
                 "source", "definition", "synonyms"],
    )
    return df, SourceInfo(
        url=f"{SPARQL_ENDPOINT}?query=<definition-of-{term}>",
        version="OntoBee SPARQL (current snapshot)",
        sha256=sha256_bytes(raw),
        extras=_extras(),
    )


def search(query: str, ontology: str | None, limit: int) -> tuple[pd.DataFrame, SourceInfo]:
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    q_safe = query.replace('"', r'\"').lower()
    # If an ontology is specified, restrict by URI prefix (OBO purl pattern).
    if ontology and ontology != "auto":
        prefix_filter = f' && STRSTARTS(STR(?t), "http://purl.obolibrary.org/obo/{ontology.upper()}_")'
    else:
        prefix_filter = ""
    sparql_query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?t ?l WHERE {{
          ?t rdfs:label ?l .
          FILTER(CONTAINS(LCASE(STR(?l)), "{q_safe}"){prefix_filter})
        }}
        LIMIT {int(limit) * 3}
    """
    payload, raw = _run_sparql(sparql_query, requests)
    seen = set()
    rows = []
    for b in _bindings(payload):
        t_uri = _v(b, "t")
        if not t_uri or t_uri in seen:
            continue
        seen.add(t_uri)
        ont_slug = ""
        m = re.search(r"obo/([A-Za-z]+)_\d+$", t_uri)
        if m:
            ont_slug = m.group(1).lower()
        rows.append({
            "term_id": _safe_compact(t_uri),
            "term_uri": t_uri,
            "term_label": _v(b, "l"),
            "ontology": ont_slug or (ontology or ""),
            "relation": "search",
            "source": SOURCE_NAME,
            "score": float("nan"),
        })
        if len(rows) >= int(limit):
            break
    df = pd.DataFrame(
        rows,
        columns=["term_id", "term_uri", "term_label", "ontology", "relation", "source", "score"],
    )
    return df, SourceInfo(
        url=f"{SPARQL_ENDPOINT}?query=<search-{query}>",
        version="OntoBee SPARQL (current snapshot)",
        sha256=sha256_bytes(raw),
        extras=_extras(),
    )
