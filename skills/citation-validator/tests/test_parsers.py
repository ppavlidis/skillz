"""Tests for citation parsers and DOI normalization (no network required).

Coverage:
- BibTeX: DOI extraction, title, year, first_author, multiple entries,
          DOI-in-URL field, bibtexparser fallback compatibility
- Plain-text: DOI extraction, year, title heuristic, multiple entries
- DOI normalization: https:// prefix, doi: prefix, trailing punctuation
- title_similarity: exact, near-exact, unrelated
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from validate import (
    _clean_doi,
    _extract_doi,
    parse_bibtex,
    parse_text,
    title_similarity,
)

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# DOI normalisation
# ---------------------------------------------------------------------------


def test_clean_doi_bare():
    assert _clean_doi("10.1038/s41586-023-01234-5") == "10.1038/s41586-023-01234-5"


def test_clean_doi_https_prefix():
    assert _clean_doi("https://doi.org/10.1038/s41586-023-01234-5") == "10.1038/s41586-023-01234-5"


def test_clean_doi_dx_prefix():
    assert _clean_doi("http://dx.doi.org/10.1038/s41586-023-01234-5") == "10.1038/s41586-023-01234-5"


def test_clean_doi_doi_colon_prefix():
    assert _clean_doi("doi:10.1038/s41586-023-01234-5") == "10.1038/s41586-023-01234-5"


def test_clean_doi_trailing_period():
    assert _clean_doi("10.1038/nature12345.") == "10.1038/nature12345"


def test_clean_doi_trailing_paren():
    assert _clean_doi("10.1038/nature12345)") == "10.1038/nature12345"


def test_clean_doi_none():
    assert _clean_doi(None) is None


def test_clean_doi_non_doi_string():
    assert _clean_doi("not-a-doi") is None


def test_extract_doi_from_text():
    text = "See also doi:10.1371/journal.pone.0017258 for details."
    assert _extract_doi(text) == "10.1371/journal.pone.0017258"


def test_extract_doi_from_url_in_text():
    text = "Available at https://doi.org/10.1038/s41586-023-01234-5."
    doi = _extract_doi(text)
    assert doi is not None and doi.startswith("10.")


def test_extract_doi_none_when_absent():
    assert _extract_doi("No DOI here, just a reference.") is None


# ---------------------------------------------------------------------------
# parse_bibtex
# ---------------------------------------------------------------------------

SIMPLE_BIB = r"""
@article{smith2020,
  title   = {A Study of {Things}},
  author  = {Smith, John and Doe, Jane},
  year    = {2020},
  journal = {Nature},
  doi     = {10.1038/nature12345},
}
"""


def test_bibtex_key():
    cits = parse_bibtex(SIMPLE_BIB)
    assert len(cits) == 1
    assert cits[0]["key"] == "smith2020"


def test_bibtex_doi():
    cits = parse_bibtex(SIMPLE_BIB)
    assert cits[0]["doi"] == "10.1038/nature12345"


def test_bibtex_title():
    cits = parse_bibtex(SIMPLE_BIB)
    assert cits[0]["title"] is not None
    assert "Things" in cits[0]["title"] or "things" in cits[0]["title"].lower()


def test_bibtex_year():
    cits = parse_bibtex(SIMPLE_BIB)
    assert cits[0]["year"] == 2020


def test_bibtex_first_author():
    cits = parse_bibtex(SIMPLE_BIB)
    assert cits[0]["first_author"] == "Smith"


def test_bibtex_doi_in_url_field():
    bib = r"""
@article{urltest2021,
  title  = {Title},
  author = {Author, A},
  year   = {2021},
  url    = {https://doi.org/10.1371/journal.pone.0017258},
}
"""
    cits = parse_bibtex(bib)
    assert cits[0]["doi"] == "10.1371/journal.pone.0017258"


def test_bibtex_doi_https_normalized():
    bib = r"""
@article{norm2021,
  title  = {Title},
  author = {Author, A},
  year   = {2021},
  doi    = {https://doi.org/10.1038/nature12345},
}
"""
    cits = parse_bibtex(bib)
    assert cits[0]["doi"] == "10.1038/nature12345"


def test_bibtex_multiple_entries():
    bib = SIMPLE_BIB + r"""
@article{jones2019,
  title   = {Another Paper},
  author  = {Jones, Alice},
  year    = {2019},
  doi     = {10.1234/another},
  journal = {Science},
}
"""
    cits = parse_bibtex(bib)
    assert len(cits) == 2
    keys = {c["key"] for c in cits}
    assert "smith2020" in keys
    assert "jones2019" in keys


def test_bibtex_no_doi():
    bib = r"""
@article{nodoi2014,
  title   = {No DOI Paper},
  author  = {Love, Michael I and Huber, Wolfgang},
  year    = {2014},
  journal = {Genome Biology},
}
"""
    cits = parse_bibtex(bib)
    assert cits[0]["doi"] is None


def test_bibtex_first_author_given_family():
    bib = r"""
@article{given2020,
  author = {John Smith and Jane Doe},
  title  = {Test},
  year   = {2020},
}
"""
    cits = parse_bibtex(bib)
    # "John Smith" → last word = "Smith"
    assert cits[0]["first_author"] == "Smith"


def test_bibtex_fixture_file():
    cits = parse_bibtex((FIXTURES / "sample.bib").read_text())
    assert len(cits) == 4
    keys = {c["key"] for c in cits}
    assert "gillis2011" in keys
    assert "fake2023" in keys


def test_bibtex_fixture_real_doi():
    cits = parse_bibtex((FIXTURES / "sample.bib").read_text())
    real = next(c for c in cits if c["key"] == "gillis2011")
    assert real["doi"] == "10.1371/journal.pone.0017258"
    assert real["year"] == 2011


def test_bibtex_fixture_fake_doi():
    cits = parse_bibtex((FIXTURES / "sample.bib").read_text())
    fake = next(c for c in cits if c["key"] == "fake2023")
    assert fake["doi"] is not None
    assert "0000" in fake["doi"]


# ---------------------------------------------------------------------------
# parse_text
# ---------------------------------------------------------------------------

SIMPLE_TEXT = """1. Smith J (2020). A Study of Things. Nature, 10:123. doi:10.1038/nature12345

2. Jones A (2019). Another Paper. Science.
"""


def test_text_entry_count():
    cits = parse_text(SIMPLE_TEXT)
    assert len(cits) == 2


def test_text_doi_extracted():
    cits = parse_text(SIMPLE_TEXT)
    assert cits[0]["doi"] == "10.1038/nature12345"


def test_text_year_extracted():
    cits = parse_text(SIMPLE_TEXT)
    assert cits[0]["year"] == 2020


def test_text_no_doi():
    cits = parse_text(SIMPLE_TEXT)
    assert cits[1]["doi"] is None


def test_text_fixture_file():
    cits = parse_text((FIXTURES / "sample.txt").read_text())
    assert len(cits) == 3
    dois = [c["doi"] for c in cits if c["doi"]]
    assert any("0017258" in d for d in dois)


# ---------------------------------------------------------------------------
# title_similarity
# ---------------------------------------------------------------------------


def test_similarity_identical():
    assert title_similarity("The Quick Brown Fox", "The Quick Brown Fox") == 1.0


def test_similarity_case_insensitive():
    assert title_similarity("THE QUICK BROWN FOX", "the quick brown fox") == pytest.approx(1.0)


def test_similarity_minor_punctuation():
    s = title_similarity(
        "Guilt by Association Analysis",
        "Guilt-by-Association Analysis",
    )
    assert s > 0.85


def test_similarity_unrelated():
    s = title_similarity(
        "The Impact of Multifunctional Genes",
        "A Completely Fabricated Study on Imaginary Genomics",
    )
    assert s < 0.50


def test_similarity_none_safe():
    assert title_similarity(None, "anything") == 0.0
    assert title_similarity("anything", None) == 0.0
    assert title_similarity(None, None) == 0.0
