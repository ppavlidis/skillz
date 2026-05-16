"""Term ID and URI format tests.

Catches: column-shift bugs, wrong-column-read, malformed compact IDs in
the term_id column (which would break downstream joins).
"""

from __future__ import annotations

import re

import pandas as pd
import pytest

COMPACT_RE = re.compile(r"^[A-Za-z]+:\d+$")
URI_RE = re.compile(r"^https?://[A-Za-z0-9.\-/]+[A-Za-z]+[_:]\d+$")


def test_term_id_format(require_any_cache):
    """term_id should be either compact (PREFIX:digits) or, for non-OBO
    sources, an http URL. Anything else suggests a column misalignment."""
    bad = []
    for tsv, _meta_path, _meta in require_any_cache:
        df = pd.read_csv(tsv, sep="\t", dtype="string")
        if "term_id" not in df.columns or df.empty:
            continue
        for v in df["term_id"].dropna().head(50):
            if not (COMPACT_RE.match(v) or v.startswith("http")):
                bad.append((tsv.name, v))
                break
    assert not bad, f"term_id values not in expected form: {bad}"


def test_term_uri_format(require_any_cache):
    bad = []
    for tsv, _meta_path, _meta in require_any_cache:
        df = pd.read_csv(tsv, sep="\t", dtype="string")
        if "term_uri" not in df.columns or df.empty:
            continue
        for v in df["term_uri"].dropna().head(50):
            if v and not v.startswith("http"):
                bad.append((tsv.name, v))
                break
    assert not bad, f"term_uri values not URLs: {bad}"


def test_term_label_is_non_empty_for_known_ops(require_any_cache):
    """parents/children/definition should always populate term_label."""
    bad = []
    for tsv, _meta_path, meta in require_any_cache:
        if meta.get("operation") not in {"parents", "children", "definition"}:
            continue
        df = pd.read_csv(tsv, sep="\t", dtype="string")
        if df.empty:
            continue
        empty = df[df["term_label"].isna() | (df["term_label"].fillna("") == "")]
        if len(empty):
            bad.append((tsv.name, len(empty)))
    assert not bad, f"TSVs with missing term_label rows: {bad}"
