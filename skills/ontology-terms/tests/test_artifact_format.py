"""Cache-integrity tests for ontology-terms artifacts.

Catches: silent schema drift, meta/TSV mismatch, missing provenance fields,
partial writes. Same shape as gene-set-fetch's test_artifact_format.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

STANDARD_COLUMNS = {"term_id", "term_uri", "term_label", "ontology", "relation", "source"}

REQUIRED_META_FIELDS = {
    "operation", "source", "ontology", "n_rows",
    "fetched_at", "source_url", "source_version",
    "source_sha256", "output_sha256", "tool_version",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_cache_has_at_least_one_artifact(require_any_cache):
    assert len(require_any_cache) >= 1


def test_every_tsv_has_standard_columns(require_any_cache):
    bad = []
    for tsv, _meta_path, _meta in require_any_cache:
        df = pd.read_csv(tsv, sep="\t", dtype="string", nrows=1)
        missing = STANDARD_COLUMNS - set(df.columns)
        if missing:
            bad.append((tsv.name, missing))
    assert not bad, f"sets missing standard columns: {bad}"


def test_every_meta_has_required_fields(require_any_cache):
    bad = []
    for _tsv, meta_path, meta in require_any_cache:
        missing = REQUIRED_META_FIELDS - set(meta.keys())
        if missing:
            bad.append((meta_path.name, missing))
    assert not bad, f"metas missing required fields: {bad}"


def test_output_sha256_matches_file(require_any_cache):
    bad = []
    for tsv, _meta_path, meta in require_any_cache:
        actual = _sha256_file(tsv)
        recorded = meta.get("output_sha256")
        if recorded != actual:
            bad.append(tsv.name)
    assert not bad, f"output_sha256 mismatches: {bad}"


def test_n_rows_matches_tsv(require_any_cache):
    bad = []
    for tsv, _meta_path, meta in require_any_cache:
        with tsv.open() as f:
            actual = sum(1 for _ in f) - 1
        if meta.get("n_rows") != actual:
            bad.append((tsv.name, meta.get("n_rows"), actual))
    assert not bad, f"n_rows mismatches: {bad}"


def test_source_sha256_is_hex(require_any_cache):
    bad = []
    for _tsv, meta_path, meta in require_any_cache:
        ssh = meta.get("source_sha256", "")
        if not (isinstance(ssh, str) and len(ssh) == 64 and all(c in "0123456789abcdef" for c in ssh)):
            bad.append((meta_path.name, ssh[:20] if ssh else ""))
    assert not bad, f"bad source_sha256: {bad}"
