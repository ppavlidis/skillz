#!/usr/bin/env python3
"""
citation-validator: check bibliography entries against CrossRef.

For each citation, checks whether the paper exists and whether the
stated metadata (title, year, first author) matches what CrossRef
returns.  Designed for personal validation of AI-generated bibliographies;
occasional false positives are acceptable.

Status codes
------------
VERIFIED          DOI resolved; title/year/author match CrossRef.
VERIFIED_NO_DOI   No DOI given; found matching paper via title search.
DOI_NOT_FOUND     DOI given but CrossRef returns 404 — likely hallucinated.
METADATA_MISMATCH DOI resolves but metadata diverges significantly.
SUSPICIOUS        Weak title match; needs manual review.
NOT_FOUND         No DOI; title search returned no close match.
UNVERIFIABLE      API/network error; could not check.

Usage
-----
    python scripts/validate.py refs.bib
    python scripts/validate.py refs.bib --format bibtex --email you@example.com
    python scripts/validate.py refs.txt --format text --out report.tsv
"""

from __future__ import annotations

import argparse
import csv
import datetime
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _crossref

TOOL_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# String normalisation + similarity
# ---------------------------------------------------------------------------

_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\{([^}]*)\}")
_CURLY_RE = re.compile(r"[{}]")


def _normalize(s: str | None) -> str:
    """Lowercase, strip accents, remove punctuation, collapse whitespace."""
    if not s:
        return ""
    s = _LATEX_CMD_RE.sub(r"\1", s)
    s = _CURLY_RE.sub("", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def title_similarity(a: str | None, b: str | None) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na and not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


# ---------------------------------------------------------------------------
# DOI normalisation
# ---------------------------------------------------------------------------

_DOI_PREFIX_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)
_DOI_RE = re.compile(r"\b(10\.\d{4,}/\S+)", re.IGNORECASE)


_ARXIV_DOI_RE = re.compile(r"^10\.48550/arXiv\.", re.IGNORECASE)
# Minimum DOI suffix length (after "10.xxxx/") to reject truncated line-wrapped DOIs
_MIN_DOI_SUFFIX = 5


def _clean_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    doi = raw.strip()
    doi = _DOI_PREFIX_RE.sub("", doi)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    doi = doi.rstrip(".,;)")
    if not doi.startswith("10."):
        return None
    # Reject truncated DOIs — publisher/journal prefix only with no real article ID.
    # Valid article DOIs always contain at least one digit in the suffix
    # (e.g. "10.1126/science" is a journal prefix; "10.1126/science.aaa1934" is an article).
    parts = doi.split("/", 1)
    if len(parts) < 2 or len(parts[1]) < _MIN_DOI_SUFFIX:
        return None
    if not re.search(r"\d", parts[1]):
        return None
    return doi


def _extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    return m.group(1).rstrip(".,;)>\"]}'") if m else None


def _is_arxiv_doi(doi: str | None) -> bool:
    return bool(doi and _ARXIV_DOI_RE.match(doi))


# ---------------------------------------------------------------------------
# BibTeX parser  (bibtexparser if installed, regex fallback otherwise)
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(
    r"@(\w+)\s*\{\s*([^,\s]+)\s*,\s*(.*?)\n\s*\}", re.DOTALL | re.IGNORECASE
)
_FIELD_RE = re.compile(
    r"""(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|"([^"]*)"|(\d+))""",
    re.DOTALL,
)


def _clean_bib_value(v: str | None) -> str | None:
    if not v:
        return None
    v = _LATEX_CMD_RE.sub(r"\1", v)
    v = _CURLY_RE.sub("", v)
    return v.strip() or None


def _bib_first_author(author_str: str | None) -> str | None:
    if not author_str:
        return None
    name = re.split(r"\s+and\s+", author_str, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if "," in name:
        return name.split(",")[0].strip()
    words = name.split()
    return words[-1] if words else name


def parse_bibtex(text: str) -> list[dict]:
    """Parse BibTeX text into a list of citation dicts."""
    # Try bibtexparser first (cleaner Unicode/encoding handling).
    try:
        import bibtexparser  # type: ignore[import]
        db = bibtexparser.loads(text)
        results = []
        for entry in db.entries:
            raw_doi = entry.get("doi") or entry.get("DOI") or ""
            if not raw_doi:
                raw_doi = _extract_doi(entry.get("url", "")) or ""
            doi = _clean_doi(raw_doi)
            yr_raw = entry.get("year") or entry.get("date") or ""
            ym = re.search(r"\d{4}", yr_raw)
            results.append({
                "key": entry.get("ID", ""),
                "entry_type": entry.get("ENTRYTYPE", ""),
                "title": _clean_bib_value(entry.get("title") or entry.get("booktitle")),
                "doi": doi,
                "year": int(ym.group(0)) if ym else None,
                "first_author": _bib_first_author(_clean_bib_value(entry.get("author", ""))),
                "journal": _clean_bib_value(entry.get("journal") or entry.get("booktitle")),
            })
        return results
    except ImportError:
        pass

    # Regex fallback.
    results = []
    for m in _ENTRY_RE.finditer(text):
        entry_type, key, body = m.group(1).lower(), m.group(2).strip(), m.group(3)
        fields: dict[str, str | None] = {}
        for fm in _FIELD_RE.finditer(body):
            fields[fm.group(1).lower()] = _clean_bib_value(fm.group(2) or fm.group(3) or fm.group(4))

        raw_doi = fields.get("doi") or ""
        if not raw_doi:
            raw_doi = _extract_doi(fields.get("url") or "") or ""
        doi = _clean_doi(raw_doi)

        yr_raw = fields.get("year") or fields.get("date") or ""
        ym = re.search(r"\d{4}", yr_raw) if yr_raw else None

        results.append({
            "key": key,
            "entry_type": entry_type,
            "title": fields.get("title") or fields.get("booktitle"),
            "doi": doi,
            "year": int(ym.group(0)) if ym else None,
            "first_author": _bib_first_author(fields.get("author")),
            "journal": fields.get("journal") or fields.get("booktitle"),
        })
    return results


# ---------------------------------------------------------------------------
# Plain-text / Markdown reference parser
# ---------------------------------------------------------------------------

def parse_text(text: str) -> list[dict]:
    """
    Parse a plain-text or Markdown bibliography into citation dicts.

    Splits on blank lines or numbered/bulleted entries.  Extracts DOIs
    reliably; title/author are best-effort.
    """
    blocks = re.split(r"\n\s*\n|\n(?=\s*[\[(]?\d+[\].)]\s)", text.strip())
    citations = []
    seen_dois: set[str] = set()
    for i, block in enumerate(blocks, start=1):
        block = block.strip()
        if not block or len(block) < 20:
            continue
        # Skip known publisher/preprint page-header/footer patterns
        if re.match(r"Downloaded from https?://", block, re.IGNORECASE):
            continue
        if re.match(r"bioRxiv preprint", block, re.IGNORECASE):
            continue
        if re.match(r"PLOS\s+\w", block):
            continue
        # Skip blocks that are too short after stripping URLs/DOIs (other footer artifacts)
        block_no_url = re.sub(r"https?://\S+|10\.\d{4,}/\S+", "", block).strip()
        if len(block_no_url) < 15:
            continue

        # DOI — most reliable signal; _clean_doi filters truncated/malformed DOIs
        doi = _clean_doi(_extract_doi(block))
        # Skip duplicate DOIs with no meaningful surrounding text (footer/header artifacts)
        if doi and doi in seen_dois and not block_no_url:
            continue
        if doi:
            seen_dois.add(doi)

        # Year — only accept 1900–2099 to avoid issue numbers like "6226"
        year = None
        for ym in re.finditer(r"\((\d{4})\)|\b((?:19|20)\d{2})\b", block):
            candidate = int(ym.group(1) or ym.group(2))
            if 1900 <= candidate <= 2099:
                year = candidate
                break

        # Title: pattern "Authors (year). Title. Journal" or "(year) Title"
        title = None
        tm = re.search(r"\(\d{4}\)\.?\s+([^.]+(?:\.[^.]+)?)\.", block)
        if tm:
            title = tm.group(1).strip().strip("*_").rstrip(".")
        elif "." in block:
            parts = [p.strip() for p in block.split(".") if p.strip()]
            # Heuristic: first sentence-like part after author section
            if len(parts) >= 2 and len(parts[0]) < 100:
                title = parts[1].strip("*_")

        # First author: capitalized word near the start
        first_author = None
        am = re.match(r"^\s*[\[(]?\d*[\].)]\s*([A-Z][a-zA-Z\-']+)", block)
        if not am:
            am = re.match(r"^\s*([A-Z][a-zA-Z\-']+)", block)
        if am:
            first_author = am.group(1)

        citations.append({
            "key": str(i),
            "entry_type": "unknown",
            "title": title,
            "doi": doi,
            "year": year,
            "first_author": first_author,
            "journal": None,
        })
    return citations


# ---------------------------------------------------------------------------
# Metadata comparison
# ---------------------------------------------------------------------------

_STATUSES = {
    "VERIFIED", "VERIFIED_NO_DOI", "DOI_NOT_FOUND",
    "METADATA_MISMATCH", "SUSPICIOUS", "NOT_FOUND", "UNVERIFIABLE",
}

# Thresholds
_TITLE_MATCH = 0.85
_TITLE_WEAK = 0.65


def _year_ok(stated: int | None, crossref: int | None, tol: int = 1) -> bool | None:
    if stated is None or crossref is None:
        return None
    return abs(stated - crossref) <= tol


def _author_ok(stated: str | None, crossref: str | None) -> bool | None:
    if not stated or not crossref:
        return None
    s, c = _normalize(stated), _normalize(crossref)
    return s in c or c in s or (len(s) >= 4 and s[:4] == c[:4])


def compare(stated: dict, found: dict | None, doi_was_given: bool) -> dict:
    """
    Compute status + flags from stated citation and CrossRef result.
    Returns a dict with status, flags, and numeric similarity scores.
    """
    if found is None:
        if doi_was_given:
            return {
                "status": "DOI_NOT_FOUND",
                "flags": ["DOI_NOT_FOUND"],
                "title_similarity": None,
                "year_match": None,
                "author_match": None,
                "confidence": 0.95,
            }
        return {
            "status": "NOT_FOUND",
            "flags": ["NO_MATCH_FOUND"],
            "title_similarity": None,
            "year_match": None,
            "author_match": None,
            "confidence": 0.50,
        }

    flags: list[str] = []
    ts = title_similarity(stated.get("title"), found.get("title"))
    ym = _year_ok(stated.get("year"), found.get("year"))
    am = _author_ok(stated.get("first_author"), found.get("first_author"))

    if ts < _TITLE_WEAK:
        flags.append("TITLE_MISMATCH")
    if ym is False:
        flags.append("YEAR_MISMATCH")
    if am is False:
        flags.append("AUTHOR_MISMATCH")

    if doi_was_given:
        if ts >= _TITLE_MATCH and ym is not False:
            status, conf = "VERIFIED", round(0.85 + ts * 0.15, 2)
        elif ts >= _TITLE_WEAK and ym is not False:
            status, conf = "SUSPICIOUS", 0.55
        else:
            status, conf = "METADATA_MISMATCH", 0.80
    else:
        if ts >= _TITLE_MATCH and ym is not False:
            status, conf = "VERIFIED_NO_DOI", 0.80
        elif ts >= _TITLE_WEAK:
            status, conf = "SUSPICIOUS", 0.45
        else:
            status, conf = "NOT_FOUND", 0.55

    return {
        "status": status,
        "flags": flags,
        "title_similarity": round(ts, 3),
        "year_match": ym,
        "author_match": am,
        "confidence": conf,
    }


# ---------------------------------------------------------------------------
# Per-citation validation
# ---------------------------------------------------------------------------

def validate_citation(citation: dict, *, email: str | None = None,
                       refresh: bool = False) -> dict:
    """
    Validate one citation against CrossRef.  Returns a result dict.
    """
    doi = citation.get("doi")
    title = citation.get("title")
    first_author = citation.get("first_author")
    year = citation.get("year")
    doi_was_given = bool(doi)

    found: dict | None = None
    error: str | None = None

    try:
        if doi and _is_arxiv_doi(doi):
            # arXiv registers DOIs with DataCite, not CrossRef — verify via arXiv API
            arxiv_id = re.sub(r"(?i)^10\.48550/arXiv\.", "", doi)
            ok = _crossref.check_arxiv(arxiv_id, refresh=refresh)
            status = "VERIFIED" if ok else ("UNVERIFIABLE" if ok is None else "DOI_NOT_FOUND")
            return {
                "key": citation.get("key"),
                "status": status,
                "flags": "ARXIV_DOI" if ok else "",
                "confidence": 0.85 if ok else 0.5,
                "stated_title": title,
                "stated_doi": doi,
                "stated_year": year,
                "stated_first_author": first_author,
                "crossref_title": None,
                "crossref_doi": doi if ok else None,
                "crossref_year": None,
                "crossref_first_author": None,
                "title_similarity": None,
                "year_match": None,
                "author_match": None,
                "notes": "verified via arXiv API" if ok else "arXiv DOI; not in CrossRef",
            }
        if doi:
            found = _crossref.lookup_doi(doi, email=email, refresh=refresh)
        elif title:
            candidates = _crossref.search_by_title(
                title, author=first_author, year=year,
                email=email, refresh=refresh,
            )
            if candidates:
                best = max(candidates,
                           key=lambda c: title_similarity(title, c.get("title")))
                if title_similarity(title, best.get("title")) > 0.35:
                    found = best
    except RuntimeError as e:
        error = str(e)

    if error:
        return {
            "key": citation.get("key"),
            "status": "UNVERIFIABLE",
            "flags": "API_ERROR",
            "confidence": 0.0,
            "stated_title": title,
            "stated_doi": doi,
            "stated_year": year,
            "stated_first_author": first_author,
            "crossref_title": None,
            "crossref_doi": None,
            "crossref_year": None,
            "crossref_first_author": None,
            "title_similarity": None,
            "year_match": None,
            "author_match": None,
            "notes": error,
        }

    cmp = compare(citation, found, doi_was_given)

    return {
        "key": citation.get("key"),
        "status": cmp["status"],
        "flags": ",".join(cmp["flags"]),
        "confidence": cmp["confidence"],
        "stated_title": title,
        "stated_doi": doi,
        "stated_year": year,
        "stated_first_author": first_author,
        "crossref_title": (found or {}).get("title"),
        "crossref_doi": (found or {}).get("doi"),
        "crossref_year": (found or {}).get("year"),
        "crossref_first_author": (found or {}).get("first_author"),
        "title_similarity": cmp.get("title_similarity"),
        "year_match": cmp.get("year_match"),
        "author_match": cmp.get("author_match"),
        "notes": "",
    }


# ---------------------------------------------------------------------------
# TSV output
# ---------------------------------------------------------------------------

_COLUMNS = [
    "key", "status", "flags", "confidence",
    "stated_title", "stated_doi", "stated_year", "stated_first_author",
    "crossref_title", "crossref_doi", "crossref_year", "crossref_first_author",
    "title_similarity", "year_match", "author_match", "notes",
]


def write_tsv(results: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(results)


def write_meta(results: list[dict], input_path: Path, out_path: Path,
               email: str | None, format_: str) -> None:
    import hashlib
    h = hashlib.sha256(input_path.read_bytes()).hexdigest()
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    meta = {
        "tool_version": TOOL_VERSION,
        "validated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "input_file": input_path.name,
        "input_sha256": h,
        "input_format": format_,
        "n_citations": len(results),
        "status_counts": counts,
        "email_used": bool(email),
        "source": "crossref",
    }
    out_path.write_text(json.dumps(meta, indent=2) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate bibliography citations against CrossRef.",
    )
    parser.add_argument("input", type=Path,
                        help="bibliography file (.bib, .txt, .md, or -  for stdin)")
    parser.add_argument("--format", choices=["bibtex", "text", "auto"],
                        default="auto",
                        help="input format (default: auto-detect from extension)")
    parser.add_argument("--email", metavar="EMAIL",
                        help="your email for CrossRef polite pool (faster, recommended)")
    parser.add_argument("--out", type=Path,
                        help="output TSV path (default: <input>.validation.tsv)")
    parser.add_argument("--refresh", action="store_true",
                        help="bypass cache and re-query CrossRef")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress per-citation progress lines")
    args = parser.parse_args(argv)

    # Read input
    if str(args.input) == "-":
        text = sys.stdin.read()
        input_path = Path("stdin.txt")
    else:
        if not args.input.exists():
            print(f"ERROR: file not found: {args.input}", file=sys.stderr)
            return 1
        text = args.input.read_text(errors="replace")
        input_path = args.input

    # Detect format
    fmt = args.format
    if fmt == "auto":
        fmt = "bibtex" if input_path.suffix.lower() == ".bib" else "text"

    # Parse
    citations = parse_bibtex(text) if fmt == "bibtex" else parse_text(text)
    if not citations:
        print("WARNING: no citations parsed.", file=sys.stderr)
        return 0

    print(f"Validating {len(citations)} citation(s) via CrossRef …", file=sys.stderr)

    # Validate
    results = []
    for cit in citations:
        result = validate_citation(cit, email=args.email, refresh=args.refresh)
        results.append(result)
        if not args.quiet:
            flag_str = f" [{result['flags']}]" if result["flags"] else ""
            print(f"  {result['key']:20s}  {result['status']}{flag_str}", file=sys.stderr)

    # Summary
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\nSummary:", file=sys.stderr)
    for status, n in sorted(counts.items()):
        print(f"  {status:<22s} {n}", file=sys.stderr)

    # Write output
    out_path = args.out or input_path.with_suffix("").with_suffix(".validation.tsv")
    write_tsv(results, out_path)
    meta_path = out_path.with_suffix(".meta.json")
    write_meta(results, input_path, meta_path, args.email, fmt)

    print(f"\nReport: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
