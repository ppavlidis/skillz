"""Composite set algebra invariants.

For any cached composite (union or intersection), enforce:
- |intersection| ≤ min(|members|)
- |union| ≥ max(|members|) and |union| ≤ sum(|members|)
- composite meta members[] paths resolve to actual files
- every row in the composite traces back to at least one member's ensembl_id

Catches: wrong join key, wrong op, broken provenance tree, members[]
pointing at stale paths.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _composites(cached_artifacts):
    return [(t, m, meta) for (t, m, meta) in cached_artifacts if "compose" in meta]


def test_composite_provenance_paths_resolve(require_any_cache):
    composites = _composites(require_any_cache)
    if not composites:
        pytest.skip("no composite sets in cache; build one to enable")
    bad = []
    for tsv, _meta_path, meta in composites:
        for m in meta["compose"]["members"]:
            for key in ("tsv_path", "meta_path"):
                if not Path(m[key]).exists():
                    bad.append((tsv.name, m["set"], key, m[key]))
    assert not bad, f"composite member paths that don't resolve: {bad}"


def test_intersection_le_min_member(require_any_cache):
    composites = _composites(require_any_cache)
    if not composites:
        pytest.skip("no composite sets in cache")
    for tsv, _meta_path, meta in composites:
        if meta["compose"]["op"] != "intersection":
            continue
        member_sizes = []
        for m in meta["compose"]["members"]:
            member_tsv = Path(m["tsv_path"])
            with member_tsv.open() as f:
                member_sizes.append(sum(1 for _ in f) - 1)
        n = meta["n_genes"]
        assert n <= min(member_sizes), (
            f"{tsv.name}: intersection size {n} exceeds smallest member "
            f"({min(member_sizes)} = min of {member_sizes}) — math broken"
        )


def test_union_ge_max_and_le_sum(require_any_cache):
    composites = _composites(require_any_cache)
    if not composites:
        pytest.skip("no composite sets in cache")
    for tsv, _meta_path, meta in composites:
        if meta["compose"]["op"] != "union":
            continue
        member_sizes = []
        for m in meta["compose"]["members"]:
            member_tsv = Path(m["tsv_path"])
            with member_tsv.open() as f:
                member_sizes.append(sum(1 for _ in f) - 1)
        n = meta["n_genes"]
        assert n >= max(member_sizes), (
            f"{tsv.name}: union size {n} is smaller than largest member "
            f"({max(member_sizes)} = max of {member_sizes})"
        )
        assert n <= sum(member_sizes), (
            f"{tsv.name}: union size {n} exceeds sum of members ({sum(member_sizes)}) — duplicates?"
        )


def test_composite_rows_appear_in_at_least_one_member(require_any_cache):
    """Every ensembl_id in the composite must be present in at least one
    member set (union) or all members (intersection)."""
    composites = _composites(require_any_cache)
    if not composites:
        pytest.skip("no composite sets in cache")
    for tsv, _meta_path, meta in composites:
        comp_ids = set(pd.read_csv(tsv, sep="\t", usecols=["ensembl_id"], dtype="string")["ensembl_id"].dropna())
        members_ids: list[set[str]] = []
        for m in meta["compose"]["members"]:
            mids = set(pd.read_csv(Path(m["tsv_path"]), sep="\t", usecols=["ensembl_id"], dtype="string")["ensembl_id"].dropna())
            members_ids.append(mids)

        if meta["compose"]["op"] == "union":
            union_of_members = set().union(*members_ids)
            stragglers = comp_ids - union_of_members
        else:  # intersection
            intersection_of_members = set.intersection(*members_ids) if members_ids else set()
            stragglers = comp_ids - intersection_of_members

        assert not stragglers, (
            f"{tsv.name}: composite contains ensembl_ids not derivable from members: "
            f"{list(stragglers)[:5]} (showing first 5 of {len(stragglers)})"
        )
