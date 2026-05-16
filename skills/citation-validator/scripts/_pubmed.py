"""
PubMed E-utilities client — title search for biomedical citations.

PubMed indexes ~37M records and is the authoritative source for biomedical
literature.  Especially useful for pre-2000 papers and clinical citations
that CrossRef and OpenAlex may not cover.

Rate limits: 3 req/sec without API key; 10 req/sec with one.
API key is optional but resolves from the macOS Keychain under the entry
names "NCBI_API_KEY", "ncbi", or "pubmed-api-key".
https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

TOOL_VERSION = "0.1.0"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CACHE_DIR = Path.home() / ".cache" / "citation-validator" / "pubmed"

_last_call: list[float] = [0.0]
_MIN_INTERVAL_NO_KEY = 0.34  # 3 req/sec
_MIN_INTERVAL_WITH_KEY = 0.11  # 10 req/sec


def _api_key() -> str | None:
    key = os.environ.get("NCBI_API_KEY")
    if key:
        return key
    try:
        import subprocess
        for entry in ("NCBI_API_KEY", "ncbi", "pubmed-api-key"):
            r = subprocess.run(
                ["security", "find-generic-password", "-s", entry, "-w"],
                capture_output=True, text=True,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
    except Exception:
        pass
    return None


def _throttle(key: str | None) -> None:
    interval = _MIN_INTERVAL_WITH_KEY if key else _MIN_INTERVAL_NO_KEY
    elapsed = time.monotonic() - _last_call[0]
    if elapsed < interval:
        time.sleep(interval - elapsed)
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


def _get(url: str, params: dict, api_key: str | None, timeout: int = 20) -> requests.Response:
    _throttle(api_key)
    if api_key:
        params = {**params, "api_key": api_key}
    headers = {"User-Agent": f"citation-validator/{TOOL_VERSION} (mailto:pubmed@ncbi.nlm.nih.gov)"}
    return requests.get(url, params=params, headers=headers, timeout=timeout)


def _parse_summary(uid: str, data: dict) -> dict | None:
    rec = (data.get("result") or {}).get(uid)
    if not rec or rec.get("uid") != uid:
        return None

    # DOI from articleids array
    doi: str | None = None
    for aid in rec.get("articleids", []):
        if aid.get("idtype") == "doi" and aid.get("value"):
            doi = aid["value"]
            break

    # Year from pubdate / epubdate
    for date_field in ("pubdate", "epubdate"):
        pubdate = rec.get(date_field) or ""
        m = re.match(r"(\d{4})", pubdate)
        if m:
            year = int(m.group(1))
            break
    else:
        year = None

    # Title — PubMed appends a period; strip it
    title = (rec.get("title") or "").rstrip(".")

    # First author family name
    authors = rec.get("authors") or []
    first_author: str | None = None
    if authors:
        # PubMed format: "Family I" or "Family GI" — first token is family name
        first_author = authors[0].get("name", "").split()[0] or None

    return {
        "doi": doi,
        "title": title,
        "year": year,
        "first_author": first_author,
        "pmid": uid,
        "source": "pubmed",
    }


def search_by_title(title: str, author: str | None = None,
                    year: int | None = None, rows: int = 3,
                    *, refresh: bool = False) -> list[dict]:
    """
    Search PubMed by title (+ optional author/year hints).
    Two-step: esearch returns PMIDs; esummary fetches metadata.
    Returns up to *rows* candidates.
    """
    cache_key = f"pm_search:{title}|{author}|{year}"

    if not refresh:
        hit, value = _read_cache(cache_key)
        if hit:
            return value

    api_key = _api_key()

    # Build search query
    query = f'"{title}"[Title]'
    if author:
        query += f' AND {author.split()[0]}[Author]'
    if year:
        query += f" AND {year - 1}:{year + 1}[PDAT]"

    try:
        resp = _get(ESEARCH_URL, {
            "db": "pubmed", "term": query,
            "retmode": "json", "retmax": rows,
        }, api_key)
    except requests.RequestException as e:
        raise RuntimeError(f"PubMed esearch failed: {e}") from e

    resp.raise_for_status()
    pmids = resp.json().get("esearchresult", {}).get("idlist", [])

    if not pmids:
        _write_cache(cache_key, [])
        return []

    # Fetch summaries
    try:
        resp2 = _get(ESUMMARY_URL, {
            "db": "pubmed", "id": ",".join(pmids),
            "retmode": "json",
        }, api_key)
    except requests.RequestException as e:
        raise RuntimeError(f"PubMed esummary failed: {e}") from e

    resp2.raise_for_status()
    data = resp2.json()

    results = [r for uid in pmids if (r := _parse_summary(uid, data)) is not None]
    _write_cache(cache_key, results)
    return results
