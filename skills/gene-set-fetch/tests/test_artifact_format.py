"""Cache-integrity tests.

For every cached artifact: schema is correct, sidecar meta is complete, and
the meta's output_sha256 matches the file on disk. No network. Catches:
- silent schema drift in fetchers
- partially written cache files
- missing or stale provenance fields
- meta/TSV mismatch (e.g. a TSV regenerated without rewriting its meta)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

STANDARD_COLUMNS = {"ensembl_id", "symbol", "entrez_id", "species", "source"}

REQUIRED_META_FIELDS_LEAF = {
    "set",
    "species",
    "ensembl_release",
    "n_genes",
    "fetched_at",
    "source_url",
    "source_version",
    "source_sha256",
    "output_sha256",
    "tool_version",
}

REQUIRED_META_FIELDS_COMPOSITE = {
    "set",
    "species",
    "ensembl_release",
    "n_genes",
    "fetched_at",
    "compose",
    "output_sha256",
    "tool_version",
}

# Ad-hoc query artifacts (query.py: disease / genomic) are a distinct family:
# they are NOT pinned to a user-chosen Ensembl release, so they carry
# `query_type` instead of `ensembl_release`, and genomic sets count `n_rows`
# (paired rows) rather than a flat `n_genes`. They still owe full provenance.
REQUIRED_META_FIELDS_QUERY = {
    "set",
    "query_type",
    "species",
    "fetched_at",
    "source_url",
    "source_version",
    "source_sha256",
    "output_sha256",
    "tool_version",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_cache_has_at_least_one_artifact(require_any_cache):
    """Sanity: don't pretend tests pass when the cache is empty."""
    assert len(require_any_cache) >= 1


def test_every_tsv_has_standard_columns(require_any_cache):
    bad = []
    for tsv, _meta_path, meta in require_any_cache:
        df = pd.read_csv(tsv, sep="\t", dtype="string", nrows=1)
        missing = STANDARD_COLUMNS - set(df.columns)
        if missing:
            bad.append((tsv.name, missing))
    assert not bad, f"sets missing standard columns: {bad}"


def test_every_tsv_is_non_empty(require_any_cache):
    """An empty TSV is the canonical silent-failure mode. Reject."""
    empty = []
    for tsv, _meta_path, meta in require_any_cache:
        # The recorded row count must match the TSV. Named/disease sets declare
        # `n_genes`; genomic (head-to-head) sets emit paired rows and declare
        # `n_rows` instead. Use whichever the meta provides.
        with tsv.open() as f:
            row_count = sum(1 for _ in f) - 1
        declared = meta.get("n_genes", meta.get("n_rows"))
        if row_count == 0:
            empty.append(tsv.name)
        elif declared != row_count:
            key = "n_genes" if "n_genes" in meta else "n_rows"
            pytest.fail(
                f"{tsv.name}: meta.{key} ({declared}) ≠ TSV row count ({row_count})"
            )
    assert not empty, f"empty TSVs (silent-failure indicator): {empty}"


def _required_fields_for(meta: dict) -> set[str]:
    """Pick the required-field set by artifact family.

    Three families: composite sets (compose.py), ad-hoc query artifacts
    (query.py, tagged with `query_type`), and leaf named sets (write_artifact).
    """
    if "compose" in meta:
        return REQUIRED_META_FIELDS_COMPOSITE
    if "query_type" in meta:
        return REQUIRED_META_FIELDS_QUERY
    return REQUIRED_META_FIELDS_LEAF


def test_every_meta_has_required_fields(require_any_cache):
    bad = []
    for _tsv, meta_path, meta in require_any_cache:
        missing = _required_fields_for(meta) - set(meta.keys())
        if missing:
            bad.append((meta_path.name, missing))
    assert not bad, f"metas missing required fields: {bad}"


def test_output_sha256_matches_file(require_any_cache):
    """If the meta and TSV ever drift apart, downstream provenance lies."""
    bad = []
    for tsv, _meta_path, meta in require_any_cache:
        actual = _sha256_file(tsv)
        recorded = meta.get("output_sha256")
        if recorded != actual:
            bad.append((tsv.name, recorded, actual))
    assert not bad, (
        f"output_sha256 in meta does not match TSV on disk for: "
        f"{[b[0] for b in bad]}"
    )


def test_source_sha256_is_64_hex(require_any_cache):
    """Source hash must be present and look like a sha256 for leaf sets."""
    bad = []
    for _tsv, meta_path, meta in require_any_cache:
        if "compose" in meta:
            continue  # composites don't have a single source_sha256
        ssh = meta.get("source_sha256", "")
        if not (isinstance(ssh, str) and len(ssh) == 64 and all(c in "0123456789abcdef" for c in ssh)):
            bad.append((meta_path.name, ssh[:20] if ssh else ""))
    assert not bad, f"leaf metas with bad source_sha256: {bad}"
