"""Unit tests for term ID ↔ URI conversion and ontology inference.

No network required. Covers OBO PURL terms, non-OBO terms (EFO), unknown
prefixes, and the infer_ontology() graceful-fallback path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from sources._common import (
    TermFormatError,
    infer_ontology,
    is_compact,
    is_uri,
    to_compact,
    to_uri,
)


# ---------------------------------------------------------------------------
# to_uri — OBO terms
# ---------------------------------------------------------------------------

def test_to_uri_go():
    assert to_uri("GO:0006915") == "http://purl.obolibrary.org/obo/GO_0006915"

def test_to_uri_mondo():
    assert to_uri("MONDO:0000408") == "http://purl.obolibrary.org/obo/MONDO_0000408"

def test_to_uri_passthrough_uri():
    uri = "http://purl.obolibrary.org/obo/GO_0006915"
    assert to_uri(uri) == uri

def test_to_uri_raises_on_garbage():
    with pytest.raises(TermFormatError):
        to_uri("not-a-term")


# ---------------------------------------------------------------------------
# to_uri — non-OBO terms (EFO)
# ---------------------------------------------------------------------------

def test_to_uri_efo_uses_ebi_uri():
    uri = to_uri("EFO:0000001")
    assert uri.startswith("http://www.ebi.ac.uk/efo/EFO_")
    assert "0000001" in uri

def test_to_uri_efo_not_obo_purl():
    uri = to_uri("EFO:0000001")
    assert "purl.obolibrary.org" not in uri

def test_to_uri_efo_zero_padded():
    uri = to_uri("EFO:0004530")
    assert uri == "http://www.ebi.ac.uk/efo/EFO_0004530"


# ---------------------------------------------------------------------------
# to_compact — OBO URIs
# ---------------------------------------------------------------------------

def test_to_compact_obo_uri():
    assert to_compact("http://purl.obolibrary.org/obo/GO_0006915") == "GO:0006915"

def test_to_compact_passthrough_compact():
    assert to_compact("GO:0006915") == "GO:0006915"

def test_to_compact_raises_unknown_uri():
    with pytest.raises(TermFormatError):
        to_compact("http://example.com/unknown/ZZZZ_9999")


# ---------------------------------------------------------------------------
# to_compact — EFO URIs
# ---------------------------------------------------------------------------

def test_to_compact_efo_uri():
    assert to_compact("http://www.ebi.ac.uk/efo/EFO_0000001") == "EFO:0000001"

def test_to_compact_efo_https():
    assert to_compact("https://www.ebi.ac.uk/efo/EFO_0004530") == "EFO:0004530"

def test_to_uri_to_compact_efo_roundtrip():
    original = "EFO:0000001"
    assert to_compact(to_uri(original)) == original


# ---------------------------------------------------------------------------
# infer_ontology
# ---------------------------------------------------------------------------

def test_infer_ontology_go():
    assert infer_ontology("GO:0006915") == "go"

def test_infer_ontology_hp():
    assert infer_ontology("HP:0001234") == "hp"

def test_infer_ontology_efo():
    assert infer_ontology("EFO:0000001") == "efo"

def test_infer_ontology_from_obo_uri():
    assert infer_ontology("http://purl.obolibrary.org/obo/MONDO_0000408") == "mondo"

def test_infer_ontology_from_efo_uri():
    assert infer_ontology("http://www.ebi.ac.uk/efo/EFO_0000001") == "efo"

def test_infer_ontology_unknown_prefix_falls_back(capsys):
    """Unknown prefix should warn and return prefix.lower(), not die."""
    result = infer_ontology("ZZZZ:0000001")
    assert result == "zzzz"
    captured = capsys.readouterr()
    assert "zzzz" in captured.err.lower() or "ZZZZ" in captured.err


# ---------------------------------------------------------------------------
# is_compact / is_uri helpers
# ---------------------------------------------------------------------------

def test_is_compact_true():
    assert is_compact("GO:0006915")
    assert is_compact("EFO:0000001")

def test_is_compact_false_for_uri():
    assert not is_compact("http://purl.obolibrary.org/obo/GO_0006915")

def test_is_uri_true():
    assert is_uri("http://purl.obolibrary.org/obo/GO_0006915")
    assert is_uri("https://www.ebi.ac.uk/efo/EFO_0000001")

def test_is_uri_false_for_compact():
    assert not is_uri("GO:0006915")
