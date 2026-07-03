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
    "rat": ("ENSRNOG",),
}


def _present_ids(tsv) -> pd.Series:
    """Non-empty ensembl_id values. Empty/NA is a legitimate 'no Ensembl
    mapping' state for symbol-only sources (AnimalTFDB symbol-only rows, and
    the gwas_catalog / omim query sources), so these checks only police the
    IDs that are actually present."""
    s = pd.read_csv(tsv, sep="\t", usecols=["ensembl_id"], dtype="string")["ensembl_id"]
    s = s.dropna()
    return s[s.str.strip() != ""]


def test_ensembl_ids_have_correct_prefix(require_any_cache):
    bad = []
    for tsv, _meta_path, meta in require_any_cache:
        species = meta.get("species")
        if species not in SPECIES_PREFIX:
            pytest.fail(f"{tsv.name}: unknown species in meta: {species!r}")
        prefixes = SPECIES_PREFIX[species]
        present = _present_ids(tsv)
        offenders = present[~present.str.startswith(prefixes)]
        if len(offenders):
            sample = offenders.head(3).tolist()
            bad.append((tsv.name, species, len(offenders), sample))
    assert not bad, (
        "TSVs containing ensembl_id values that don't match the species prefix:\n"
        + "\n".join(f"  {n}: species={s}, {c} bad rows, sample={smp}" for n, s, c, smp in bad)
    )


def test_ensembl_ids_are_unique(require_any_cache):
    """ensembl_id is the canonical join key; duplicates break set algebra.

    Only populated IDs are policed — empty/NA (symbol-only rows) can't collide
    on a join key and are legitimate for symbol-based sources."""
    bad = []
    for tsv, _meta_path, _meta in require_any_cache:
        present = _present_ids(tsv)
        dups = present[present.duplicated(keep=False)]
        if len(dups):
            sample = dups.head(3).tolist()
            bad.append((tsv.name, len(dups), sample))
    assert not bad, f"TSVs with duplicate ensembl_id: {bad}"
