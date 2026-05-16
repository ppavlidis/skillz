"""Tests for the multifunctionality operation.

Coverage:
- Cache integrity (schema, meta fields, sha256, row counts)
- Scoring invariants (monotonic rank, percentile range, n_annotations sane)
- Known-gene sanity (canonical multifunctional genes rank high)
- Bottom-of-distribution check (genes with very few annotations rank low)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

STANDARD_COLUMNS = {
    "gene_id", "gene_symbol", "gene_uniprot", "n_annotations",
    "mf_score", "mf_rank", "mf_percentile", "species", "source",
}

REQUIRED_META_FIELDS = {
    "operation", "source", "species", "aspect", "namespace",
    "evidence_codes_filter", "propagated", "background_kind",
    "n_genes_in_background", "n_terms_used_in_calculation",
    "fetched_at", "gaf_url", "gaf_sha256", "gaf_date_generated",
    "obo_url", "obo_sha256", "obo_data_version",
    "output_sha256", "tool_version", "formula", "reference",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_cache_has_artifact(require_mf_artifact):
    assert len(require_mf_artifact) >= 1


def test_schema(require_mf_artifact):
    bad = []
    for tsv, _, _meta in require_mf_artifact:
        df = pd.read_csv(tsv, sep="\t", nrows=1)
        missing = STANDARD_COLUMNS - set(df.columns)
        if missing:
            bad.append((tsv.name, missing))
    assert not bad, f"missing columns: {bad}"


def test_meta_fields(require_mf_artifact):
    bad = []
    for _tsv, meta_path, meta in require_mf_artifact:
        missing = REQUIRED_META_FIELDS - set(meta.keys())
        if missing:
            bad.append((meta_path.name, missing))
    assert not bad, f"missing meta fields: {bad}"


def test_output_sha256_matches(require_mf_artifact):
    bad = []
    for tsv, _meta_path, meta in require_mf_artifact:
        if _sha256_file(tsv) != meta.get("output_sha256"):
            bad.append(tsv.name)
    assert not bad, f"sha256 mismatch: {bad}"


def test_n_rows_matches_background(require_mf_artifact):
    bad = []
    for tsv, _meta_path, meta in require_mf_artifact:
        with tsv.open() as f:
            actual = sum(1 for _ in f) - 1
        if meta.get("n_genes_in_background") != actual:
            bad.append((tsv.name, actual, meta.get("n_genes_in_background")))
    assert not bad, f"n_rows != n_genes_in_background: {bad}"


def test_ranks_are_dense_and_sequential(require_mf_artifact):
    """Rank 1..N with no gaps or duplicates."""
    for tsv, _, _meta in require_mf_artifact:
        df = pd.read_csv(tsv, sep="\t")
        ranks = sorted(df["mf_rank"].tolist())
        expected = list(range(1, len(df) + 1))
        assert ranks == expected, f"{tsv.name}: ranks not dense/sequential"


def test_mf_score_monotonic_with_rank(require_mf_artifact):
    """Higher rank number = lower (or equal) score."""
    for tsv, _, _meta in require_mf_artifact:
        df = pd.read_csv(tsv, sep="\t").sort_values("mf_rank")
        scores = df["mf_score"].tolist()
        for i in range(1, len(scores)):
            assert scores[i] <= scores[i - 1], (
                f"{tsv.name}: rank {df['mf_rank'].iloc[i]} has higher score than rank {df['mf_rank'].iloc[i-1]}"
            )


def test_percentile_in_unit_interval(require_mf_artifact):
    for tsv, _, _meta in require_mf_artifact:
        df = pd.read_csv(tsv, sep="\t")
        assert df["mf_percentile"].min() > 0, f"{tsv.name}: min percentile <= 0"
        assert df["mf_percentile"].max() == 1.0, f"{tsv.name}: max percentile != 1.0"
        assert df["mf_percentile"].le(1.0).all(), f"{tsv.name}: percentile > 1"


def test_known_multifunctional_genes_rank_high(require_mf_artifact):
    """Genes G&P 2011 explicitly flagged as the most multifunctional MUST
    land in the top 1% of the ranking. These are the unambiguous "always-
    a-hit" genes (TNF, TGFB1, VEGFA, TP53 in any reasonable annotated
    universe). If any falls below the 99th percentile, propagation is
    almost certainly broken."""
    very_top_mf = {"TP53", "TNF", "TGFB1", "VEGFA"}
    for tsv, _, meta in require_mf_artifact:
        if meta.get("species") != "human":
            continue
        df = pd.read_csv(tsv, sep="\t")
        symbol_to_pct = dict(zip(df["gene_symbol"], df["mf_percentile"]))
        bad = []
        for s in very_top_mf:
            pct = symbol_to_pct.get(s)
            if pct is None:
                continue  # may be filtered out by background; ok
            if pct < 0.99:
                bad.append((s, round(pct, 4)))
        assert not bad, (
            f"the most-multifunctional canonical genes (TNF/TGFB1/VEGFA/TP53) "
            f"didn't land in the top 1%: {bad}. propagation may be broken."
        )


def test_n_annotations_decreases_or_equal_with_rank(require_mf_artifact):
    """Genes with few annotations should be at the bottom. Specifically, no
    gene in the bottom 1% should have more than 10 BP annotations — that
    would suggest the MF formula isn't reflecting annotation count
    sensibly."""
    for tsv, _, _meta in require_mf_artifact:
        df = pd.read_csv(tsv, sep="\t").sort_values("mf_rank")
        N = len(df)
        bottom_1pct = df.tail(max(1, N // 100))
        high_annot_in_bottom = bottom_1pct[bottom_1pct["n_annotations"] > 10]
        assert len(high_annot_in_bottom) == 0, (
            f"{tsv.name}: bottom 1% contains genes with >10 BP annotations "
            f"({len(high_annot_in_bottom)} of them); formula may be inverted"
        )


def test_evidence_codes_filter_default_is_all(require_mf_artifact):
    """Per the IEA-isn't-lower-quality policy, default must include all codes."""
    for tsv, _meta_path, meta in require_mf_artifact:
        # Look at the filename to detect if this artifact was generated with
        # the default ("all") evidence filter.
        if "__all." in tsv.name or "__all.meta" in tsv.name:
            assert meta.get("evidence_codes_filter") == "all", (
                f"{tsv.name}: default-tagged artifact has non-'all' evidence filter"
            )
