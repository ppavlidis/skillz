#!/usr/bin/env python3
"""
citation-validator: check bibliography entries against CrossRef, OpenAlex, and PubMed.

For each citation, checks whether the paper exists and whether the
stated metadata (title, year, first author) matches what is on record.
Designed for personal validation of AI-generated bibliographies;
occasional false positives are acceptable.

Status codes (CITADEL taxonomy)
--------------------------------
VERIFIED          DOI resolved; title/year/author match ≥ 85%.
VERIFIED_NO_DOI   No DOI given; found matching paper via title search.
PHANTOM           DOI given but not registered — entirely fabricated citation.
CHIMERA           DOI resolves but title/author bear no resemblance (< 50%);
                  real DOI attached to fabricated content (Topaz et al. 2026).
CORRUPTED         DOI resolves but metadata partly wrong: real paper, bad
                  metadata (wrong year, mismatched author, reformatted title).
SUSPICIOUS        Weak title match (65–85%); needs manual review.
NOT_FOUND         No DOI; title search returned no close match across all
                  sources (CrossRef, OpenAlex, PubMed).
UNVERIFIABLE      API/network error; could not check.

Sources tried in order
-----------------------
DOI lookup:   CrossRef (authoritative) → arXiv API (for 10.48550/arXiv.*)
Title search: CrossRef → OpenAlex → PubMed

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
import _openalex
import _pubmed

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

# Abbreviation periods that should NOT be treated as sentence boundaries when
# splitting plain-text references into segments for title extraction.
_ABBREV_PERIOD_RE = re.compile(
    r"\b(vs|pp|et al|ed|eds|vol|fig|cf|ca|approx|suppl|no|nr|dr|mr|mrs|prof|jr|sr|dept|univ)\.",
    re.IGNORECASE,
)


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
        # Skip blocks that are pure publisher/preprint page-header/footer patterns
        if re.match(r"Downloaded from https?://", block, re.IGNORECASE):
            continue
        if re.match(r"bioRxiv preprint", block, re.IGNORECASE):
            continue
        if re.match(r"PLOS\s+\w", block):
            continue
        # Skip figure/table caption blocks (appear after references in some PDFs)
        if re.match(r"(?:Figure|Fig\.|Table)\s+\d+", block, re.IGNORECASE):
            continue
        # Strip publisher footer clusters embedded WITHIN citation blocks.
        # PLOS footers look like: "Short running title\nPLOS Journal | https://doi.org/...\nDate\nPage / Total"
        # We strip: the PLOS line, the preceding line (often a short running title), and 1-2 following lines.
        block = re.sub(
            r"\n[^\n]*\n[^\n]*\bPLOS\s+\w+[^\n]*(?:\n[^\n]*){1,2}",
            "",
            block,
        )
        # OUP: "Downloaded from https://..." already handled above; strip if mid-block
        block = re.sub(r"\n[^\n]*Downloaded from https?://[^\n]*", "", block, flags=re.IGNORECASE)
        # Skip blocks that are too short after stripping URLs/DOIs (other footer artifacts)
        block_no_url = re.sub(r"https?://\S+|10\.\d{4,}/\S+", "", block).strip()
        if len(block_no_url) < 15:
            continue

        # Normalize intra-block line breaks: wrapped references become one line
        block_flat = re.sub(r"\s*\n\s*", " ", block).strip()

        # DOI — extract before stripping URL annotations (DOI may be inside an
        # "Available from: https://doi.org/..." link)
        doi = _clean_doi(_extract_doi(block_flat))

        # Strip URL/PMID suffixes for cleaner title extraction
        block_flat = re.sub(r"\s*Available from:\s*https?://\S+", "", block_flat, flags=re.IGNORECASE)
        block_flat = re.sub(r"\s*PMID:\s*\d+", "", block_flat, flags=re.IGNORECASE)
        # Skip duplicate DOIs with no meaningful surrounding text (footer/header artifacts)
        if doi and doi in seen_dois and not block_no_url:
            continue
        if doi:
            seen_dois.add(doi)

        # Year — only accept 1900–2099 to avoid issue numbers like "6226"
        year = None
        for ym in re.finditer(r"\((\d{4})\)|\b((?:19|20)\d{2})\b", block_flat):
            candidate = int(ym.group(1) or ym.group(2))
            if 1900 <= candidate <= 2099:
                year = candidate
                break

        # Strip BMC/BioMed Central page-footer lines embedded within citation blocks
        # (format: "Author et al JournalName YEAR, Vol(Issue):Pages\nhttp://...")
        block_flat = re.sub(
            r"\s+[A-Z][a-z]+ (?:et al|and [A-Z][a-z]+) [A-Za-z ]+ \d{4}, [0-9()\-:Suppl]+\s+https?://\S+",
            "",
            block_flat,
        )

        # Title extraction — four patterns tried in priority order:
        title = None

        # Pattern 0: "Author(s): Title. Journal YEAR" — BMC/NLM colon-before-title format.
        # The author list ends with "Surname I:" (possibly with et al) and the title follows.
        # Handles: plain period, question mark, exclamation; optional leading quote on title.
        colon_m = re.search(
            r"(?:\bet al\.?\s*|[A-Z][a-z]+\s+[A-Z]{1,3})\s*:\s+(\"?[A-Z][^.?!]{10,})[.?!]",
            block_flat,
        )
        if colon_m:
            candidate = colon_m.group(1).strip().strip('"').rstrip(".,")
            # Reject if the "title" looks like a journal citation (contains year + vol)
            if not re.search(r"\d{4},\s*\d+", candidate):
                title = candidate

        # Pattern 1: "(YEAR). Title." or "(YEAR) Title" — APA/Nature style
        if not title:
            tm = re.search(r"\((?:19|20)\d{2}\)\.?\s+([A-Z][^.]{10,})\.", block_flat)
            if tm:
                title = tm.group(1).strip().rstrip(".")

        # Pattern 2: ". YEAR. Title." — Vancouver with year after authors (e.g. JI style)
        if not title:
            tm = re.search(r"\.\s+((?:19|20)\d{2})\.\s+([A-Z][^.]{10,})\.", block_flat)
            if tm:
                title = tm.group(2).strip().rstrip(".")

        # Pattern 3: sentence scan — split on ". " and find the first segment that
        # looks like a title (≥20 chars, not just author initials or a journal abbrev).
        # Protect known abbreviation periods (vs., pp., et al., …) so they don't
        # produce spurious sentence breaks.
        if not title:
            _PLACEHOLDER = "\x00"
            protected = _ABBREV_PERIOD_RE.sub(
                lambda m: m.group(1) + _PLACEHOLDER, block_flat
            )
            sentences = [
                s.replace(_PLACEHOLDER, ".").strip()
                for s in re.split(r"(?<=\.)\s+", protected)
                if s.strip()
            ]
            for seg in sentences[1:]:  # skip first segment (usually author list / ref number)
                # Reject: author initials (e.g. "Gillis J"), journal abbreviations
                # (short all-caps words), volume/page patterns
                if len(seg) < 20:
                    continue
                # vol:page in any form: "27:1860", "27(13):1860", "215(3):403"
                if re.search(r"\d+\(?(?:\d+\))?:\d+", seg):
                    continue
                if re.match(r"[A-Z][a-z]+ [A-Z]{1,2}[,;]?$", seg):  # "Author I"
                    continue
                # Reject author-list segments: "Surname I[,.]" at the start
                if re.match(r"^[A-Z][a-z]+\s+[A-Z]{1,3}[,.]", seg):
                    continue
                # Reject multi-author lists: "Name I, Name2 GH, Name3 X, et al" pattern
                # (≥2 commas + initials after each family name)
                if seg.count(",") >= 2 and re.search(r"\b[A-Z]{1,2}\b", seg):
                    continue
                # Accept: starts with capital, contains 3+ consecutive lowercase letters
                # (use [a-z]{3,} not \b[a-z]{3,}\b so title-case words like "Ontology" pass)
                if re.match(r"[A-Z]", seg) and re.search(r"[a-z]{3,}", seg):
                    title = seg.rstrip(".")
                    break

        # Strip conference/venue suffixes that leak into extracted titles.
        # APA/Zotero format: "Title, in: Conference Name" or "Title. Presented at ..."
        if title:
            title = re.sub(r",?\s+[Ii]n:\s+.*$", "", title)
            title = re.sub(r"\.\s+[Pp]resented at\s+.*$", "", title)
            title = title.rstrip(".,").strip()

        # First author: first capitalized word in the block
        first_author = None
        am = re.match(r"^\s*[\[(]?\d*[\].)]\s*([A-Z][a-zA-Z\-']+)", block_flat)
        if not am:
            am = re.match(r"^\s*([A-Z][a-zA-Z\-']+)", block_flat)
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
# LaTeX bibliography parser (.tex with thebibliography env, or .bbl)
# ---------------------------------------------------------------------------

# Minimal mapping for common accented-letter macros. Not exhaustive — the
# downstream metadata comparison normalizes/folds accents anyway, so
# leaving an unmapped macro in place mostly costs us nothing.
_LATEX_ACCENTS = {
    r'\"a': "ä", r'\"o': "ö", r'\"u': "ü",
    r'\"A': "Ä", r'\"O': "Ö", r'\"U': "Ü",
    r"\'a": "á", r"\'e": "é", r"\'i": "í", r"\'o": "ó", r"\'u": "ú",
    r"\'A": "Á", r"\'E": "É", r"\'I": "Í", r"\'O": "Ó", r"\'U": "Ú",
    r"\`a": "à", r"\`e": "è", r"\`i": "ì", r"\`o": "ò", r"\`u": "ù",
    r"\^a": "â", r"\^e": "ê", r"\^i": "î", r"\^o": "ô", r"\^u": "û",
    r"\~n": "ñ", r"\~N": "Ñ",
    r"{\ss}": "ß", r"\ss": "ß",
    r"\o": "ø", r"\O": "Ø",
    r"\AA": "Å", r"\aa": "å",
    r"\ae": "æ", r"\AE": "Æ",
}


def _clean_latex(s: str) -> str:
    """Strip enough LaTeX markup to make a citation block readable as
    plain text. Conservative — preserves all content tokens, only
    removes formatting commands and braces."""
    # Accented characters first (longest keys first wins via substitution order
    # only if non-overlapping; the keys here are non-overlapping).
    for k, v in _LATEX_ACCENTS.items():
        s = s.replace(k, v)

    # Two passes through the inner-arg commands to handle one level of
    # nesting (e.g. \textbf{\textit{X}}). Three passes are overkill for
    # real-world bibliographies; two catches the common cases.
    inner_arg = re.compile(
        r"\\(?:textit|textbf|emph|textsc|textrm|texttt|textsf|mathrm|mathit)"
        r"\s*\{([^{}]*)\}"
    )
    for _ in range(2):
        s = inner_arg.sub(r"\1", s)

    # \href{url}{text} -> text; we lose the url, but the DOI extractor
    # downstream picks up any 10.xxxx/yyy from the raw block via the
    # bare doi.org URL, so this is safe.
    s = re.sub(r"\\href\s*\{[^}]*\}\s*\{([^{}]*)\}", r"\1", s)
    # \url{X} / \doi{X} / \path{X} -> X (keep — may carry the DOI)
    s = re.sub(r"\\(?:url|doi|path)\s*\{([^{}]*)\}", r"\1", s)
    # \newblock and \bibinfo{field}{value} (used by some .bbl styles)
    s = re.sub(r"\\newblock\s*", " ", s)
    s = re.sub(r"\\bibinfo\s*\{[^}]*\}\s*\{([^{}]*)\}", r"\1", s)

    # Generic single-argument command: \cmd{X} -> X (one pass — anything
    # nested deeper falls through, harmless after brace stripping below).
    s = re.sub(r"\\[a-zA-Z]+\*?\s*\{([^{}]*)\}", r"\1", s)
    # Remaining bare commands: \something -> drop
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)

    # Escaped special chars
    s = re.sub(r"\\([&%#$_])", r"\1", s)
    # ~ is a non-breaking space; --- and -- are en/em dashes
    s = s.replace("~", " ").replace("---", "-").replace("--", "-")
    # Strip remaining braces (preserves their contents)
    s = re.sub(r"[{}]", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_latex_bibitems(text: str) -> tuple[list[str], list[str]]:
    """Return parallel lists of (cite-keys, cleaned-block-text) for
    each ``\\bibitem`` in ``text``.

    If the input contains a ``thebibliography`` environment, only the
    body of that environment is scanned. Otherwise the whole input is
    scanned — this is the right behaviour for ``.bbl`` files, which
    are usually just the body without the wrapper.
    """
    env_m = re.search(
        r"\\begin\{thebibliography\}.*?\n(.*?)\\end\{thebibliography\}",
        text, flags=re.S,
    )
    body = env_m.group(1) if env_m else text

    # Split on \bibitem[optional-label]{key}. The split keeps the captured
    # key as the odd-indexed group; the content for each entry is the
    # following even-indexed slice.
    parts = re.split(r"\\bibitem(?:\[[^\]]*\])?\s*\{([^}]+)\}", body)

    keys: list[str] = []
    blocks: list[str] = []
    for i in range(1, len(parts), 2):
        key = parts[i].strip()
        content = parts[i + 1] if (i + 1) < len(parts) else ""
        cleaned = _clean_latex(content)
        if cleaned:
            keys.append(key)
            blocks.append(cleaned)
    return keys, blocks


def parse_latex(text: str) -> list[dict]:
    """Parse a LaTeX bibliography (``.tex`` with a ``thebibliography``
    environment, or a ``.bbl`` file) into citation dicts.

    Each ``\\bibitem`` becomes one citation. The block content is
    stripped of LaTeX markup (``\\textit``, ``\\emph``, ``\\href``,
    accented-letter macros, etc.) and then run through the existing
    plain-text parser so DOI / title / year / first-author extraction
    is identical to the ``.txt`` / ``.md`` path. The original
    ``\\bibitem`` key replaces the numeric key that ``parse_text``
    would otherwise assign.
    """
    keys, blocks = _extract_latex_bibitems(text)
    if not blocks:
        return []
    glued = "\n\n".join(blocks)
    citations = parse_text(glued)
    # Restore the LaTeX cite-keys (best-effort: parse_text skips blocks
    # it considers junk, so we re-align by counting non-empty blocks).
    for i, c in enumerate(citations):
        if i < len(keys):
            c["key"] = keys[i]
        c["entry_type"] = "latex_bibitem"
    return citations


# ---------------------------------------------------------------------------
# Metadata comparison
# ---------------------------------------------------------------------------

_STATUSES = {
    "VERIFIED", "VERIFIED_NO_DOI",
    "PHANTOM", "CHIMERA", "CORRUPTED",
    "SUSPICIOUS", "NOT_FOUND", "UNVERIFIABLE",
}

# Thresholds (Topaz et al. 2026 taxonomy)
_TITLE_MATCH = 0.85   # VERIFIED
_TITLE_WEAK = 0.65    # SUSPICIOUS
_TITLE_CHIMERA = 0.50 # below this with a given DOI → CHIMERA


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
    Compute status + flags from stated citation and database result.

    Taxonomy follows Topaz et al. (2026 Lancet) / CITADEL:
      PHANTOM   — DOI given, not found anywhere (entirely fabricated)
      CHIMERA   — DOI resolves, title < 50% match (real DOI, fabricated paper)
      CORRUPTED — DOI resolves, title 50–85% OR metadata wrong (real paper, bad fields)
      VERIFIED  — DOI resolves, title ≥ 85%, year not contradicted
      SUSPICIOUS — no-DOI title search, 65–85% match
      VERIFIED_NO_DOI — no-DOI title search ≥ 85% match
    """
    if found is None:
        if doi_was_given:
            return {
                "status": "PHANTOM",
                "flags": ["DOI_NOT_FOUND"],
                "title_similarity": None,
                "year_match": None,
                "author_match": None,
                "confidence": 0.95,
                "source": None,
            }
        return {
            "status": "NOT_FOUND",
            "flags": ["NO_MATCH_FOUND"],
            "title_similarity": None,
            "year_match": None,
            "author_match": None,
            "confidence": 0.50,
            "source": None,
        }

    flags: list[str] = []
    ts = title_similarity(stated.get("title"), found.get("title"))
    ym = _year_ok(stated.get("year"), found.get("year"))
    am = _author_ok(stated.get("first_author"), found.get("first_author"))
    source = found.get("source", "crossref")
    has_stated_title = bool(stated.get("title"))

    if has_stated_title and ts < _TITLE_WEAK:
        flags.append("TITLE_MISMATCH")
    if ym is False:
        flags.append("YEAR_MISMATCH")
    if am is False:
        flags.append("AUTHOR_MISMATCH")

    if doi_was_given:
        # No stated title: DOI resolved is sufficient evidence — VERIFIED at lower confidence
        if not has_stated_title:
            status = "VERIFIED"
            conf = 0.75
        elif ts >= _TITLE_MATCH and ym is not False:
            status = "VERIFIED"
            conf = round(0.85 + ts * 0.15, 2)
        elif ts >= _TITLE_WEAK and ym is not False:
            status, conf = "SUSPICIOUS", 0.55
        elif ts >= _TITLE_CHIMERA:
            status, conf = "CORRUPTED", 0.80
        else:
            status, conf = "CHIMERA", 0.90
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
        "source": source,
    }


# ---------------------------------------------------------------------------
# Multi-source title search cascade
# ---------------------------------------------------------------------------

def _title_search_cascade(title: str, author: str | None, year: int | None,
                           *, email: str | None, refresh: bool) -> dict | None:
    """
    Try CrossRef → OpenAlex → PubMed for title search.
    Returns the best-matching work dict (with .source field) or None.
    """
    _THRESHOLD = 0.35

    # CrossRef
    try:
        candidates = _crossref.search_by_title(
            title, author=author, year=year, email=email, refresh=refresh,
        )
        if candidates:
            best = max(candidates, key=lambda c: title_similarity(title, c.get("title")))
            if title_similarity(title, best.get("title")) >= _THRESHOLD:
                best["source"] = "crossref"
                return best
    except RuntimeError:
        pass

    # OpenAlex
    try:
        candidates = _openalex.search_by_title(
            title, author=author, year=year, refresh=refresh,
        )
        if candidates:
            best = max(candidates, key=lambda c: title_similarity(title, c.get("title")))
            if title_similarity(title, best.get("title")) >= _THRESHOLD:
                return best  # source already set to "openalex"
    except RuntimeError:
        pass

    # PubMed
    try:
        candidates = _pubmed.search_by_title(
            title, author=author, year=year, refresh=refresh,
        )
        if candidates:
            best = max(candidates, key=lambda c: title_similarity(title, c.get("title")))
            if title_similarity(title, best.get("title")) >= _THRESHOLD:
                return best  # source already set to "pubmed"
    except RuntimeError:
        pass

    return None


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
            status = "VERIFIED" if ok else ("UNVERIFIABLE" if ok is None else "PHANTOM")
            return {
                "key": citation.get("key"),
                "status": status,
                "flags": "ARXIV_DOI" if ok else "",
                "confidence": 0.85 if ok else 0.5,
                "stated_title": title,
                "stated_doi": doi,
                "stated_year": year,
                "stated_first_author": first_author,
                "db_title": None,
                "db_doi": doi if ok else None,
                "db_year": None,
                "db_first_author": None,
                "title_similarity": None,
                "year_match": None,
                "author_match": None,
                "source": "arxiv" if ok else None,
                "notes": "verified via arXiv API" if ok else "arXiv DOI; not in CrossRef",
            }
        if doi:
            found = _crossref.lookup_doi(doi, email=email, refresh=refresh)
        elif title:
            found = _title_search_cascade(
                title, first_author, year, email=email, refresh=refresh,
            )
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
            "db_title": None,
            "db_doi": None,
            "db_year": None,
            "db_first_author": None,
            "source": None,
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
        "db_title": (found or {}).get("title"),
        "db_doi": (found or {}).get("doi"),
        "db_year": (found or {}).get("year"),
        "db_first_author": (found or {}).get("first_author"),
        "source": cmp.get("source"),
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
    "db_title", "db_doi", "db_year", "db_first_author",
    "source", "title_similarity", "year_match", "author_match", "notes",
]


def write_tsv(results: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS, delimiter="\t",
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(results)


def write_meta(results: list[dict], input_path: Path, out_path: Path,
               email: str | None, format_: str,
               input_text: str | None = None) -> None:
    import hashlib
    if input_path.exists():
        h = hashlib.sha256(input_path.read_bytes()).hexdigest()
    elif input_text is not None:
        h = hashlib.sha256(input_text.encode()).hexdigest()
    else:
        h = "unavailable"
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
# PDF text extraction
# ---------------------------------------------------------------------------

_REF_SECTION_RE = re.compile(
    r"\n(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY|Works Cited|WORKS CITED)"
    r"[\s\n]",
    re.MULTILINE,
)


def _extract_pdf_text(path: Path) -> str:
    """
    Extract the reference section from a PDF using pymupdf (fitz), with pypdf fallback.
    Returns only the text from the references/bibliography section onward, so that
    parse_text does not accidentally consume figure captions or body text.
    Falls back to the full document text if no reference section heading is found.
    """
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(path))
        pages = [page.get_text() for page in doc]
        doc.close()
        full_text = "\n".join(pages)
    except ImportError:
        try:
            from pypdf import PdfReader  # type: ignore[import]
            reader = PdfReader(str(path))
            full_text = "\n".join(p.extract_text() or "" for p in reader.pages)
        except ImportError:
            raise RuntimeError(
                "PDF input requires pymupdf (pip install pymupdf) or pypdf (pip install pypdf)."
            )

    # Find the LAST occurrence of a reference-section heading (avoids in-text "References" mentions)
    matches = list(_REF_SECTION_RE.finditer(full_text))
    if matches:
        return full_text[matches[-1].start():]
    return full_text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate bibliography citations against CrossRef.",
    )
    parser.add_argument("input",
                        help="bibliography file (.bib, .txt, .md, .pdf, "
                             ".docx, .tex, .bbl), "
                             "Google Docs URL, or - for stdin")
    parser.add_argument("--format", choices=["bibtex", "text", "latex", "auto"],
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
    gdocs_url = None
    if str(args.input) == "-":
        text = sys.stdin.read()
        input_path = Path("stdin.txt")
    elif "docs.google.com" in str(args.input) or re.match(r"^[A-Za-z0-9_\-]{20,}$", str(args.input)):
        # Google Docs URL or bare document ID
        gdocs_url = str(args.input)
        try:
            import _gdocs
            text = _gdocs.extract_references(gdocs_url)
        except Exception as e:
            print(f"ERROR fetching Google Doc: {e}", file=sys.stderr)
            return 1
        import re as _re
        doc_id = _re.search(r"/document/d/([A-Za-z0-9_\-]+)", gdocs_url)
        slug = doc_id.group(1)[:20] if doc_id else "gdoc"
        input_path = Path(f"{slug}.gdoc")
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"ERROR: file not found: {input_path}", file=sys.stderr)
            return 1
        suffix = input_path.suffix.lower()
        if suffix == ".pdf":
            text = _extract_pdf_text(input_path)
        elif suffix == ".docx":
            try:
                import _docx
                text = _docx.extract_text(input_path)
            except RuntimeError as e:
                print(f"ERROR reading .docx: {e}", file=sys.stderr)
                return 1
        else:
            text = input_path.read_text(errors="replace")

    # Detect format
    fmt = args.format
    if fmt == "auto":
        suffix = input_path.suffix.lower()
        if suffix == ".bib":
            fmt = "bibtex"
        elif suffix in (".tex", ".bbl"):
            fmt = "latex"
        else:
            fmt = "text"

    # Parse
    if fmt == "bibtex":
        citations = parse_bibtex(text)
    elif fmt == "latex":
        citations = parse_latex(text)
    else:
        citations = parse_text(text)
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
    write_meta(results, input_path, meta_path, args.email, fmt,
               input_text=text if gdocs_url else None)

    print(f"\nReport: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
