"""
CrossRef REST API client.

Authoritative source for DOI validation: CrossRef is the DOI registrar,
so a 404 response definitively means the DOI was never registered.

Usage:
    from _crossref import lookup_doi, search_by_title

    meta = lookup_doi("10.1371/journal.pone.0017258", email="you@example.com")
    # None → DOI not found; dict → metadata

    candidates = search_by_title("The Impact of Multifunctional Genes",
                                  author="Gillis", year=2011, email="you@example.com")
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

TOOL_VERSION = "0.1.0"
BASE_URL = "https://api.crossref.org/works"
CACHE_DIR = Path.home() / ".cache" / "citation-validator" / "crossref"

_last_call: list[float] = [0.0]
_MIN_INTERVAL = 0.5  # ≤ 2 req/sec — well within polite pool limits


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


def _read_cache(key: str) -> tuple[bool, object]:
    path = _cache_key(key)
    if path.exists():
        raw = json.loads(path.read_text())
        return True, raw.get("value")
    return False, None


def _write_cache(key: str, value: object) -> None:
    _cache_key(key).write_text(json.dumps({"value": value}))


def _parse_work(item: dict) -> dict:
    """Extract the fields we care about from a CrossRef work object."""
    titles = item.get("title") or []
    title = titles[0] if titles else None

    year = None
    for k in ("published-print", "published-online", "issued"):
        dp = (item.get(k) or {}).get("date-parts")
        if dp and dp[0]:
            year = dp[0][0]
            break

    authors = item.get("author") or []
    first_author = None
    if authors:
        a = authors[0]
        first_author = a.get("family") or a.get("name")

    containers = item.get("container-title") or []

    return {
        "doi": item.get("DOI"),
        "title": title,
        "year": year,
        "first_author": first_author,
        "journal": containers[0] if containers else None,
        "source": "crossref",
    }


def _get(url: str, params: dict | None = None, email: str | None = None,
         timeout: int = 20) -> requests.Response:
    _throttle()
    headers = {"User-Agent": _user_agent(email)}
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    return resp


def lookup_doi(doi: str, *, email: str | None = None,
               refresh: bool = False) -> dict | None:
    """
    Look up a DOI via CrossRef.

    Returns a metadata dict on success, or None if the DOI is not registered
    (HTTP 404). Raises RuntimeError on rate-limit or other errors.
    """
    doi = doi.strip()
    cache_key = f"doi:{doi.lower()}"

    if not refresh:
        hit, value = _read_cache(cache_key)
        if hit:
            return value  # type: ignore[return-value]

    try:
        resp = _get(f"{BASE_URL}/{doi}", email=email)
    except requests.RequestException as e:
        raise RuntimeError(f"CrossRef request failed: {e}") from e

    if resp.status_code == 404:
        _write_cache(cache_key, None)
        return None

    if resp.status_code == 429:
        raise RuntimeError(
            "CrossRef rate limit (429). Wait a moment and retry, or add --email to use the polite pool."
        )

    resp.raise_for_status()
    result = _parse_work(resp.json().get("message", {}))
    _write_cache(cache_key, result)
    return result


def search_by_title(title: str, author: str | None = None,
                    year: int | None = None, rows: int = 3,
                    *, email: str | None = None,
                    refresh: bool = False) -> list[dict]:
    """
    Search CrossRef by bibliographic text.

    Uses `query.bibliographic` (not the deprecated `query.title`).
    Returns up to *rows* candidates, sorted by relevance.
    """
    cache_key = f"search:{title}|{author}|{year}"

    if not refresh:
        hit, value = _read_cache(cache_key)
        if hit:
            return value  # type: ignore[return-value]

    params: dict = {"query.bibliographic": title, "rows": rows}
    if author:
        params["query.author"] = author

    try:
        resp = _get(BASE_URL, params=params, email=email)
    except requests.RequestException as e:
        raise RuntimeError(f"CrossRef request failed: {e}") from e

    if resp.status_code == 429:
        raise RuntimeError("CrossRef rate limit (429). See lookup_doi for guidance.")

    resp.raise_for_status()
    items = resp.json().get("message", {}).get("items", [])
    result = [_parse_work(item) for item in items]
    _write_cache(cache_key, result)
    return result
