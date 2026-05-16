"""
OpenAlex REST API client — title search and DOI lookup.

OpenAlex indexes 250M+ works including conference proceedings and preprints
that CrossRef sometimes misses.  No authentication required; a mailto: email
in the User-Agent enables the polite pool (higher rate limit).

https://docs.openalex.org/
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import requests

TOOL_VERSION = "0.1.0"
BASE_URL = "https://api.openalex.org/works"
CACHE_DIR = Path.home() / ".cache" / "citation-validator" / "openalex"

_last_call: list[float] = [0.0]
_MIN_INTERVAL = 0.12  # ≤ 8 req/sec — within polite pool limit


def _user_agent(email: str | None) -> str:
    ua = f"citation-validator/{TOOL_VERSION} (https://github.com/ppavlidis/skillz"
    if email:
        ua += f"; mailto:{email}"
    ua += ")"
    return ua


def _throttle() -> None:
    elapsed = time.monotonic() - _last_call[0]
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call[0] = time.monotonic()


def _cache_key(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / (hashlib.md5(key.encode()).hexdigest() + ".json")


def _read_cache(key: str):
    path = _cache_key(key)
    if path.exists():
        raw = json.loads(path.read_text())
        return True, raw.get("value")
    return False, None


def _write_cache(key: str, value) -> None:
    _cache_key(key).write_text(json.dumps({"value": value}))


def _get(url: str, params: dict | None = None, email: str | None = None,
         timeout: int = 20) -> requests.Response:
    _throttle()
    headers = {"User-Agent": _user_agent(email)}
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    return resp


def _parse_work(item: dict) -> dict:
    """Extract normalised fields from an OpenAlex work object."""
    raw_doi = item.get("doi") or (item.get("ids") or {}).get("doi") or ""
    doi = re.sub(r"^https?://doi\.org/", "", raw_doi, flags=re.IGNORECASE) or None

    title = item.get("display_name") or item.get("title")

    authorships = item.get("authorships") or []
    first_author: str | None = None
    if authorships:
        display = (authorships[0].get("author") or {}).get("display_name") or ""
        # OpenAlex uses "Given Family" order; take last token as family name
        parts = display.strip().split()
        first_author = parts[-1] if parts else None

    year = item.get("publication_year")

    return {
        "doi": doi,
        "title": title,
        "year": year,
        "first_author": first_author,
        "source": "openalex",
    }


def lookup_doi(doi: str, *, email: str | None = None,
               refresh: bool = False) -> dict | None:
    """
    Look up a work by DOI in OpenAlex.
    Returns a metadata dict or None if not found.
    """
    doi = doi.strip()
    cache_key = f"oa_doi:{doi.lower()}"

    if not refresh:
        hit, value = _read_cache(cache_key)
        if hit:
            return value

    try:
        resp = _get(f"{BASE_URL}/https://doi.org/{doi}", email=email)
    except requests.RequestException as e:
        raise RuntimeError(f"OpenAlex request failed: {e}") from e

    if resp.status_code == 404:
        _write_cache(cache_key, None)
        return None

    if resp.status_code == 429:
        raise RuntimeError("OpenAlex rate limit (429). Add --email to use the polite pool.")

    resp.raise_for_status()
    result = _parse_work(resp.json())
    _write_cache(cache_key, result)
    return result


def search_by_title(title: str, author: str | None = None,
                    year: int | None = None, rows: int = 3,
                    *, email: str | None = None,
                    refresh: bool = False) -> list[dict]:
    """
    Search OpenAlex by title text.  Returns up to *rows* candidates.
    """
    cache_key = f"oa_search:{title}|{author}|{year}"

    if not refresh:
        hit, value = _read_cache(cache_key)
        if hit:
            return value

    params: dict = {"search": title, "per_page": rows, "select": "id,doi,display_name,publication_year,authorships,ids"}
    if year:
        params["filter"] = f"publication_year:{year - 1}-{year + 1}"

    try:
        resp = _get(BASE_URL, params=params, email=email)
    except requests.RequestException as e:
        raise RuntimeError(f"OpenAlex request failed: {e}") from e

    if resp.status_code == 429:
        raise RuntimeError("OpenAlex rate limit (429). See lookup_doi for guidance.")

    resp.raise_for_status()
    items = resp.json().get("results", [])
    result = [_parse_work(item) for item in items]
    _write_cache(cache_key, result)
    return result
