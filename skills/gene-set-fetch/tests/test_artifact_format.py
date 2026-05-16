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
        # n_genes recorded in meta must match TSV row count (header excluded).
        with tsv.open() as f:
            row_count = sum(1 for _ in f) - 1
        if row_count == 0:
            empty.append(tsv.name)
        elif meta.get("n_genes") != row_count:
            pytest.fail(
                f"{tsv.name}: meta.n_genes ({meta.get('n_genes')}) "
                f"≠ TSV row count ({row_count})"
            )
    assert not empty, f"empty TSVs (silent-failure indicator): {empty}"


def test_every_meta_has_required_fields(require_any_cache):
    bad = []
    for _tsv, meta_path, meta in require_any_cache:
        is_composite = "compose" in meta
        required = REQUIRED_META_FIELDS_COMPOSITE if is_composite else REQUIRED_META_FIELDS_LEAF
        missing = required - set(meta.keys())
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
