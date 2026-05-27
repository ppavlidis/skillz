"""AnimalTFDB v4 — transcription factor lists by species.

**Currently broken upstream (as of 2026-05).** AnimalTFDB has moved to
`guolab.wchscu.cn`, and that host now serves a JavaScript anti-bot
challenge in front of the static download paths. A plain HTTP client
(requests, curl, wget) sees an `acw_sc__v2` cookie-setter HTML page
instead of the file.

This fetcher supports a **manual-placement workflow** as a workaround.
If a raw AnimalTFDB TSV is present at one of:

  - ``$ANIMALTFDB_RAW_DIR/{species_code}_TF.txt``
  - ``~/Downloads/{species_code}_TF.txt`` (user's typical download spot)

…the fetcher reads it, normalises to the skill's standard schema, and
writes the cached artifact + sidecar meta. The `source_version_tag`
includes ``manual-`` plus the sha256-prefix of the raw file so the cache
key still encodes upstream identity.

Long-term options: add a Playwright-based fetcher (heavy dep), find a
mirror, or fall back to TF lists from a different authority. See the
"v2 candidates" section of SKILL.md.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from ._common import (
    SourceInfo,
    cache_paths,
    die,
    iso_now,
    sha256_file,
    write_artifact,
)

FETCHER_NAME = "animaltfdb"

CANDIDATE_URLS = [
    "https://guolab.wchscu.cn/AnimalTFDB4/static/download/TF_list/{species_code}_TF",
    "https://guolab.wchscu.cn/AnimalTFDB4/TF_list/{species_code}_TF",
]

SPECIES_CODES = {
    "human": "Homo_sapiens",
    "mouse": "Mus_musculus",
    "rat": "Rattus_norvegicus",
}


def fetch(
    name: str,
    species: str,
    args: dict,
    ensembl_release: int,
    cache_dir: Path,
    out: Path | None,
    refresh: bool,
) -> Path:
    if species not in SPECIES_CODES:
        die(f"unsupported species: {species}", fetcher=FETCHER_NAME)

    species_code = args.get("species_code", SPECIES_CODES[species])

    # ---- Manual-placement workflow ----------------------------------
    # If the user has the raw AnimalTFDB file locally (Paul's pattern:
    # download via browser, drop in ~/Downloads), read + normalise it
    # into the cache. The cache_version tag pins the artifact to the
    # raw file's sha256 prefix so a different upstream snapshot
    # produces a different cache key.
    manual_dir_env = os.environ.get("ANIMALTFDB_RAW_DIR")
    manual_candidates = []
    if manual_dir_env:
        manual_candidates.append(Path(manual_dir_env) / f"{species_code}_TF.txt")
    manual_candidates.append(Path.home() / "Downloads" / f"{species_code}_TF.txt")

    raw_path: Path | None = None
    for cand in manual_candidates:
        if cand.exists():
            raw_path = cand
            break

    if raw_path is not None:
        raw_sha = sha256_file(raw_path)
        source_version_tag = f"animaltfdb4-manual-{raw_sha[:12]}"
        tsv_path, _meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
        if not refresh and tsv_path.exists():
            return tsv_path

        # Raw schema (verified for human/mouse/rat 2026-05-26):
        # Species  Symbol  Ensembl  Family  Protein  Entrez_ID
        raw = pd.read_csv(raw_path, sep="\t", dtype=str, keep_default_na=False)
        required = {"Species", "Symbol", "Ensembl", "Family", "Entrez_ID"}
        missing = required - set(raw.columns)
        if missing:
            die(
                f"AnimalTFDB raw file at {raw_path} is missing columns: {missing}",
                fetcher=FETCHER_NAME,
            )
        # Normalise to standard schema. AnimalTFDB rows occasionally
        # have empty Symbol (Ensembl-only); keep them but flag.
        out_df = pd.DataFrame({
            "ensembl_id": raw["Ensembl"].astype(str).str.strip(),
            "symbol": raw["Symbol"].astype(str).str.strip(),
            "entrez_id": raw["Entrez_ID"].astype(str).str.strip()
                .replace({"NA": "", "nan": ""}),
            "species": species,
            "source": name,
            "family": raw["Family"].astype(str).str.strip(),
        })
        # Drop rows with neither ensembl_id nor symbol.
        out_df = out_df[(out_df["ensembl_id"] != "") | (out_df["symbol"] != "")].reset_index(drop=True)
        # De-duplicate on ensembl_id (some rows lack one; keep all such).
        non_empty = out_df["ensembl_id"] != ""
        deduped_ens = out_df[non_empty].drop_duplicates(subset=["ensembl_id"])
        symbol_only = out_df[~non_empty]
        out_df = pd.concat([deduped_ens, symbol_only], ignore_index=True)

        return write_artifact(
            df=out_df,
            name=name,
            species=species,
            ensembl_release=ensembl_release,
            source=SourceInfo(
                url=f"file://{raw_path}",
                version=(
                    "AnimalTFDB v4 — manually downloaded raw file "
                    f"(upstream JS-challenged; placed at {raw_path})"
                ),
                sha256=raw_sha,
                durability=(
                    "manual placement; upstream guolab.wchscu.cn is "
                    "JS-challenged. If the raw file is replaced, the "
                    "cache key changes (sha256 in version tag)."
                ),
                notes=f"raw_columns={list(raw.columns)}, n_raw={len(raw)}, n_norm={len(out_df)}",
            ),
            cache_dir=cache_dir,
            out=out,
            source_version_tag=source_version_tag,
            extra_meta={
                "manual_raw_path": str(raw_path),
                "manual_raw_sha256": raw_sha,
            },
        )

    # ---- Upstream attempt (currently broken; fail loud) -------------
    today = iso_now().split("T")[0]
    source_version_tag = f"animaltfdb4-{today}"
    tsv_path, _meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)
    candidate_urls = [u.format(species_code=species_code) for u in CANDIDATE_URLS]

    die(
        "AnimalTFDB v4 cannot currently be fetched programmatically.\n\n"
        f"  Species: {species_code}\n"
        "  Reason: the new AnimalTFDB host (guolab.wchscu.cn) serves a\n"
        "  JavaScript anti-bot challenge in front of the static download\n"
        "  paths, so plain HTTP clients (requests, curl, wget) see an\n"
        "  acw_sc__v2 cookie-setter page instead of the file.\n\n"
        "  Manual workaround:\n"
        f"    1. Open https://guolab.wchscu.cn/AnimalTFDB4/ in a browser\n"
        f"    2. Navigate to Download → TF list → {species_code}\n"
        f"    3. Save the resulting raw TSV to ONE of:\n"
        f"         ~/Downloads/{species_code}_TF.txt   (default)\n"
        f"         $ANIMALTFDB_RAW_DIR/{species_code}_TF.txt   (override)\n"
        "    4. Re-run; the fetcher will read the raw file, normalise it\n"
        "       to the standard schema, and write the cache + sidecar meta\n"
        "       under a tag that includes the raw file's sha256 prefix.\n\n"
        f"  Tried these candidate URLs (all blocked or behind JS):\n    "
        + "\n    ".join(candidate_urls),
        fetcher=FETCHER_NAME,
    )
    # Unreachable; die() exits non-zero. Keep the return for type checkers.
    return tsv_path  # type: ignore[unreachable]
