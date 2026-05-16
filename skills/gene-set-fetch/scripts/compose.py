"""Set algebra over already-fetched member sets.

Composite sets (union, intersection) don't talk to any upstream source. They
read the TSVs of their member sets, apply the operation on `ensembl_id`,
and write a new TSV + sidecar meta that *includes the full provenance tree
of every contributing member*.

This is what makes a downstream figure built on `tfs_human_intersection`
provenance-traceable: walking the meta tree gets you back to every raw
upstream file with its sha256.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import pandas as pd

from fetchers._common import (
    STANDARD_COLUMNS,
    TOOL_VERSION,
    cache_paths,
    die,
    iso_now,
    sha256_file,
)


def _load_member(tsv_path: Path) -> tuple[pd.DataFrame, dict]:
    """Read a member's TSV and its sidecar meta. Both must exist."""
    meta_path = tsv_path.with_suffix(".meta.json")
    if not meta_path.exists():
        die(
            f"member set's sidecar meta is missing: {meta_path}\n"
            f"  every gene-set-fetch artifact must have a .meta.json — \n"
            f"  re-run the producing fetcher with --refresh",
            fetcher="compose",
        )
    df = pd.read_csv(tsv_path, sep="\t", dtype={"entrez_id": "string"})
    meta = json.loads(meta_path.read_text())
    return df, meta


def compose_sets(
    name: str,
    op: str,
    member_paths: list[Path],
    species: str,
    ensembl_release: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    """Compose a new set from existing member TSVs.

    `op` is "union" or "intersection". Joins on `ensembl_id`.
    """
    if op not in ("union", "intersection"):
        die(f"unknown compose op '{op}' for set '{name}' (must be union or intersection)", fetcher="compose")

    if not member_paths:
        die(f"compose set '{name}' has no members", fetcher="compose")

    members: list[tuple[pd.DataFrame, dict]] = [_load_member(p) for p in member_paths]

    # Sanity: species should match across members.
    species_seen = {m[1].get("species") for m in members}
    if species_seen != {species}:
        die(
            f"compose set '{name}' (species={species}) has members with mixed species: {species_seen}",
            fetcher="compose",
        )

    # Sanity: Ensembl release should match. If a member used a different
    # release, the join may silently lose IDs across release boundaries.
    releases_seen = {m[1].get("ensembl_release") for m in members}
    if releases_seen != {ensembl_release}:
        die(
            f"compose set '{name}' (ensembl_release={ensembl_release}) has members "
            f"with mismatched releases: {releases_seen}\n"
            f"  re-fetch members with --ensembl-release {ensembl_release}",
            fetcher="compose",
        )

    member_metas = [m[1] for m in members]
    member_names = [m["set"] for m in member_metas]

    # Build a per-ensembl_id contribution map.
    id_to_sources: dict[str, set[str]] = {}
    id_to_row: dict[str, dict] = {}
    for (df, meta) in members:
        for _, row in df.iterrows():
            eid = row["ensembl_id"]
            if not isinstance(eid, str) or not eid:
                continue
            id_to_sources.setdefault(eid, set()).add(meta["set"])
            if eid not in id_to_row:
                id_to_row[eid] = {
                    "ensembl_id": eid,
                    "symbol": row.get("symbol"),
                    "entrez_id": row.get("entrez_id"),
                    "species": species,
                }

    if op == "union":
        kept_ids = sorted(id_to_sources.keys())
    else:  # intersection
        all_members = set(member_names)
        kept_ids = sorted(eid for eid, srcs in id_to_sources.items() if srcs >= all_members)

    rows = []
    for eid in kept_ids:
        row = id_to_row[eid].copy()
        row["source"] = name
        row["sources"] = ";".join(sorted(id_to_sources[eid]))
        rows.append(row)

    out_df = pd.DataFrame(rows, columns=STANDARD_COLUMNS + ["sources"])

    # Cache path: tag the source version with the op + member name hashes so a
    # composite of two different member sets goes to a different file.
    source_version_tag = f"compose-{op}"
    tsv_path, meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    tsv_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = tsv_path.with_suffix(tsv_path.suffix + ".tmp")
    out_df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(tsv_path)
    output_sha = sha256_file(tsv_path)

    # The composite meta carries a full members[] array referencing each
    # contributing member's sha256s, URLs, and meta path. Walking this tree
    # gets a downstream consumer back to every raw upstream file.
    members_payload = []
    for path, meta in zip(member_paths, member_metas):
        members_payload.append({
            "set": meta["set"],
            "meta_path": str(path.with_suffix(".meta.json")),
            "tsv_path": str(path),
            "output_sha256": meta.get("output_sha256"),
            "source_url": meta.get("source_url"),
            "source_version": meta.get("source_version"),
            "source_sha256": meta.get("source_sha256"),
        })

    meta_payload = {
        "set": name,
        "species": species,
        "ensembl_release": ensembl_release,
        "n_genes": int(len(out_df)),
        "fetched_at": iso_now(),
        "compose": {
            "op": op,
            "members": members_payload,
        },
        "output_sha256": output_sha,
        "tool_version": TOOL_VERSION,
    }
    tmp_meta = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp_meta.write_text(json.dumps(meta_payload, indent=2, sort_keys=True) + "\n")
    tmp_meta.replace(meta_path)

    return tsv_path
