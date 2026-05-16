"""
Tests for pdf-extract.  Uses only synthetic fixtures — no network, no real PDFs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from extract import (
    extract_metadata,
    extract_text,
    extract_annotations,
    _sha256,
    _clean_doi,
    _extract_doi,
    _parse_pdf_date,
    _parse_page_spec,
)

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample.pdf"
ANNOTATED = FIXTURES / "annotated.pdf"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text())


# ---------------------------------------------------------------------------
# _clean_doi
# ---------------------------------------------------------------------------

def test_clean_doi_bare():
    assert _clean_doi("10.1371/journal.pone.0017258") == "10.1371/journal.pone.0017258"

def test_clean_doi_with_https():
    assert _clean_doi("https://doi.org/10.1371/journal.pone.0017258") == "10.1371/journal.pone.0017258"

def test_clean_doi_with_dx():
    assert _clean_doi("http://dx.doi.org/10.1186/s13059-014-0550-8") == "10.1186/s13059-014-0550-8"

def test_clean_doi_trailing_punct():
    assert _clean_doi("10.1371/journal.pone.0017258.") == "10.1371/journal.pone.0017258"

def test_clean_doi_journal_prefix_rejected():
    assert _clean_doi("10.1126/science") is None

def test_clean_doi_no_digit_in_suffix_rejected():
    assert _clean_doi("10.0000/fakesuffix") is None

def test_clean_doi_too_short_rejected():
    assert _clean_doi("10.1016/j") is None

def test_clean_doi_with_doi_prefix():
    assert _clean_doi("doi:10.1093/nar/gks1114") == "10.1093/nar/gks1114"


# ---------------------------------------------------------------------------
# _extract_doi
# ---------------------------------------------------------------------------

def test_extract_doi_from_text():
    text = "See Smith (2020) doi: 10.1371/journal.pone.0017258 for details."
    assert _extract_doi(text) == "10.1371/journal.pone.0017258"

def test_extract_doi_from_url():
    text = "Available at https://doi.org/10.1186/s13059-014-0550-8"
    assert _extract_doi(text) == "10.1186/s13059-014-0550-8"

def test_extract_doi_none_when_absent():
    assert _extract_doi("No DOI here.") is None

def test_extract_doi_skips_journal_prefix():
    assert _extract_doi("published in 10.1126/science somehow") is None


# ---------------------------------------------------------------------------
# _parse_pdf_date
# ---------------------------------------------------------------------------

def test_parse_pdf_date_standard():
    assert _parse_pdf_date("D:20240115120000Z") == "2024-01-15"

def test_parse_pdf_date_none():
    assert _parse_pdf_date(None) is None

def test_parse_pdf_date_no_match():
    assert _parse_pdf_date("unknown") is None


# ---------------------------------------------------------------------------
# _parse_page_spec
# ---------------------------------------------------------------------------

def test_page_spec_single():
    assert _parse_page_spec("3", 10) == {3}

def test_page_spec_range():
    assert _parse_page_spec("2-5", 10) == {2, 3, 4, 5}

def test_page_spec_list():
    assert _parse_page_spec("1,3,5", 10) == {1, 3, 5}

def test_page_spec_mixed():
    assert _parse_page_spec("1,3-5", 10) == {1, 3, 4, 5}

def test_page_spec_clamps_to_total():
    assert _parse_page_spec("8-12", 10) == {8, 9, 10}


# ---------------------------------------------------------------------------
# _sha256
# ---------------------------------------------------------------------------

def test_sha256_deterministic():
    h1 = _sha256(SAMPLE)
    h2 = _sha256(SAMPLE)
    assert h1 == h2
    assert len(h1) == 64

def test_sha256_differs_across_files():
    assert _sha256(SAMPLE) != _sha256(ANNOTATED)


# ---------------------------------------------------------------------------
# extract_metadata
# ---------------------------------------------------------------------------

def test_metadata_returns_dict():
    result = extract_metadata(SAMPLE)
    assert isinstance(result, dict)

def test_metadata_doi_extracted():
    result = extract_metadata(SAMPLE)
    assert result["doi"] == EXPECTED["sample_doi"]

def test_metadata_title():
    result = extract_metadata(SAMPLE)
    assert result["title"] is not None
    assert EXPECTED["sample_title"] in (result["title"] or "")

def test_metadata_n_pages():
    result = extract_metadata(SAMPLE)
    assert result["n_pages"] == EXPECTED["sample_n_pages"]

def test_metadata_has_sha256():
    result = extract_metadata(SAMPLE)
    assert len(result["input_sha256"]) == 64

def test_metadata_has_library():
    result = extract_metadata(SAMPLE)
    assert result["library"] in ("pymupdf", "pypdf")

def test_metadata_has_extracted_at():
    result = extract_metadata(SAMPLE)
    assert result["extracted_at"].endswith("Z")

def test_metadata_creation_date_parsed():
    result = extract_metadata(SAMPLE)
    assert result["created"] == "2024-01-15"


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------

def test_text_all_pages():
    result = extract_text(SAMPLE)
    assert len(result["pages"]) == EXPECTED["sample_n_pages"]

def test_text_page_numbers():
    result = extract_text(SAMPLE)
    assert result["pages"][0]["page"] == 1
    assert result["pages"][1]["page"] == 2

def test_text_content_nonempty():
    result = extract_text(SAMPLE)
    assert len(result["pages"][0]["text"]) > 20

def test_text_contains_doi():
    result = extract_text(SAMPLE)
    full = " ".join(p["text"] for p in result["pages"])
    assert EXPECTED["sample_doi"] in full

def test_text_page_filter_single():
    result = extract_text(SAMPLE, pages="1")
    assert len(result["pages"]) == 1
    assert result["pages"][0]["page"] == 1

def test_text_page_filter_range():
    result = extract_text(SAMPLE, pages="1-2")
    assert len(result["pages"]) == 2

def test_text_page_filter_out_of_range():
    result = extract_text(SAMPLE, pages="99")
    assert len(result["pages"]) == 0

def test_text_has_provenance():
    result = extract_text(SAMPLE)
    assert result["input_sha256"]
    assert result["library"]
    assert result["extracted_at"]

def test_text_json_format():
    result = extract_text(SAMPLE, fmt="json")
    assert result["format"] == "json"


# ---------------------------------------------------------------------------
# extract_annotations
# ---------------------------------------------------------------------------

def test_annotations_count():
    result = extract_annotations(ANNOTATED)
    assert result["n_annotations"] == EXPECTED["annotated_n_annotations"]

def test_annotations_list_length():
    result = extract_annotations(ANNOTATED)
    assert len(result["annotations"]) == EXPECTED["annotated_n_annotations"]

def test_annotations_page_numbers_valid():
    result = extract_annotations(ANNOTATED)
    for ann in result["annotations"]:
        assert ann["page"] >= 1

def test_annotations_types_known():
    result = extract_annotations(ANNOTATED)
    valid = {"Highlight", "Underline", "StrikeOut", "Squiggly", "Text",
             "FreeText", "Square", "Circle", "Line", "Ink"}
    for ann in result["annotations"]:
        assert ann["type"] in valid

def test_annotations_highlight_text():
    result = extract_annotations(ANNOTATED)
    highlights = [a for a in result["annotations"] if a["type"] == "Highlight"]
    assert len(highlights) >= 1
    text = highlights[0]["highlighted_text"] or ""
    assert "highlighted" in text.lower()

def test_annotations_sticky_note_content():
    result = extract_annotations(ANNOTATED)
    notes = [a for a in result["annotations"] if a["type"] == "Text"]
    assert len(notes) >= 1
    assert notes[0]["note"] is not None
    assert len(notes[0]["note"]) > 0

def test_annotations_has_rect():
    result = extract_annotations(ANNOTATED)
    for ann in result["annotations"]:
        assert isinstance(ann["rect"], list)
        assert len(ann["rect"]) == 4

def test_annotations_has_provenance():
    result = extract_annotations(ANNOTATED)
    assert result["input_sha256"]
    assert result["library"] == "pymupdf"
    assert result["extracted_at"]

def test_annotations_no_annotations_file():
    result = extract_annotations(SAMPLE)
    assert result["n_annotations"] == 0
    assert result["annotations"] == []


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

def test_cli_metadata(tmp_path):
    out = tmp_path / "out.json"
    from extract import main
    rc = main(["metadata", str(SAMPLE), "--out", str(out)])
    assert rc == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["doi"] == EXPECTED["sample_doi"]
    meta_path = tmp_path / "out.meta.json"
    assert meta_path.exists()

def test_cli_text_json(tmp_path):
    out = tmp_path / "out.json"
    from extract import main
    rc = main(["text", str(SAMPLE), "--out", str(out), "--format", "json"])
    assert rc == 0
    data = json.loads(out.read_text())
    assert "pages" in data

def test_cli_text_plain(tmp_path):
    out = tmp_path / "out.txt"
    from extract import main
    rc = main(["text", str(SAMPLE), "--out", str(out), "--format", "text"])
    assert rc == 0
    content = out.read_text()
    assert "page 1" in content

def test_cli_annotations(tmp_path):
    out = tmp_path / "out.json"
    from extract import main
    rc = main(["annotations", str(ANNOTATED), "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["n_annotations"] == EXPECTED["annotated_n_annotations"]

def test_cli_all(tmp_path):
    out = tmp_path / "out.extracted.json"
    from extract import main
    rc = main(["all", str(SAMPLE), "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert "metadata" in data
    assert "text" in data
    assert "annotations" in data

def test_cli_missing_file(tmp_path):
    from extract import main
    rc = main(["metadata", str(tmp_path / "nonexistent.pdf")])
    assert rc == 1
