"""Known annotation sanity tests.

Catches semantic regressions: well-known gene/term pairs that any working
GOA implementation MUST return.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _find_artifact(cached_artifacts, operation: str, input_substring: str):
    for tsv, _meta_path, meta in cached_artifacts:
        if meta.get("operation") != operation:
            continue
        if input_substring in str(meta.get("input", "")) or input_substring in str(meta.get("input_resolved", "")):
            return tsv, meta
    return None


def test_apoptosis_geneset_contains_canonical_apoptotic_genes(require_any_cache):
    """GO:0006915 with descendants should yield genes including TP53, BCL2,
    BAX, BAK1, CASP3 — the textbook apoptosis regulators."""
    found = _find_artifact(require_any_cache, "genes_with_annotation", "GO:0006915")
    if found is None:
        pytest.skip("genes_with_annotation for GO:0006915 not in cache")
    tsv, _meta = found
    df = pd.read_csv(tsv, sep="\t", dtype="string")
    symbols = set(df["gene_symbol"].dropna().str.upper())
    expected = {"TP53", "BCL2", "BAX", "CASP3"}
    missing = expected - symbols
    assert not missing, (
        f"apoptosis genes_with_annotation missing canonical regulators: {sorted(missing)} — "
        f"either the term ID is wrong, propagation isn't working, or the source is broken"
    )


def test_apoptosis_propagated_mix_in_propagated_call(require_any_cache):
    """In a propagated genes_with_annotation call, the output must contain BOTH
    direct rows (gene annotated exactly to the query term) and propagated rows
    (gene annotated to a descendant). A propagated call where every row has
    propagated=True (no direct rows) implies the source can't distinguish
    per-row direct from descendant — a real semantic gap."""
    found = _find_artifact(require_any_cache, "genes_with_annotation", "GO:0006915")
    if found is None:
        pytest.skip()
    tsv, meta = found
    if not meta.get("propagated"):
        pytest.skip("artifact was fetched with --direct; not testing propagation mix")
    df = pd.read_csv(tsv, sep="\t", dtype="string")
    propagated_vals = df["propagated"].astype(str).str.lower()
    n_direct = int((propagated_vals == "false").sum())
    n_prop = int((propagated_vals == "true").sum())
    assert n_direct > 0, f"propagated call returned zero direct rows — source can't distinguish per-row direct/propagated"
    assert n_prop > 0, f"propagated call returned zero propagated rows — propagation not working"


def test_tp53_annotations_have_evidence_codes(require_any_cache):
    found = _find_artifact(require_any_cache, "annotations_of_gene", "TP53")
    if found is None:
        pytest.skip("annotations_of_gene for TP53 not in cache")
    tsv, _meta = found
    df = pd.read_csv(tsv, sep="\t", dtype="string")
    assert len(df) > 50, f"TP53 should have many annotations; got {len(df)}"
    codes = set(df["evidence_code"].dropna())
    assert codes, "no evidence codes present in TP53 annotations"
    # TP53 is well-studied — should have experimental codes (IDA/EXP) not just IEA.
    experimental = {"IDA", "EXP", "IMP", "IPI", "IGI", "ISS"}
    has_experimental = bool(codes & experimental)
    assert has_experimental, (
        f"TP53 has no experimental evidence codes; got: {sorted(codes)}"
    )


def test_tp53_annotations_span_all_three_aspects(require_any_cache):
    """TP53 is annotated to BP, MF, AND CC. If only one aspect appears, the
    parser likely dropped fields."""
    found = _find_artifact(require_any_cache, "annotations_of_gene", "TP53")
    if found is None:
        pytest.skip()
    tsv, _meta = found
    df = pd.read_csv(tsv, sep="\t", dtype="string")
    aspects = set(df["term_aspect"].dropna())
    expected = {"biological_process", "molecular_function", "cellular_component"}
    missing = expected - aspects
    assert not missing, f"TP53 annotations missing aspects: {missing}; got {aspects}"


def test_taxon_id_matches_species(require_any_cache):
    """Meta's taxon_id must match species."""
    bad = []
    for _tsv, meta_path, meta in require_any_cache:
        if meta.get("species") == "human" and meta.get("taxon_id") != 9606:
            bad.append((meta_path.name, "human", meta.get("taxon_id")))
        if meta.get("species") == "mouse" and meta.get("taxon_id") != 10090:
            bad.append((meta_path.name, "mouse", meta.get("taxon_id")))
    assert not bad, f"taxon_id/species mismatches: {bad}"
