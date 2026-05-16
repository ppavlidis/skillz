"""AnimalTFDB v4 — transcription factor lists by species.

**Currently broken upstream (as of 2026-05).** AnimalTFDB has moved to
`guolab.wchscu.cn`, and that host now serves a JavaScript anti-bot
challenge in front of the static download paths. A plain HTTP client
(requests, curl, wget) sees an `acw_sc__v2` cookie-setter HTML page
instead of the file.

This fetcher's job, until upstream relaxes the JS challenge or the file
is mirrored elsewhere, is to fail loud with a clear pointer to the manual
download UI and an explanation of the situation. Composites that depend
on `tfs_human_animaltfdb` / `tfs_mouse_animaltfdb` (e.g.
`tfs_human_intersection`) will therefore also fail until a workaround is
in place.

**Manual workaround:** download the species TF file from
https://guolab.wchscu.cn/AnimalTFDB4/ via a real browser, then place it at
the cache path the fetcher prints in its error message. Re-run.

**Long-term options:** add a Playwright-based fetcher (heavy dep), find a
mirror, or fall back to TF lists from a different authority. See the
"v2 candidates" section of SKILL.md.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._common import (
    cache_paths,
    die,
    iso_now,
)

FETCHER_NAME = "animaltfdb"

CANDIDATE_URLS = [
    "https://guolab.wchscu.cn/AnimalTFDB4/static/download/TF_list/{species_code}_TF",
    "https://guolab.wchscu.cn/AnimalTFDB4/TF_list/{species_code}_TF",
]

SPECIES_CODES = {
    "human": "Homo_sapiens",
    "mouse": "Mus_musculus",
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
    today = iso_now().split("T")[0]
    source_version_tag = f"animaltfdb4-{today}"

    tsv_path, _meta_path = cache_paths(name, ensembl_release, source_version_tag, cache_dir, out)

    # If the user has manually placed a downloaded AnimalTFDB file at the
    # expected cache path AND written a matching .meta.json, the dispatcher's
    # is_fresh check (in fetch.py) will short-circuit before we even get
    # here. So if we're running, it means there is no manual workaround in
    # place — fail loud with a clear pointer.
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
        f"    3. Save the resulting TSV to: {tsv_path}\n"
        f"    4. Write a matching sidecar to: {tsv_path.with_suffix(tsv_path.suffix + '.meta.json')}\n"
        "       (use any other fetcher's .meta.json as a template; the\n"
        "        source_sha256 should hash the raw downloaded file)\n"
        "    5. Re-run; the cache check will pick up your manual artifact.\n\n"
        f"  Tried these candidate URLs (all blocked or behind JS):\n    "
        + "\n    ".join(candidate_urls),
        fetcher=FETCHER_NAME,
    )
    # Unreachable; die() exits non-zero. Keep the return for type checkers.
    return tsv_path  # type: ignore[unreachable]
