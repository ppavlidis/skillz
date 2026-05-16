"""Shared helpers for fetchers.

A fetcher's job: take a recipe (set name, species, args, ensembl release),
produce a TSV in the standard schema (ensembl_id, symbol, entrez_id, species,
source, +extras), and write it next to a sidecar .meta.json that captures
full provenance.

The functions here factor out the parts every fetcher does the same way:
sha256, cache path resolution, schema validation, meta JSON construction,
atomic-ish writing. Each fetcher stays focused on one thing: how to talk to
its upstream source.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

TOOL_VERSION = "0.1.0"

STANDARD_COLUMNS = ["ensembl_id", "symbol", "entrez_id", "species", "source"]

# Identify ourselves on every outbound request. Free public bioinformatics
# APIs (Ensembl, EBI, NCBI, MGI) are run by academic groups; a descriptive
# User-Agent lets operators find us if we cause trouble. See feedback memory
# "Be nice to APIs".
USER_AGENT = (
    f"gene-set-fetch/{TOOL_VERSION} (https://github.com/ppavlidis/skillz; "
    f"+contact via repo issues)"
)


def http_get(url: str, requests_module, **kwargs):
    """Wrap requests.get with our standard User-Agent. Honor caller's headers."""
    headers = dict(kwargs.pop("headers", None) or {})
    headers.setdefault("User-Agent", USER_AGENT)
    return requests_module.get(url, headers=headers, **kwargs)


@dataclass
class SourceInfo:
    """Provenance for an upstream fetch."""
    url: str
    version: str
    sha256: str
    durability: str = ""  # one-line note on how durable this source is
    notes: str = ""       # any per-fetch notes worth recording


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


def cache_paths(
    name: str,
    ensembl_release: int,
    source_version_tag: str,
    cache_dir: Path,
    out: Path | None,
) -> tuple[Path, Path]:
    """Return (tsv_path, meta_path) for this artifact.

    Filename encodes everything that affects content: set name, Ensembl release,
    and a short source-version tag. A stale file cannot masquerade as fresh
    because the cache key bakes in the source version.
    """
    if out is not None:
        tsv_path = Path(out)
        meta_path = tsv_path.with_suffix(".meta.json")
        return tsv_path, meta_path

    stem = f"{name}__ensembl{ensembl_release}__{source_version_tag}"
    tsv_path = cache_dir / f"{stem}.tsv"
    meta_path = cache_dir / f"{stem}.meta.json"
    return tsv_path, meta_path


def validate_schema(df: pd.DataFrame, set_name: str) -> None:
    """All fetcher output must conform to the standard schema and be non-empty.

    A zero-row output is treated as a fail-loud violation: it usually means
    upstream changed or a parser silently misaligned. Better to crash now
    than to ship an empty TSV that downstream code happily reads.
    """
    missing = [c for c in STANDARD_COLUMNS if c not in df.columns]
    if missing:
        die(
            f"fetcher for '{set_name}' produced a DataFrame missing "
            f"required columns: {missing}\n"
            f"got columns: {list(df.columns)}"
        )
    if len(df) == 0:
        die(
            f"fetcher for '{set_name}' produced zero rows. This is treated as "
            f"a failure (silent empty outputs rot downstream). If you genuinely "
            f"expect zero rows, investigate the upstream first."
        )


def write_artifact(
    df: pd.DataFrame,
    name: str,
    species: str,
    ensembl_release: int,
    source: SourceInfo,
    cache_dir: Path,
    out: Path | None,
    source_version_tag: str,
    extra_meta: dict[str, Any] | None = None,
) -> Path:
    """Write TSV + sidecar .meta.json. Returns the TSV path.

    The TSV is written atomically (via a temp file + rename) so a downstream
    reader never sees a half-written file.
    """
    validate_schema(df, name)

    tsv_path, meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    tsv_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: temp file + rename.
    tmp = tsv_path.with_suffix(tsv_path.suffix + ".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(tsv_path)

    output_sha = sha256_file(tsv_path)

    meta = {
        "set": name,
        "species": species,
        "ensembl_release": ensembl_release,
        "n_genes": int(len(df)),
        "fetched_at": iso_now(),
        "source_url": source.url,
        "source_version": source.version,
        "source_sha256": source.sha256,
        "source_durability": source.durability,
        "source_notes": source.notes,
        "output_sha256": output_sha,
        "tool_version": TOOL_VERSION,
    }
    if extra_meta:
        meta.update(extra_meta)

    tmp_meta = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp_meta.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    tmp_meta.replace(meta_path)

    return tsv_path


def is_fresh(tsv_path: Path, meta_path: Path) -> bool:
    """Treat a cached artifact as fresh iff both files exist and the meta
    parses and references the TSV file we have (by checking output_sha256).

    Cache freshness does NOT consider upstream — it's a same-content check, not
    a same-as-upstream check. Use --refresh to force re-fetch.
    """
    if not (tsv_path.exists() and meta_path.exists()):
        return False
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return False
    return meta.get("output_sha256") == sha256_file(tsv_path)


def die(msg: str, fetcher: str | None = None) -> "NoReturn":  # type: ignore[name-defined]
    """Fail loud: write a clear error to stderr and exit non-zero.

    Use this for every recoverable-but-don't-recover situation: HTTP failure,
    schema drift, missing dependency, parse error. The point is that the
    caller gets a useful pointer to inspect, not a silent fallback.
    """
    prefix = f"[gene-set-fetch:{fetcher}] " if fetcher else "[gene-set-fetch] "
    print(prefix + "ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def require_module(name: str, install_hint: str, fetcher: str) -> Any:
    """Import a module or die with a clear install hint."""
    try:
        return __import__(name)
    except ImportError as e:
        die(
            f"required module '{name}' is not installed.\n"
            f"  install: {install_hint}\n"
            f"  underlying error: {e}",
            fetcher=fetcher,
        )
