"""Tests for comparison logic and status assignment (no network required).

Coverage:
- compare(): VERIFIED, DOI_NOT_FOUND, METADATA_MISMATCH, SUSPICIOUS,
             VERIFIED_NO_DOI, NOT_FOUND
- flags: TITLE_MISMATCH, YEAR_MISMATCH, AUTHOR_MISMATCH, DOI_NOT_FOUND
- year tolerance (±1)
- author matching edge cases
- confidence values within [0, 1]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from validate import compare, _year_ok, _author_ok


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stated(title=None, doi=None, year=None, author=None):
    return {"title": title, "doi": doi, "year": year, "first_author": author}


def _found(title=None, doi=None, year=None, author=None):
    return {"title": title, "doi": doi, "year": year, "first_author": author,
            "source": "crossref"}


# ---------------------------------------------------------------------------
# _year_ok
# ---------------------------------------------------------------------------


def test_year_ok_exact():
    assert _year_ok(2011, 2011) is True


def test_year_ok_off_by_one():
    assert _year_ok(2011, 2012) is True


def test_year_ok_off_by_two():
    assert _year_ok(2011, 2013) is False


def test_year_ok_none_stated():
    assert _year_ok(None, 2011) is None


def test_year_ok_none_crossref():
    assert _year_ok(2011, None) is None


# ---------------------------------------------------------------------------
# _author_ok
# ---------------------------------------------------------------------------


def test_author_ok_exact_family():
    assert _author_ok("Gillis", "Gillis") is True


def test_author_ok_case_insensitive():
    assert _author_ok("gillis", "Gillis") is True


def test_author_ok_prefix_match():
    assert _author_ok("Gil", "Gillis") is True


def test_author_ok_unrelated():
    assert _author_ok("Smith", "Pavlidis") is False


def test_author_ok_none():
    assert _author_ok(None, "Gillis") is None
    assert _author_ok("Gillis", None) is None


# ---------------------------------------------------------------------------
# compare() — DOI given
# ---------------------------------------------------------------------------


def test_verified_exact_match():
    stated = _stated(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2011, author="Gillis",
    )
    found = _found(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2011, author="Gillis",
        doi="10.1371/journal.pone.0017258",
    )
    result = compare(stated, found, doi_was_given=True)
    assert result["status"] == "VERIFIED"
    assert result["flags"] == []
    assert result["confidence"] > 0.85


def test_verified_minor_title_difference():
    stated = _stated(
        title="Moderated estimation of fold change and dispersion for RNA-seq data",
        year=2014, author="Love",
    )
    found = _found(
        title="Moderated estimation of fold change and dispersion for RNA-seq data with DESeq2",
        year=2014, author="Love",
    )
    result = compare(stated, found, doi_was_given=True)
    # Minor title difference — may be VERIFIED or SUSPICIOUS; should not be METADATA_MISMATCH
    assert result["status"] in {"VERIFIED", "SUSPICIOUS"}


def test_doi_not_found():
    result = compare(_stated(doi="10.0000/fake"), None, doi_was_given=True)
    assert result["status"] == "DOI_NOT_FOUND"
    assert "DOI_NOT_FOUND" in result["flags"]
    assert result["confidence"] > 0.90


def test_metadata_mismatch_completely_different_title():
    stated = _stated(
        title="A Completely Wrong Title That Does Not Match The Real Paper At All",
        year=2011,
    )
    found = _found(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2011,
    )
    result = compare(stated, found, doi_was_given=True)
    assert result["status"] == "METADATA_MISMATCH"
    assert "TITLE_MISMATCH" in result["flags"]


def test_metadata_mismatch_year_flag():
    stated = _stated(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2005,  # wrong year
    )
    found = _found(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2011,
    )
    result = compare(stated, found, doi_was_given=True)
    assert "YEAR_MISMATCH" in result["flags"]


def test_author_mismatch_flag():
    stated = _stated(
        title="The Impact of Multifunctional Genes",
        year=2011, author="Completely_Wrong",
    )
    found = _found(
        title="The Impact of Multifunctional Genes",
        year=2011, author="Gillis",
    )
    result = compare(stated, found, doi_was_given=True)
    assert "AUTHOR_MISMATCH" in result["flags"]


def test_verified_with_year_tolerance():
    stated = _stated(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2012,  # off by 1 (preprint→published)
    )
    found = _found(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2011,
    )
    result = compare(stated, found, doi_was_given=True)
    # Off-by-one year should not prevent VERIFIED
    assert result["status"] in {"VERIFIED", "SUSPICIOUS"}
    assert "YEAR_MISMATCH" not in result["flags"]


# ---------------------------------------------------------------------------
# compare() — no DOI given
# ---------------------------------------------------------------------------


def test_verified_no_doi():
    stated = _stated(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2011,
    )
    found = _found(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2011,
        doi="10.1371/journal.pone.0017258",
    )
    result = compare(stated, found, doi_was_given=False)
    assert result["status"] == "VERIFIED_NO_DOI"


def test_not_found_no_doi_no_result():
    result = compare(_stated(title="Some Title"), None, doi_was_given=False)
    assert result["status"] == "NOT_FOUND"
    assert "NO_MATCH_FOUND" in result["flags"]


def test_suspicious_no_doi_weak_match():
    stated = _stated(title="Impact of Genes on Analysis", year=2011)
    found = _found(
        title="The Impact of Multifunctional Genes on Guilt by Association Analysis",
        year=2011,
    )
    result = compare(stated, found, doi_was_given=False)
    # Partial title overlap — should be SUSPICIOUS, not VERIFIED_NO_DOI
    assert result["status"] in {"SUSPICIOUS", "NOT_FOUND"}


# ---------------------------------------------------------------------------
# Confidence always in [0, 1]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_setup", [
    ("doi_found_match", True, True),
    ("doi_found_mismatch", True, False),
    ("doi_not_found", True, None),
    ("no_doi_match", False, True),
    ("no_doi_no_result", False, None),
])
def test_confidence_in_unit_interval(status_setup):
    name, doi_given, has_result = status_setup
    if has_result is True:
        found = _found(title="Same Title", year=2020, author="Smith")
        stated = _stated(title="Same Title" if doi_given else "Different Title",
                         year=2020)
    elif has_result is False:
        found = _found(title="Completely Different Title No Match", year=1900)
        stated = _stated(title="Original Title", year=2020)
    else:
        found = None
        stated = _stated(title="Title", year=2020)

    result = compare(stated, found, doi_was_given=doi_given)
    assert 0.0 <= result["confidence"] <= 1.0, f"bad confidence for {name}: {result['confidence']}"
