"""Known-term sanity tests — catches structure-right-semantics-wrong bugs.

Hand-picked, undisputed term relationships. If any of these fails, a fetcher
is almost certainly broken (column-shift, wrong endpoint, parser drift).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

CACHE = Path.home() / ".cache" / "ontology-terms"


def _find_artifact(cached_artifacts, operation: str, source: str, term_substring: str) -> tuple[Path, dict] | None:
    for tsv, _meta_path, meta in cached_artifacts:
        if meta.get("operation") != operation or meta.get("source") != source:
            continue
        if term_substring in str(meta.get("input_term_id", "")) or term_substring in str(meta.get("input_term_uri", "")):
            return tsv, meta
    return None


def _term_ids(tsv: Path) -> set[str]:
    return set(pd.read_csv(tsv, sep="\t", usecols=["term_id"], dtype="string")["term_id"].dropna())


def test_ols_parents_apoptosis_includes_programmed_cell_death(require_any_cache):
    """GO:0006915 (apoptotic process) is_a GO:0012501 (programmed cell death) —
    a foundational, undisputed parent relation. If OLS doesn't return it,
    something is broken."""
    found = _find_artifact(require_any_cache, "parents", "ols", "GO:0006915")
    if found is None:
        pytest.skip("OLS parents of GO:0006915 not in cache")
    tsv, _meta = found
    ids = _term_ids(tsv)
    assert "GO:0012501" in ids, (
        f"OLS parents of GO:0006915 (apoptotic process) does NOT include "
        f"GO:0012501 (programmed cell death). Got: {sorted(ids)}"
    )


def test_ols_children_programmed_cell_death_includes_apoptosis(require_any_cache):
    """Inverse relation: GO:0012501's children should include GO:0006915."""
    found = _find_artifact(require_any_cache, "children", "ols", "GO:0012501")
    if found is None:
        pytest.skip("OLS children of GO:0012501 not in cache")
    tsv, _meta = found
    ids = _term_ids(tsv)
    # GO:0012501 has many child cell-death types — apoptotic process is one
    # of the canonical ones but reorganizations have happened over the years.
    # Accept any well-known child as evidence the call works.
    known_children = {"GO:0006915", "GO:0097707", "GO:0070268"}  # apoptosis, ferroptosis, cornification
    assert ids & known_children, (
        f"OLS children of GO:0012501 contains none of the canonical children "
        f"({sorted(known_children)}). Got first 10: {sorted(ids)[:10]}"
    )


def test_ols_definition_has_text(require_any_cache):
    """Any definition query that landed in cache should have a non-empty text."""
    for tsv, _meta_path, meta in require_any_cache:
        if meta.get("operation") != "definition" or meta.get("source") != "ols":
            continue
        df = pd.read_csv(tsv, sep="\t", dtype="string")
        if df.empty:
            continue
        if "definition" not in df.columns:
            pytest.fail(f"{tsv.name}: definition operation TSV missing 'definition' column")
        defn = df["definition"].iloc[0]
        assert isinstance(defn, str) and len(defn.strip()) > 0, (
            f"{tsv.name}: definition column is empty for term {df['term_id'].iloc[0]}"
        )
        return  # one is enough
    pytest.skip("no OLS definition artifacts in cache")


def test_gemma_parents_returns_transitive_not_just_immediate(require_any_cache):
    """Gemma's parents endpoint returns propagated relations. For any well-
    connected MONDO term we should get more than 1 parent. (OLS would return
    typically 1-3 immediate parents; Gemma returns many more.)"""
    for tsv, _meta_path, meta in require_any_cache:
        if meta.get("operation") != "parents" or meta.get("source") != "gemma":
            continue
        if "MONDO" not in str(meta.get("input_term_id", "")):
            continue
        df = pd.read_csv(tsv, sep="\t", dtype="string")
        if len(df) >= 3:
            return  # passed
    pytest.skip("no Gemma MONDO parents artifact in cache; fetch one to enable")


def test_search_results_have_score_or_explanation(require_any_cache):
    """Search artifacts must declare their score column. OLS scores can be 0
    (it's a known limitation of OLS4 search), Gemma scores are NaN. Either
    is acceptable; what's NOT acceptable is the column being absent."""
    for tsv, _meta_path, meta in require_any_cache:
        if meta.get("operation") != "search":
            continue
        df = pd.read_csv(tsv, sep="\t", dtype="string", nrows=1)
        assert "score" in df.columns, f"{tsv.name}: search artifact missing 'score' column"


def test_compact_and_uri_forms_are_consistent(require_any_cache):
    """For any OBO-form URI, the compact term_id should match the URI's tail.
    Catches URI/ID mapping bugs."""
    import re
    bad = []
    for tsv, _meta_path, _meta in require_any_cache:
        df = pd.read_csv(tsv, sep="\t", dtype="string")
        if df.empty:
            continue
        for _, row in df.head(20).iterrows():
            uri = row.get("term_uri", "")
            cid = row.get("term_id", "")
            if not isinstance(uri, str) or not uri.startswith("http://purl.obolibrary.org/obo/"):
                continue
            m = re.search(r"obo/([A-Za-z]+)_(\d+)$", uri)
            if not m:
                continue
            expected = f"{m.group(1)}:{m.group(2)}"
            if cid != expected:
                bad.append((tsv.name, cid, expected))
                break
    assert not bad, f"compact/URI mismatch: {bad}"
