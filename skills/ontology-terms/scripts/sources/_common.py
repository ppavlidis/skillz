"""Shared helpers for ontology source modules.

Each source under sources/ exposes four functions:
    parents(term_id, ontology) -> pd.DataFrame
    children(term_id, ontology) -> pd.DataFrame
    definition(term_id, ontology) -> pd.DataFrame
    search(query, ontology, limit) -> pd.DataFrame

Each returns a DataFrame with the standard schema. This module factors out
term-ID/URI conversion, cache paths, atomic writes, sha256, and politeness
(User-Agent, rate-limit-friendly defaults). See SKILL.md "Design contract".
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

TOOL_VERSION = "0.1.0"

CACHE_DIR = Path.home() / ".cache" / "ontology-terms"

STANDARD_COLUMNS = ["term_id", "term_uri", "term_label", "ontology", "relation", "source"]

# Per the be-nice-to-APIs policy: identify ourselves on every outbound request.
USER_AGENT = (
    f"ontology-terms/{TOOL_VERSION} (https://github.com/ppavlidis/skillz; "
    f"+contact via repo issues)"
)

OBO_BASE = "http://purl.obolibrary.org/obo/"

# ---------------------------------------------------------------------------
# Ontology registry
#
# Two tables cover the two URI worlds that appear in practice:
#
#   PREFIX_TO_ONTOLOGY  — OBO Foundry ontologies (URI = OBO_BASE + PREFIX_ID).
#                         The slug is used as the OLS ontology path component
#                         and as the --ontology value.
#
#   _NON_OBO_URIS       — Ontologies that do NOT use OBO PURL URIs. Each entry
#                         maps an uppercase prefix → (slug, uri_template, uri_regex).
#                         uri_template has a {num} placeholder (zero-padded to 7).
#                         uri_regex must capture the numeric ID as group(1).
#
# Sources that construct URIs from compact IDs check _NON_OBO_URIS first, then
# fall back to the OBO PURL pattern for everything in PREFIX_TO_ONTOLOGY.
# ---------------------------------------------------------------------------

PREFIX_TO_ONTOLOGY: dict[str, str] = {
    # Core ontologies used heavily in Gemma
    "GO": "go",
    "MONDO": "mondo",
    "MP": "mp",
    "HP": "hp",
    "CL": "cl",
    "UBERON": "uberon",
    "DOID": "doid",
    "CHEBI": "chebi",
    "PR": "pr",
    "OBI": "obi",
    # Phenotype / anatomy
    "PATO": "pato",
    "EMAPA": "emapa",
    "MA": "ma",
    "ZFA": "zfa",
    "FBBT": "fbbt",
    "WBBT": "wbbt",
    "NBO": "nbo",
    "SYMP": "symp",
    # Sequence / genomics
    "SO": "so",
    "OBA": "oba",
    # Taxonomy
    "NCBITAXON": "ncbitaxon",
    # Relations / upper-level
    "RO": "ro",
    "BFO": "bfo",
    "IAO": "iao",
    "OGMS": "ogms",
}

# Ontologies whose canonical URIs are NOT OBO PURLs.
# Format: UPPERCASE_PREFIX -> (ols_slug, uri_template, uri_regex)
#   uri_template:  receives int(num) via .format(num=...)
#   uri_regex:     must match the full URI and capture the numeric ID as group(1)
_NON_OBO_URIS: dict[str, tuple[str, str, re.Pattern]] = {
    "EFO": (
        "efo",
        "http://www.ebi.ac.uk/efo/EFO_{num:07d}",
        re.compile(r"^https?://www\.ebi\.ac\.uk/efo/EFO_(\d+)$"),
    ),
}

# Combined slug lookup (non-OBO entries take precedence for URI construction).
_ALL_PREFIXES: dict[str, str] = {
    **PREFIX_TO_ONTOLOGY,
    **{p: info[0] for p, info in _NON_OBO_URIS.items()},
}


# ---------------------------------------------------------------------------
# Term notation: compact (GO:0006915) <-> URI
# ---------------------------------------------------------------------------

_COMPACT_RE = re.compile(r"^([A-Za-z]+):(\d+)$")
_URI_RE = re.compile(r"^https?://purl\.obolibrary\.org/obo/([A-Za-z]+)_(\d+)$")


def is_uri(term: str) -> bool:
    return term.startswith("http://") or term.startswith("https://")


def is_compact(term: str) -> bool:
    return bool(_COMPACT_RE.match(term))


class TermFormatError(ValueError):
    """Raised by term conversion helpers when input doesn't parse. Library
    code should catch this and decide whether to surface it; CLI code should
    convert to die() at the user-visible boundary."""


def to_uri(term: str) -> str:
    """Compact ID or URI -> canonical URI.

    Checks _NON_OBO_URIS first (e.g. EFO uses EBI URIs, not OBO PURLs),
    then falls back to the OBO PURL pattern for all other prefixes.
    Raises TermFormatError on unparseable input.
    """
    if is_uri(term):
        return term
    m = _COMPACT_RE.match(term)
    if not m:
        raise TermFormatError(f"unparseable term: {term!r}; expected GO:0006915 or full URI")
    prefix, num = m.group(1).upper(), m.group(2)
    if prefix in _NON_OBO_URIS:
        _, uri_template, _ = _NON_OBO_URIS[prefix]
        return uri_template.format(num=int(num))
    return f"{OBO_BASE}{prefix}_{num}"


def to_compact(term: str) -> str:
    """URI -> compact ID. Pass-through if already compact.

    Handles both OBO PURL URIs and known non-OBO URIs (e.g. EFO).
    Raises TermFormatError for unrecognised URI patterns; callers that want
    best-effort conversion should catch and fall back.
    """
    if is_compact(term):
        return term
    m = _URI_RE.match(term)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    for prefix, (_, _, uri_re) in _NON_OBO_URIS.items():
        m2 = uri_re.match(term)
        if m2:
            return f"{prefix}:{m2.group(1)}"
    raise TermFormatError(
        f"URI not in a recognised form: {term!r}\n"
        f"  Supported: OBO PURL (purl.obolibrary.org/obo/PREFIX_ID) and "
        f"known non-OBO patterns ({list(_NON_OBO_URIS)})"
    )


def infer_ontology(term: str) -> str:
    """Auto-infer ontology slug from a term's prefix.

    For prefixes not in the registry, warns and falls back to prefix.lower()
    (which OLS and Gemma often accept). The caller can pass --ontology
    explicitly to override.
    """
    if is_uri(term):
        try:
            compact = to_compact(term)
        except TermFormatError:
            # Non-OBO URI: try to extract prefix from the path tail
            m = re.search(r"/([A-Za-z]+)[_:](\d+)$", term)
            if m:
                compact = f"{m.group(1)}:{m.group(2)}"
            else:
                die(f"can't infer ontology from URI: {term!r}; pass --ontology explicitly")
    else:
        compact = term
    m = _COMPACT_RE.match(compact)
    if not m:
        die(f"can't infer ontology from term: {term!r}")
    prefix = m.group(1).upper()
    ont = _ALL_PREFIXES.get(prefix)
    if ont is None:
        # Graceful fallback: use prefix.lower() as the slug — works for the
        # majority of OBO ontologies OLS hosts, even if not in our registry.
        sys.stderr.write(
            f"[ontology-terms] prefix {prefix!r} not in registry; "
            f"using {prefix.lower()!r} as ontology slug. "
            f"Pass --ontology explicitly if this fails.\n"
        )
        return prefix.lower()
    return ont


# ---------------------------------------------------------------------------
# Provenance, cache, sha256, atomic writes
# ---------------------------------------------------------------------------


from dataclasses import dataclass, field


@dataclass
class SourceInfo:
    url: str
    version: str
    sha256: str
    extras: dict = field(default_factory=dict)  # source-specific meta to spread into .meta.json (e.g. ontology_version)


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
    """Make a string safe for use in a filename — keep alnum + underscores + hyphens."""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", s)[:120]


def cache_paths(
    operation: str,
    source: str,
    term_or_query: str,
    ontology: str | None,
    extras: str = "",
    out: Path | None = None,
) -> tuple[Path, Path]:
    """Return (tsv_path, meta_path) for this artifact.

    Cache key encodes operation + source + term/query + ontology + any extras
    that affect content. A change to any of these goes to a different file —
    a stale cache cannot masquerade as fresh.
    """
    if out is not None:
        tsv_path = Path(out)
        meta_path = tsv_path.with_suffix(".meta.json")
        return tsv_path, meta_path
    parts = [operation, source, _sanitize(term_or_query)]
    if ontology:
        parts.append(_sanitize(ontology))
    if extras:
        parts.append(_sanitize(extras))
    stem = "__".join(parts)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{stem}.tsv", CACHE_DIR / f"{stem}.meta.json"


def validate_schema(df: pd.DataFrame, op: str, source: str) -> None:
    missing = [c for c in STANDARD_COLUMNS if c not in df.columns]
    if missing:
        die(
            f"source {source!r} returned a DataFrame missing required columns "
            f"for operation {op!r}: {missing}\n"
            f"got: {list(df.columns)}"
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
    input_term: str,
    ontology: str,
    source_info: SourceInfo,
    cache_dir: Path,
    out: Path | None,
    extras: str = "",
    extra_meta: dict[str, Any] | None = None,
) -> Path:
    """Write TSV + sidecar .meta.json atomically. Returns the TSV path.

    Empty outputs are accepted here (some operations legitimately return zero
    rows, e.g. a term with no children). The source is responsible for
    distinguishing legitimate-empty from upstream-failure-empty.
    """
    validate_schema(df, operation, source)

    # For parents/children/definition, the term ID matters for cache key.
    # For search, the query string takes that slot.
    cache_key = input_term if operation != "search" else input_term

    tsv_path, meta_path = cache_paths(operation, source, cache_key, ontology, extras, out)
    tsv_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = tsv_path.with_suffix(tsv_path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(tsv_path)
    output_sha = sha256_file(tsv_path)

    meta = {
        "operation": operation,
        "source": source,
        "ontology": ontology,
        "n_rows": int(len(df)),
        "fetched_at": iso_now(),
        "source_url": source_info.url,
        "source_version": source_info.version,
        "source_sha256": source_info.sha256,
        "output_sha256": output_sha,
        "tool_version": TOOL_VERSION,
    }
    # Spread source-specific metadata (e.g. ontology_version, ontology_version_iri).
    if source_info.extras:
        meta.update(source_info.extras)
    if operation == "search":
        meta["input_query"] = input_term
    else:
        # Best-effort: emit both forms when convertible; pass-through otherwise.
        try:
            meta["input_term_id"] = input_term if is_compact(input_term) else to_compact(input_term)
        except TermFormatError:
            meta["input_term_id"] = input_term
        try:
            meta["input_term_uri"] = input_term if is_uri(input_term) else to_uri(input_term)
        except TermFormatError:
            meta["input_term_uri"] = input_term

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
    """Wrap requests.get with our standard User-Agent."""
    headers = dict(kwargs.pop("headers", None) or {})
    headers.setdefault("User-Agent", USER_AGENT)
    return requests_module.get(url, headers=headers, **kwargs)


def die(msg: str, source: str | None = None) -> "NoReturn":  # type: ignore[name-defined]
    prefix = f"[ontology-terms:{source}] " if source else "[ontology-terms] "
    print(prefix + "ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def require_module(name: str, install_hint: str, source: str) -> Any:
    try:
        return __import__(name)
    except ImportError as e:
        die(
            f"required module '{name}' is not installed.\n"
            f"  install: {install_hint}\n"
            f"  underlying error: {e}",
            source=source,
        )
