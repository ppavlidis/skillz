"""Ensembl Compara — ortholog mapping between species via the REST API.

Source: Ensembl REST homology endpoint. Queries are pinned to a specific
Ensembl release through the archive subdomain (e{N}.rest.ensembl.org), so
the mapping is reproducible by release.

Why Compara over DIOPT: DIOPT (DRSC Integrative Ortholog Prediction Tool)
is the user's lab convention for ortholog calls and would be the natural
default — but it has no documented public REST API (web form only, with an
undocumented CGI handler), and the canonical-sources principle for this
skill is "most canonical / most durable / least likely to disappear".
Ensembl Compara wins on all three: official authority for vertebrate
homology, REST-accessible, immutable per-release archived endpoints.

If you want DIOPT calls for a specific set, add a sibling `diopt_ortholog_map`
fetcher and ship both as separate sets (e.g. `tfs_mouse_lambert_orthologs_diopt`
vs `tfs_mouse_lambert_orthologs_compara`), then compose union/intersection
per the multi-authority pattern in SKILL.md.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from ._common import (
    SourceInfo,
    cache_paths,
    die,
    http_get,
    is_fresh,
    require_module,
    sha256_bytes,
    write_artifact,
)

FETCHER_NAME = "ensembl_compara_ortholog_map"

SPECIES_REST_NAME = {
    "human": "homo_sapiens",
    "mouse": "mus_musculus",
}

REST_RATE_LIMIT_SLEEP = 0.07  # seconds per call (~14 req/s, under Ensembl's 15 limit)


def _rest_base(release: int) -> str:
    # NOTE: per-release REST archive subdomains (e{N}.rest.ensembl.org)
    # frequently refuse connections — same operational pattern as the
    # BioMart archives. Only the main rest.ensembl.org reliably serves
    # the homology endpoints. The release is still recorded in the
    # .meta.json for traceability but is NOT enforced server-side in v0.1.
    # TODO: investigate REST date-archive hosts (e.g. nov2024.archive.ensembl.org)
    # which DO sometimes serve REST, with a release→date mapping.
    return "https://rest.ensembl.org"


def _read_from_set(from_set_path: Path) -> pd.DataFrame:
    df = pd.read_csv(from_set_path, sep="\t", dtype={"entrez_id": "string"})
    if "ensembl_id" not in df.columns:
        die(
            f"from_set TSV at {from_set_path} has no ensembl_id column; cannot map orthologs",
            fetcher=FETCHER_NAME,
        )
    return df


def fetch(
    name: str,
    species: str,
    args: dict,
    ensembl_release: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    from_species = args.get("from_species")
    to_species = args.get("to_species")
    from_set_name = args.get("from_set")
    best_match_only = bool(args.get("best_match", True))

    if not (from_species and to_species and from_set_name):
        die(
            f"ensembl_compara_ortholog_map requires args: from_set, from_species, to_species. "
            f"got: {args}",
            fetcher=FETCHER_NAME,
        )
    if from_species not in SPECIES_REST_NAME or to_species not in SPECIES_REST_NAME:
        die(f"unsupported species: from={from_species} to={to_species}", fetcher=FETCHER_NAME)
    if species != to_species:
        die(
            f"recipe species ({species}) must equal to_species ({to_species})",
            fetcher=FETCHER_NAME,
        )

    source_version_tag = f"compara-e{ensembl_release}-{from_species}-to-{to_species}"
    tsv_path, meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    if not refresh and is_fresh(tsv_path, meta_path):
        return tsv_path

    requests = require_module("requests", "pip install requests", FETCHER_NAME)

    # Resolve the from_set first. Lazy import to avoid circular dependency
    # at module-load time.
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from fetch import load_registry, resolve_set  # type: ignore[import-not-found]

    registry = load_registry()
    from_set_path = resolve_set(
        name=from_set_name,
        registry=registry,
        ensembl_release=ensembl_release,
        refresh=False,
        out=None,
    )
    from_df = _read_from_set(from_set_path)
    from_ids = sorted(set(from_df["ensembl_id"].dropna().astype(str).tolist()))

    base = _rest_base(ensembl_release)
    to_species_rest = SPECIES_REST_NAME[to_species]

    rows: list[dict] = []
    raw_concat = bytearray()  # for source_sha across all REST responses

    for i, src_id in enumerate(from_ids):
        url = f"{base}/homology/id/{from_species}/{src_id}"
        params = {
            "target_species": to_species_rest,
            "type": "orthologues",
            "format": "condensed",
            "content-type": "application/json",
        }
        try:
            resp = http_get(url, requests, params=params, headers={"Accept": "application/json"}, timeout=30)
        except requests.RequestException as e:
            die(
                f"Ensembl REST homology call failed for {src_id}: {e}\n"
                f"  url: {url}",
                fetcher=FETCHER_NAME,
            )
        if resp.status_code == 429:
            # Honor server rate-limit signal: sleep at least Retry-After (or 2s)
            # and retry once. If still 429, fail loud rather than hammer.
            try:
                wait = float(resp.headers.get("Retry-After", "2"))
            except ValueError:
                wait = 2.0
            time.sleep(max(wait, 2.0))
            resp = http_get(url, requests, params=params, headers={"Accept": "application/json"}, timeout=30)
            if resp.status_code == 429:
                die(
                    f"Ensembl REST returned 429 (rate-limited) on retry for {src_id}; "
                    "back off and try again later.",
                    fetcher=FETCHER_NAME,
                )
        if resp.status_code == 404:
            # ID not known to Compara at this release — skip silently. Not
            # silent-failure: the row simply doesn't exist in the output, and
            # the meta records the input set size vs output size.
            time.sleep(REST_RATE_LIMIT_SLEEP)
            continue
        if not resp.ok:
            die(
                f"Ensembl REST returned HTTP {resp.status_code} for {src_id}\n  body: {resp.text[:300]}",
                fetcher=FETCHER_NAME,
            )

        raw_concat.extend(resp.content)
        payload = resp.json()
        data = payload.get("data", [])
        if not data:
            time.sleep(REST_RATE_LIMIT_SLEEP)
            continue
        homologies = data[0].get("homologies", [])
        if best_match_only:
            # Prefer ortholog_one2one; otherwise take the first listed.
            o2o = [h for h in homologies if h.get("type") == "ortholog_one2one"]
            chosen = o2o if o2o else homologies[:1]
        else:
            chosen = homologies
        for h in chosen:
            tgt_id = h.get("target", {}).get("id") or h.get("target_id") or h.get("id")
            tgt_species = h.get("species") or to_species_rest
            if not tgt_id or tgt_species != to_species_rest:
                continue
            rows.append({
                "ensembl_id": tgt_id,
                "symbol": pd.NA,
                "entrez_id": pd.NA,
                "species": to_species,
                "source": name,
                "from_ensembl_id": src_id,
                "homology_type": h.get("type"),
            })

        time.sleep(REST_RATE_LIMIT_SLEEP)

    if not rows:
        die(
            f"compara mapping produced zero rows from {len(from_ids)} input IDs.\n"
            f"  check Ensembl release {ensembl_release} availability of the input IDs.",
            fetcher=FETCHER_NAME,
        )

    out_df = pd.DataFrame(rows).drop_duplicates(subset=["ensembl_id"]).reset_index(drop=True)
    # Ensure the standard column order at the front.
    standard = ["ensembl_id", "symbol", "entrez_id", "species", "source"]
    out_df = out_df[standard + [c for c in out_df.columns if c not in standard]]

    source = SourceInfo(
        url=f"{base}/homology/id/{from_species}/{{id}} (per-ID GET)",
        version=f"Ensembl Compara via REST, archived endpoint e{ensembl_release}",
        sha256=sha256_bytes(bytes(raw_concat)),
        durability="Ensembl REST archived endpoints are immutable and long-lived",
        notes=(
            f"resolved {len(from_ids)} input IDs from {from_set_name}; "
            f"emitted {len(out_df)} mapped target IDs; "
            f"best_match={best_match_only}"
        ),
    )

    return write_artifact(
        df=out_df,
        name=name,
        species=to_species,
        ensembl_release=ensembl_release,
        source=source,
        cache_dir=cache_dir,
        out=out,
        source_version_tag=source_version_tag,
        extra_meta={
            "from_set": from_set_name,
            "from_set_path": str(from_set_path),
            "from_species": from_species,
            "to_species": to_species,
            "best_match_only": best_match_only,
            "n_input_ids": len(from_ids),
            "n_output_ids": int(len(out_df)),
        },
    )
