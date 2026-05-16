"""Tests for the pr_enrichment operation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

STANDARD_COLUMNS = {
    "set_id", "set_name", "set_size", "set_size_after_filter",
    "n_genes_in_input", "pr_auc", "pvalue", "qvalue",
    "mf_pr_auc", "mf_corrected_pvalue", "mf_corrected_qvalue",
    "library_source", "species", "background_kind",
}

REQUIRED_META_FIELDS = {
    "operation", "tool_version", "fetched_at",
    "scores_input_path", "scores_input_sha256", "scores_input_n_genes",
    "gene_col", "score_col", "score_direction",
    "species", "library", "min_set_size", "max_set_size",
    "permutations", "seed", "mf_correction", "n_sets_tested",
    "output_sha256", "reference",
    # Provenance from library + background.
    "library_kind", "library_source_files",
    "background_kind",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_has_artifact(require_enrichment_artifact):
    assert len(require_enrichment_artifact) >= 1


def test_schema(require_enrichment_artifact):
    bad = []
    for tsv, _, _meta in require_enrichment_artifact:
        df = pd.read_csv(tsv, sep="\t", nrows=1)
        missing = STANDARD_COLUMNS - set(df.columns)
        if missing:
            bad.append((tsv.name, missing))
    assert not bad, f"missing columns: {bad}"


def test_meta_fields(require_enrichment_artifact):
    bad = []
    for _tsv, meta_path, meta in require_enrichment_artifact:
        missing = REQUIRED_META_FIELDS - set(meta.keys())
        if missing:
            bad.append((meta_path.name, missing))
    assert not bad, f"missing meta fields: {bad}"


def test_output_sha256_matches(require_enrichment_artifact):
    bad = []
    for tsv, _, meta in require_enrichment_artifact:
        if _sha256_file(tsv) != meta.get("output_sha256"):
            bad.append(tsv.name)
    assert not bad, f"sha256 mismatch: {bad}"


def test_n_sets_matches(require_enrichment_artifact):
    bad = []
    for tsv, _, meta in require_enrichment_artifact:
        with tsv.open() as f:
            actual = sum(1 for _ in f) - 1
        if meta.get("n_sets_tested") != actual:
            bad.append((tsv.name, actual, meta.get("n_sets_tested")))
    assert not bad, f"n_sets_tested mismatch: {bad}"


def test_pvalues_in_unit_interval(require_enrichment_artifact):
    for tsv, _, _meta in require_enrichment_artifact:
        df = pd.read_csv(tsv, sep="\t")
        for col in ("pvalue", "qvalue"):
            vals = df[col].dropna()
            assert (vals >= 0).all() and (vals <= 1).all(), (
                f"{tsv.name}: {col} has values outside [0,1]: min={vals.min()}, max={vals.max()}"
            )


def test_qvalues_monotonic_with_pvalues(require_enrichment_artifact):
    """After sorting by pvalue ascending, qvalues should also be non-decreasing
    (BH property)."""
    for tsv, _, _meta in require_enrichment_artifact:
        df = pd.read_csv(tsv, sep="\t").sort_values("pvalue")
        q = df["qvalue"].dropna().tolist()
        for i in range(1, len(q)):
            assert q[i] >= q[i - 1] - 1e-9, (
                f"{tsv.name}: qvalues not monotone with pvalues at i={i}"
            )


def test_pr_auc_in_unit_interval(require_enrichment_artifact):
    for tsv, _, _meta in require_enrichment_artifact:
        df = pd.read_csv(tsv, sep="\t")
        vals = df["pr_auc"].dropna()
        assert (vals >= 0).all() and (vals <= 1).all(), (
            f"{tsv.name}: pr_auc out of [0,1]: min={vals.min()}, max={vals.max()}"
        )


def test_set_size_respects_filter(require_enrichment_artifact):
    for tsv, _, meta in require_enrichment_artifact:
        lo = meta.get("min_set_size", 0)
        hi = meta.get("max_set_size", 10**9)
        df = pd.read_csv(tsv, sep="\t")
        bad = df[(df["set_size_after_filter"] < lo) | (df["set_size_after_filter"] > hi)]
        assert len(bad) == 0, (
            f"{tsv.name}: {len(bad)} sets violate size filter [{lo},{hi}]"
        )


def test_mf_correction_is_more_stringent(require_enrichment_artifact):
    """Per Ballouz et al. 2017, the MF-corrected p-value distribution should
    be at least as conservative as the raw p-value distribution — the number
    of significant sets after MF correction should be <= the number before."""
    for tsv, _, meta in require_enrichment_artifact:
        if not meta.get("mf_correction"):
            continue
        df = pd.read_csv(tsv, sep="\t")
        n_raw = int((df["pvalue"] < 0.05).sum())
        n_mf = int((df["mf_corrected_pvalue"] < 0.05).sum())
        assert n_mf <= n_raw, (
            f"{tsv.name}: MF correction made MORE sets significant "
            f"({n_mf} mf vs {n_raw} raw), which contradicts its design"
        )


def test_mf_pr_auc_present_when_correction_on(require_enrichment_artifact):
    for tsv, _, meta in require_enrichment_artifact:
        if not meta.get("mf_correction"):
            continue
        df = pd.read_csv(tsv, sep="\t")
        # mf_pr_auc must be populated (not all NaN) when correction is on.
        non_null = df["mf_pr_auc"].notna().sum()
        assert non_null > 0, (
            f"{tsv.name}: mf_correction=True but mf_pr_auc is all null"
        )


def test_taxon_consistency(require_enrichment_artifact):
    """Library source's species must match meta.species."""
    for tsv, _, meta in require_enrichment_artifact:
        df = pd.read_csv(tsv, sep="\t")
        if df.empty:
            continue
        assert (df["species"] == meta["species"]).all(), (
            f"{tsv.name}: row species values don't all match meta.species"
        )
