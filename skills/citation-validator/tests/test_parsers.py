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
    _clean_latex,
    _extract_doi,
    parse_bibtex,
    parse_latex,
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


# ---------------------------------------------------------------------------
# LaTeX parser
# ---------------------------------------------------------------------------

def test_clean_latex_textit():
    assert _clean_latex(r"\textit{Genome Biology}") == "Genome Biology"


def test_clean_latex_emph_textbf_nested():
    out = _clean_latex(r"\textbf{\textit{Hello}} world")
    assert "Hello" in out and "world" in out
    assert "\\" not in out


def test_clean_latex_accents():
    out = _clean_latex(r'\"Ostlund and Caf\'e')
    assert "Östlund" in out
    assert "Café" in out


def test_clean_latex_href_keeps_visible_text():
    out = _clean_latex(r"\href{https://doi.org/10.1/x}{doi:10.1/x}")
    assert "10.1/x" in out


def test_clean_latex_url_macro():
    out = _clean_latex(r"\url{https://doi.org/10.5/y}")
    assert "10.5/y" in out


def test_clean_latex_dashes_and_tildes():
    out = _clean_latex(r"pp.~10--20, vol.~3---4")
    assert "10-20" in out
    assert "3-4" in out
    # ~ should become a space, not be left in the output
    assert "~" not in out


def test_parse_latex_three_bibitems():
    text = (FIXTURES / "sample.tex").read_text()
    cits = parse_latex(text)
    assert len(cits) == 3
    keys = [c["key"] for c in cits]
    assert keys == ["love2014", "smith2020", "nodoi2019"]


def test_parse_latex_extracts_doi():
    text = (FIXTURES / "sample.tex").read_text()
    cits = parse_latex(text)
    by_key = {c["key"]: c for c in cits}
    assert by_key["love2014"]["doi"] == "10.1186/s13059-014-0550-8"
    assert by_key["smith2020"]["doi"] == "10.1234/example.2020.123"


def test_parse_latex_no_doi_when_absent():
    text = (FIXTURES / "sample.tex").read_text()
    cits = parse_latex(text)
    by_key = {c["key"]: c for c in cits}
    assert by_key["nodoi2019"]["doi"] is None


def test_parse_latex_year_extracted():
    text = (FIXTURES / "sample.tex").read_text()
    cits = parse_latex(text)
    by_key = {c["key"]: c for c in cits}
    assert by_key["love2014"]["year"] == 2014
    assert by_key["smith2020"]["year"] == 2020
    assert by_key["nodoi2019"]["year"] == 2019


def test_parse_latex_entry_type_marked():
    text = (FIXTURES / "sample.tex").read_text()
    cits = parse_latex(text)
    assert all(c["entry_type"] == "latex_bibitem" for c in cits)


def test_parse_latex_bbl_no_environment_wrapper():
    """A .bbl file with the \\begin/\\end wrapper should also parse."""
    text = (FIXTURES / "sample.bbl").read_text()
    cits = parse_latex(text)
    assert len(cits) == 1
    assert cits[0]["key"] == "love2014"
    assert cits[0]["doi"] == "10.1186/s13059-014-0550-8"


def test_parse_latex_bbl_without_environment():
    """A bare \\bibitem stream (some .bbl variants) should still parse."""
    bare = (
        r"\bibitem{a2020} Author, A. (2020). Title A. "
        r"\textit{Journal}, 1:1. doi:10.1234/a.2020." "\n\n"
        r"\bibitem{b2021} Author, B. (2021). Title B. "
        r"\textit{Journal}, 2:2. doi:10.5678/b.2021."
    )
    cits = parse_latex(bare)
    assert [c["key"] for c in cits] == ["a2020", "b2021"]
    assert cits[0]["doi"] == "10.1234/a.2020"
    assert cits[1]["doi"] == "10.5678/b.2021"


def test_parse_latex_empty_returns_empty():
    assert parse_latex("") == []
    assert parse_latex(r"\documentclass{article}\begin{document}\end{document}") == []


# ---------------------------------------------------------------------------
# Real-world Zotero (Better BibTeX) export — covers the edge cases the
# regex / bibtexparser path sees in practice but the synthetic fixture
# doesn't (latex-escaped Unicode in author, {{double braces}} for case
# preservation, &amp; HTML entity, no-DOI @misc entries).
# ---------------------------------------------------------------------------

def test_bibtex_zotero_export_parses_all_entries():
    text = (FIXTURES / "zotero_export.bib").read_text()
    cits = parse_bibtex(text)
    assert len(cits) == 4
    keys = [c["key"] for c in cits]
    assert "ahlmannEltzeDeepLearningGene2025" in keys
    assert "beurelGlycogenSynthaseKinase32015" in keys


def test_bibtex_zotero_export_extracts_real_dois():
    text = (FIXTURES / "zotero_export.bib").read_text()
    by_key = {c["key"]: c for c in parse_bibtex(text)}
    assert by_key["ahlmannEltzeDeepLearningGene2025"]["doi"] == "10.1038/s41592-025-02772-6"
    assert by_key["beurelGlycogenSynthaseKinase32015"]["doi"] == "10.1016/j.pharmthera.2014.11.016"


def test_bibtex_zotero_export_handles_missing_doi():
    text = (FIXTURES / "zotero_export.bib").read_text()
    by_key = {c["key"]: c for c in parse_bibtex(text)}
    assert by_key["ActingEthicalImperfect2026"]["doi"] is None
    assert by_key["202526InstituteAI"]["doi"] is None


def test_bibtex_zotero_export_year_extracted():
    text = (FIXTURES / "zotero_export.bib").read_text()
    by_key = {c["key"]: c for c in parse_bibtex(text)}
    assert by_key["ahlmannEltzeDeepLearningGene2025"]["year"] == 2025
    assert by_key["beurelGlycogenSynthaseKinase32015"]["year"] == 2015


# ---------------------------------------------------------------------------
# .docx parser — generated on the fly so we don't ship binary fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def docx_fixture(tmp_path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_paragraph(
        "1. Love MI, Huber W, Anders S (2014). Moderated estimation of "
        "fold change and dispersion for RNA-seq data with DESeq2. "
        "Genome Biology 15(12):550. doi:10.1186/s13059-014-0550-8"
    )
    doc.add_paragraph(
        "2. Brown K (2019). Title without a DOI. "
        "Journal of Hard Cases 1(1):1-5."
    )
    path = tmp_path / "sample.docx"
    doc.save(str(path))
    return path


def test_docx_extracts_paragraphs(docx_fixture):
    import _docx
    text = _docx.extract_text(docx_fixture)
    assert "Love MI" in text
    assert "Brown K" in text
    # Paragraphs are double-newline separated for parse_text's block splitter.
    assert "\n\n" in text


def test_docx_round_trip_through_parse_text(docx_fixture):
    import _docx
    text = _docx.extract_text(docx_fixture)
    cits = parse_text(text)
    assert len(cits) == 2
    dois = [c["doi"] for c in cits]
    assert "10.1186/s13059-014-0550-8" in dois
    # Second has no DOI
    assert None in dois


def test_docx_missing_python_docx_raises_runtime_error(monkeypatch, tmp_path):
    """If python-docx isn't installed, the helper must raise loudly,
    not silently return empty text."""
    import _docx
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "docx":
            raise ImportError("simulated missing python-docx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    fake_path = tmp_path / "fake.docx"
    fake_path.write_bytes(b"not really a docx")
    with pytest.raises(RuntimeError, match="python-docx"):
        _docx.extract_text(fake_path)
