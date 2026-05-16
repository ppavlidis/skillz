"""Known-genes sanity tests — catches structure-right-semantics-wrong bugs.

A TSV can be well-formed and the right size but contain entirely the wrong
data (e.g. a column-mapping mistake that reads the wrong field into
`symbol`). The format/schema tests can't catch this. A small hand-curated
list of canonical members, checked against each cached set that should
contain them, is a quick semantic gate.

These are intentionally conservative: only well-known, widely-cited genes
whose membership is not in dispute. If a test here fails, something is
likely deeply wrong with the fetcher.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

# Canonical human TFs that appear in essentially every TF list ever
# published — used to sanity-check tfs_human_lambert2018 et al.
KNOWN_HUMAN_TFS = {
    "TP53",   # tumor suppressor
    "MYC",    # bHLH TF, c-Myc
    "GATA3",  # GATA-family
    "FOXP3",  # forkhead, Treg master regulator
    "JUN",    # AP-1
    "NANOG",  # pluripotency
}

# Canonical human protein-coding genes used to sanity-check protein-coding sets.
KNOWN_HUMAN_PROTEIN_CODING = {
    "TP53",
    "MYC",
    "ACTB",   # beta-actin, ubiquitous
    "GAPDH",  # housekeeper
    "INS",    # insulin
    "HBB",    # hemoglobin beta
}

# Canonical mouse protein-coding genes. Mouse symbols are conventionally
# Title-cased (Actb, not ACTB); we uppercase before comparing so the check
# is robust to case.
KNOWN_MOUSE_PROTEIN_CODING = {
    "TRP53",   # p53 in mouse (note: orthologs use "Trp53")
    "MYC",
    "ACTB",
    "GAPDH",
    "INS1",    # mouse has Ins1 and Ins2; pick one
    "HBB-B1",  # mouse hemoglobin beta — varies by registry; this is the MGI canonical
}


def _read_symbols(tsv: Path) -> set[str]:
    df = pd.read_csv(tsv, sep="\t", usecols=["symbol"], dtype="string")
    return set(df["symbol"].dropna().str.upper().tolist())


def _find_set(cached_artifacts, set_name_substring: str) -> Path | None:
    for tsv, _meta_path, meta in cached_artifacts:
        if meta.get("set") == set_name_substring:
            return tsv
    return None


def test_lambert_contains_known_tfs(require_any_cache):
    tsv = _find_set(require_any_cache, "tfs_human_lambert2018")
    if tsv is None:
        pytest.skip("tfs_human_lambert2018 not in cache; fetch it to enable this test")
    symbols = _read_symbols(tsv)
    missing = KNOWN_HUMAN_TFS - symbols
    assert not missing, (
        f"tfs_human_lambert2018 is missing canonical TFs: {sorted(missing)}\n"
        f"  if even one of these is missing, the symbol column may be misaligned"
    )


def test_protein_coding_human_contains_known_genes(require_any_cache):
    tsv = _find_set(require_any_cache, "protein_coding_human")
    if tsv is None:
        pytest.skip("protein_coding_human not in cache")
    symbols = _read_symbols(tsv)
    missing = KNOWN_HUMAN_PROTEIN_CODING - symbols
    assert not missing, f"protein_coding_human missing canonical genes: {sorted(missing)}"


def test_protein_coding_human_strict_contains_known_genes(require_any_cache):
    tsv = _find_set(require_any_cache, "protein_coding_human_strict")
    if tsv is None:
        pytest.skip("protein_coding_human_strict not in cache")
    symbols = _read_symbols(tsv)
    # The strict set is the intersection of Ensembl + HGNC + GENCODE; canonical
    # protein-coding genes should be in all three.
    missing = KNOWN_HUMAN_PROTEIN_CODING - symbols
    assert not missing, (
        f"protein_coding_human_strict (Ensembl ∩ HGNC ∩ GENCODE) is missing "
        f"canonical genes: {sorted(missing)}. If TP53/ACTB/INS aren't in the "
        f"three-way intersection, something is very wrong."
    )


@pytest.mark.parametrize(
    "set_name",
    ["protein_coding_mouse", "protein_coding_mouse_mgi", "protein_coding_mouse_gencode"],
)
def test_mouse_protein_coding_contains_canonical_genes(require_any_cache, set_name):
    """Each individual mouse authority must contain the canonical housekeepers.

    If any of Actb/Gapdh/Myc is missing from a per-authority set, that
    authority's parser is almost certainly broken.
    """
    tsv = _find_set(require_any_cache, set_name)
    if tsv is None:
        pytest.skip(f"{set_name} not in cache")
    symbols = _read_symbols(tsv)
    # Use a smaller, more robust subset for per-authority checks — Ins1 and
    # Hbb-b1 have authority-specific naming quirks.
    canon = {"ACTB", "GAPDH", "MYC", "TRP53"}
    missing = canon - symbols
    assert not missing, (
        f"{set_name} is missing canonical mouse genes: {sorted(missing)} — "
        f"parser likely broken"
    )


def test_protein_coding_mouse_strict_contains_canonical_genes(require_any_cache):
    tsv = _find_set(require_any_cache, "protein_coding_mouse_strict")
    if tsv is None:
        pytest.skip("protein_coding_mouse_strict not in cache")
    symbols = _read_symbols(tsv)
    canon = {"ACTB", "GAPDH", "MYC", "TRP53"}
    missing = canon - symbols
    assert not missing, (
        f"protein_coding_mouse_strict (Ensembl ∩ MGI ∩ GENCODE) is missing "
        f"canonical mouse genes: {sorted(missing)}"
    )
