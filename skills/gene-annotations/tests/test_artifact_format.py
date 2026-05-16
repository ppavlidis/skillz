"""Cache-integrity tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

STANDARD_COLUMNS = {
    "gene_id", "gene_symbol", "gene_uniprot", "gene_entrez",
    "term_id", "term_label", "term_aspect",
    "evidence_code", "qualifier", "propagated",
    "species", "source",
}

REQUIRED_META_FIELDS = {
    "operation", "source", "species", "taxon_id",
    "input", "input_resolved", "propagated", "n_rows",
    "fetched_at", "source_url", "source_version",
    "source_sha256", "output_sha256", "tool_version",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_cache_has_artifacts(require_any_cache):
    assert len(require_any_cache) >= 1


def test_every_tsv_has_standard_columns(require_any_cache):
    bad = []
    for tsv, _, _meta in require_any_cache:
        df = pd.read_csv(tsv, sep="\t", dtype="string", nrows=1)
        missing = STANDARD_COLUMNS - set(df.columns)
        if missing:
            bad.append((tsv.name, missing))
    assert not bad, f"missing columns: {bad}"


def test_every_meta_has_required_fields(require_any_cache):
    bad = []
    for _tsv, meta_path, meta in require_any_cache:
        missing = REQUIRED_META_FIELDS - set(meta.keys())
        if missing:
            bad.append((meta_path.name, missing))
    assert not bad, f"missing meta fields: {bad}"


def test_output_sha256_matches(require_any_cache):
    bad = []
    for tsv, _, meta in require_any_cache:
        if _sha256_file(tsv) != meta.get("output_sha256"):
            bad.append(tsv.name)
    assert not bad, f"sha256 mismatches: {bad}"


def test_n_rows_matches(require_any_cache):
    bad = []
    for tsv, _, meta in require_any_cache:
        with tsv.open() as f:
            actual = sum(1 for _ in f) - 1
        if meta.get("n_rows") != actual:
            bad.append((tsv.name, meta.get("n_rows"), actual))
    assert not bad, f"n_rows mismatches: {bad}"
