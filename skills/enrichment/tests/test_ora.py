"""Tests for the ORA operation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

CACHE_DIR = Path.home() / ".cache" / "enrichment"

STANDARD_COLUMNS = {
    "set_id", "set_name", "set_size", "set_size_after_filter",
    "n_hits_in_set", "expected_hits", "fold_enrichment",
    "pvalue", "qvalue",
    "mf_baseline_n_hits_in_set", "mf_baseline_pvalue", "mf_baseline_qvalue",
    "library_source", "species", "background_kind",
}

REQUIRED_META_FIELDS = {
    "operation", "tool_version", "fetched_at",
    "hits_input_path", "hits_input_sha256",
    "hits_input_n_symbols", "hits_in_background",
    "species", "library", "min_set_size", "max_set_size",
    "mf_correction", "n_genes_in_background", "n_sets_tested",
    "output_sha256", "reference",
    "library_kind", "library_source_files",
    "background_kind",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="session")
def ora_artifacts():
    out = []
    if not CACHE_DIR.exists():
        return out
    for tsv in sorted(CACHE_DIR.glob("ora__*.tsv")):
        meta_path = tsv.with_suffix(".meta.json")
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        out.append((tsv, meta_path, meta))
    return out


@pytest.fixture()
def require_ora_artifact(ora_artifacts):
    if not ora_artifacts:
        pytest.skip("no ORA artifacts in cache; run `python scripts/ora.py --hits <file>`")
    return ora_artifacts


def test_ora_schema(require_ora_artifact):
    bad = []
    for tsv, _, _meta in require_ora_artifact:
        df = pd.read_csv(tsv, sep="\t", nrows=1)
        missing = STANDARD_COLUMNS - set(df.columns)
        if missing:
            bad.append((tsv.name, missing))
    assert not bad, f"missing columns: {bad}"


def test_ora_meta_fields(require_ora_artifact):
    bad = []
    for _tsv, meta_path, meta in require_ora_artifact:
        missing = REQUIRED_META_FIELDS - set(meta.keys())
        if missing:
            bad.append((meta_path.name, missing))
    assert not bad, f"missing meta fields: {bad}"


def test_ora_output_sha256_matches(require_ora_artifact):
    bad = []
    for tsv, _, meta in require_ora_artifact:
        if _sha256_file(tsv) != meta.get("output_sha256"):
            bad.append(tsv.name)
    assert not bad, f"sha256 mismatch: {bad}"


def test_ora_pvalues_in_unit_interval(require_ora_artifact):
    for tsv, _, _meta in require_ora_artifact:
        df = pd.read_csv(tsv, sep="\t")
        for col in ("pvalue", "qvalue"):
            vals = df[col].dropna()
            assert (vals >= 0).all() and (vals <= 1).all(), (
                f"{tsv.name}: {col} out of [0,1]: min={vals.min()}, max={vals.max()}"
            )


def test_ora_n_hits_le_set_size_and_n(require_ora_artifact):
    """n_hits_in_set must be <= min(set_size_after_filter, hits_in_background)."""
    for tsv, _, meta in require_ora_artifact:
        df = pd.read_csv(tsv, sep="\t")
        n_hits_total = meta.get("hits_in_background", 0)
        bad = df[df["n_hits_in_set"] > df["set_size_after_filter"]]
        assert len(bad) == 0, f"{tsv.name}: n_hits_in_set > set_size for {len(bad)} sets"
        bad2 = df[df["n_hits_in_set"] > n_hits_total]
        assert len(bad2) == 0, f"{tsv.name}: n_hits_in_set > total hits ({n_hits_total}) for {len(bad2)} sets"


def test_ora_expected_hits_sensible(require_ora_artifact):
    """expected_hits = K * n / N must equal set_size_after_filter * hits_in_bg / N."""
    for tsv, _, meta in require_ora_artifact:
        df = pd.read_csv(tsv, sep="\t")
        N = meta.get("n_genes_in_background")
        n = meta.get("hits_in_background")
        if not N or not n:
            continue
        recomputed = df["set_size_after_filter"] * n / N
        diff = (df["expected_hits"] - recomputed).abs().max()
        assert diff < 1e-9, f"{tsv.name}: expected_hits formula doesn't match (max diff {diff})"


def test_ora_qvalues_bh(require_ora_artifact):
    """After sorting by pvalue ascending, qvalues should be non-decreasing."""
    for tsv, _, _meta in require_ora_artifact:
        df = pd.read_csv(tsv, sep="\t").sort_values("pvalue")
        q = df["qvalue"].dropna().tolist()
        for i in range(1, len(q)):
            assert q[i] >= q[i - 1] - 1e-9, f"{tsv.name}: q not monotonic at i={i}"


def test_ora_mf_baseline_present_when_correction_on(require_ora_artifact):
    for tsv, _, meta in require_ora_artifact:
        if not meta.get("mf_correction"):
            continue
        df = pd.read_csv(tsv, sep="\t")
        non_null = df["mf_baseline_pvalue"].notna().sum()
        assert non_null > 0, f"{tsv.name}: mf_correction=True but mf_baseline_pvalue all null"


def test_ora_top_hit_significant(require_ora_artifact):
    """At least the top hit should be highly significant — if the smallest
    p-value is > 0.1, something is broken (no signal at all)."""
    for tsv, _, _meta in require_ora_artifact:
        df = pd.read_csv(tsv, sep="\t")
        min_p = float(df["pvalue"].min())
        assert min_p < 0.1, (
            f"{tsv.name}: smallest p-value is {min_p:.4f}; either the hit list is "
            f"random or the test is broken"
        )
