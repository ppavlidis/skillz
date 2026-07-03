"""Live-fetch smoke test for the JASPAR fetcher (opt-in: --network).

This is the regeneration guarantee: it re-fetches `tfs_human_jaspar` from the
live JASPAR + Ensembl APIs into a temp dir and asserts the artifact is still
well-formed. If JASPAR or Ensembl change their API shape, this test fails loud
so we know the recipe needs updating — exactly what "we can regenerate these
lists later" requires.

Run: pytest tests/ --network
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

# TFs that indisputably have a JASPAR CORE profile (see test_known_genes).
KNOWN = {"CTCF", "TP53", "JUN", "MYC", "GATA3", "SOX2"}


@pytest.mark.network
def test_jaspar_human_regenerates(tmp_path):
    out = tmp_path / "tfs_human_jaspar.tsv"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "fetch.py"), "tfs_human_jaspar", "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"fetch failed:\n{proc.stderr}"
    assert out.exists(), "no TSV written"

    df = pd.read_csv(out, sep="\t", dtype="string")
    # Standard schema + JASPAR extras.
    for col in ("ensembl_id", "symbol", "entrez_id", "species", "source",
                "jaspar_matrix_ids", "n_jaspar_motifs"):
        assert col in df.columns, f"missing column {col!r}"
    assert len(df) > 500, f"suspiciously few human JASPAR genes: {len(df)}"
    assert df["ensembl_id"].str.startswith("ENSG").all(), "non-human ensembl_id present"

    symbols = set(df["symbol"].dropna().str.upper())
    missing = KNOWN - symbols
    assert not missing, f"canonical motif-backed TFs missing: {sorted(missing)}"

    # Provenance sufficient to know exactly what release we regenerated from.
    meta = json.loads(out.with_suffix(".meta.json").read_text())
    for field in ("jaspar_release_number", "jaspar_release_year", "source_sha256",
                  "output_sha256", "n_core_matrices"):
        assert field in meta, f"meta missing {field!r}"
