"""Network integration tests — query the live CrossRef API.

Skipped by default. Run with:
    pytest tests/test_network.py --network

Uses two known stable DOIs plus a fixture guaranteed to be unregistered.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _crossref
from validate import parse_bibtex, validate_citation

FIXTURES = Path(__file__).parent / "fixtures"

# Stable DOI for Gillis & Pavlidis 2011
REAL_DOI = "10.1371/journal.pone.0017258"
# This DOI is permanently reserved for testing (never assigned)
FAKE_DOI = "10.0000/test-fixture-nonexistent.2023.99999"


# ---------------------------------------------------------------------------
# _crossref.lookup_doi
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_lookup_real_doi():
    result = _crossref.lookup_doi(REAL_DOI, refresh=True)
    assert result is not None
    assert result["doi"].lower() == REAL_DOI.lower()
    assert result["year"] == 2011
    assert result["title"] is not None
    assert "multifunctional" in result["title"].lower() or "Multifunctional" in result["title"]


@pytest.mark.network
def test_lookup_fake_doi_returns_none():
    result = _crossref.lookup_doi(FAKE_DOI, refresh=True)
    assert result is None


@pytest.mark.network
def test_lookup_doi_first_author():
    result = _crossref.lookup_doi(REAL_DOI, refresh=True)
    assert result is not None
    assert result["first_author"] is not None
    assert "Gillis" in result["first_author"] or "gillis" in result["first_author"].lower()


@pytest.mark.network
def test_search_by_title_finds_known_paper():
    results = _crossref.search_by_title(
        "The Impact of Multifunctional Genes on Guilt by Association Analysis",
        author="Gillis",
        year=2011,
        refresh=True,
    )
    assert len(results) > 0
    titles = [r.get("title", "") for r in results]
    assert any("multifunctional" in (t or "").lower() for t in titles)


# ---------------------------------------------------------------------------
# validate_citation
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_validate_real_citation_verified():
    citation = {
        "key": "gillis2011",
        "title": "The Impact of Multifunctional Genes on \"Guilt by Association\" Analysis",
        "doi": REAL_DOI,
        "year": 2011,
        "first_author": "Gillis",
    }
    result = validate_citation(citation, refresh=True)
    assert result["status"] == "VERIFIED"
    assert result["crossref_doi"] is not None


@pytest.mark.network
def test_validate_fake_doi_not_found():
    citation = {
        "key": "fake2023",
        "title": "A Completely Fabricated Study",
        "doi": FAKE_DOI,
        "year": 2023,
        "first_author": "Nonexistent",
    }
    result = validate_citation(citation, refresh=True)
    assert result["status"] == "DOI_NOT_FOUND"


@pytest.mark.network
def test_validate_metadata_mismatch():
    citation = {
        "key": "mismatch",
        "title": "A Completely Wrong Title That Does Not Match The Real Paper At All",
        "doi": REAL_DOI,
        "year": 2011,
        "first_author": "Gillis",
    }
    result = validate_citation(citation, refresh=True)
    assert result["status"] == "METADATA_MISMATCH"
    assert "TITLE_MISMATCH" in result["flags"]


@pytest.mark.network
def test_validate_no_doi_finds_deseq2():
    citation = {
        "key": "love2014",
        "title": "Moderated estimation of fold change and dispersion for RNA-seq data with DESeq2",
        "doi": None,
        "year": 2014,
        "first_author": "Love",
    }
    result = validate_citation(citation, refresh=True)
    assert result["status"] in {"VERIFIED_NO_DOI", "SUSPICIOUS"}
    if result["status"] == "VERIFIED_NO_DOI":
        assert result["crossref_doi"] is not None


# ---------------------------------------------------------------------------
# End-to-end from fixture file
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_validate_bib_fixture():
    cits = parse_bibtex((FIXTURES / "sample.bib").read_text())
    assert len(cits) == 4
    results = [validate_citation(c, refresh=True) for c in cits]

    by_key = {r["key"]: r for r in results}
    assert by_key["gillis2011"]["status"] == "VERIFIED"
    assert by_key["fake2023"]["status"] == "DOI_NOT_FOUND"
    assert by_key["mismatch2011"]["status"] == "METADATA_MISMATCH"
