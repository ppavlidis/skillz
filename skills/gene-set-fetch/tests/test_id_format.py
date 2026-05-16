"""Ensembl ID format tests.

Would have caught the MGI column-shift bug: when pandas auto-promoted the
first data field to a row index, the `ensembl_id` column ended up holding
`Gene` values (the marker_type field). Asserting that every ensembl_id
starts with the species-appropriate prefix surfaces this class of error
immediately.
"""

from __future__ import annotations

import pandas as pd
import pytest

SPECIES_PREFIX = {
    "human": ("ENSG",),
    "mouse": ("ENSMUSG",),
}


def test_ensembl_ids_have_correct_prefix(require_any_cache):
    bad = []
    for tsv, _meta_path, meta in require_any_cache:
        species = meta.get("species")
        if species not in SPECIES_PREFIX:
            pytest.fail(f"{tsv.name}: unknown species in meta: {species!r}")
        prefixes = SPECIES_PREFIX[species]
        df = pd.read_csv(tsv, sep="\t", usecols=["ensembl_id"], dtype="string")
        offenders = df[~df["ensembl_id"].str.startswith(prefixes, na=False)]
        if len(offenders):
            sample = offenders["ensembl_id"].head(3).tolist()
            bad.append((tsv.name, species, len(offenders), sample))
    assert not bad, (
        "TSVs containing ensembl_id values that don't match the species prefix:\n"
        + "\n".join(f"  {n}: species={s}, {c} bad rows, sample={smp}" for n, s, c, smp in bad)
    )


def test_ensembl_ids_are_unique(require_any_cache):
    """ensembl_id is the canonical join key; duplicates break set algebra."""
    bad = []
    for tsv, _meta_path, _meta in require_any_cache:
        df = pd.read_csv(tsv, sep="\t", usecols=["ensembl_id"], dtype="string")
        dups = df[df["ensembl_id"].duplicated(keep=False)]
        if len(dups):
            sample = dups["ensembl_id"].head(3).tolist()
            bad.append((tsv.name, len(dups), sample))
    assert not bad, f"TSVs with duplicate ensembl_id: {bad}"
