#!/usr/bin/env python3
"""
pdf-extract: reproducible text, metadata, and annotation extraction from PDFs.

All operations run entirely offline with no LLM calls.  Every output ships
with a *_meta.json provenance sidecar recording the input sha256, library
version, and extraction timestamp so results can be re-verified later.

Subcommands
-----------
    python scripts/extract.py text       paper.pdf
    python scripts/extract.py metadata   paper.pdf
    python scripts/extract.py annotations paper.pdf
    python scripts/extract.py all        paper.pdf

Primary library: pymupdf (fitz) — pip install pymupdf.
Fallback for text-only: pypdf — pip install pypdf.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

TOOL_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# PDF open helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _open_fitz(path: Path):
    try:
        import fitz  # type: ignore[import]
        return fitz.open(str(path)), "pymupdf", fitz.__version__
    except ImportError:
        return None, None, None


def _open_pypdf(path: Path):
    try:
        import pypdf  # type: ignore[import]
        return pypdf.PdfReader(str(path)), "pypdf", pypdf.__version__
    except ImportError:
        return None, None, None


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(r"\b(10\.\d{4,}/\S+)", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_DATE_RE = re.compile(r"D:(\d{4})(\d{2})(\d{2})")  # PDF date format


def _parse_pdf_date(raw: str | None) -> str | None:
    if not raw:
        return None
    m = _DATE_RE.match(raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _clean_doi(raw: str) -> str | None:
    """Strip URL prefix and trailing punctuation from a DOI match."""
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", raw, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    doi = doi.rstrip(".,;)>\"']}")
    # Require at least one digit in suffix (filters journal-only prefixes)
    parts = doi.split("/", 1)
    if len(parts) < 2 or len(parts[1]) < 4 or not re.search(r"\d", parts[1]):
        return None
    return doi if doi.startswith("10.") else None


def _extract_doi(text: str) -> str | None:
    for m in _DOI_RE.finditer(text):
        doi = _clean_doi(m.group(1))
        if doi:
            return doi
    return None


def _fitz_metadata(doc, path: Path, sha256: str) -> dict:
    import fitz  # type: ignore[import]
    raw_meta = doc.metadata or {}

    # --- docinfo fields ---
    title = raw_meta.get("title") or None
    author = raw_meta.get("author") or None
    subject = raw_meta.get("subject") or None
    creator = raw_meta.get("creator") or None
    producer = raw_meta.get("producer") or None
    created = _parse_pdf_date(raw_meta.get("creationDate"))
    modified = _parse_pdf_date(raw_meta.get("modDate"))

    # --- XMP: richer title/author/DOI/abstract ---
    doi: str | None = None
    abstract: str | None = None
    keywords: str | None = None
    xmp_str = doc.get_xml_metadata()
    if xmp_str:
        # Try to pull DOI from XMP (some publishers embed it)
        xmp_doi_m = re.search(r"<[^>]*doi[^>]*>([^<]+)</", xmp_str, re.IGNORECASE)
        if xmp_doi_m:
            doi = _clean_doi(xmp_doi_m.group(1).strip())
        kw_m = re.search(r"<[^>]*keywords[^>]*>([^<]+)</", xmp_str, re.IGNORECASE)
        if kw_m:
            keywords = kw_m.group(1).strip()

    # --- first-page heuristics ---
    first_page = doc[0] if len(doc) > 0 else None
    first_text = first_page.get_text("text") if first_page else ""

    # DOI from first page if not in XMP
    if not doi:
        doi = _extract_doi(first_text)

    # Year from first page
    year: int | None = None
    for m in _YEAR_RE.finditer(first_text):
        candidate = int(m.group(1))
        if 1900 <= candidate <= 2099:
            year = candidate
            break

    # Title heuristic: if docinfo has none, try largest font block on page 1
    if not title and first_page:
        blocks = first_page.get_text("dict").get("blocks", [])
        best_size, best_text = 0.0, ""
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = span.get("size", 0)
                    text = span.get("text", "").strip()
                    if size > best_size and len(text) > 10:
                        best_size, best_text = size, text
        if best_text:
            title = best_text

    return {
        "title": title,
        "author": author,
        "subject": subject,
        "doi": doi,
        "year": year,
        "keywords": keywords,
        "abstract": abstract,
        "creator": creator,
        "producer": producer,
        "created": created,
        "modified": modified,
        "pdf_version": raw_meta.get("format"),
        "n_pages": len(doc),
        "input_file": path.name,
        "input_sha256": sha256,
        "library": "pymupdf",
        "library_version": fitz.__version__,
        "extracted_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def _pypdf_metadata(reader, path: Path, sha256: str) -> dict:
    import pypdf  # type: ignore[import]
    info = reader.metadata or {}

    title = info.get("/Title") or None
    author = info.get("/Author") or None
    creator = info.get("/Creator") or None
    producer = info.get("/Producer") or None

    first_text = ""
    if reader.pages:
        first_text = reader.pages[0].extract_text() or ""

    doi = _extract_doi(first_text)
    year: int | None = None
    for m in _YEAR_RE.finditer(first_text):
        candidate = int(m.group(1))
        if 1900 <= candidate <= 2099:
            year = candidate
            break

    return {
        "title": title,
        "author": author,
        "subject": info.get("/Subject") or None,
        "doi": doi,
        "year": year,
        "keywords": info.get("/Keywords") or None,
        "abstract": None,
        "creator": creator,
        "producer": producer,
        "created": None,
        "modified": None,
        "pdf_version": None,
        "n_pages": len(reader.pages),
        "input_file": path.name,
        "input_sha256": sha256,
        "library": "pypdf",
        "library_version": pypdf.__version__,
        "extracted_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def extract_metadata(path: Path) -> dict:
    sha = _sha256(path)
    doc, lib, ver = _open_fitz(path)
    if doc is not None:
        result = _fitz_metadata(doc, path, sha)
        doc.close()
        return result
    reader, lib, ver = _open_pypdf(path)
    if reader is not None:
        return _pypdf_metadata(reader, path, sha)
    raise RuntimeError("Neither pymupdf nor pypdf is installed. pip install pymupdf")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(path: Path, pages: str | None = None,
                 fmt: str = "text") -> dict:
    """
    Extract body text.

    pages: None (all), "3" (single), "2-5" (range), "1,3,5" (list).
    fmt: "text" (plain) or "json" (per-page list).
    """
    sha = _sha256(path)
    doc, lib, ver = _open_fitz(path)

    if doc is None:
        reader, lib, ver = _open_pypdf(path)
        if reader is None:
            raise RuntimeError("Neither pymupdf nor pypdf is installed.")
        page_texts = []
        for i, page in enumerate(reader.pages, start=1):
            page_texts.append({"page": i, "text": page.extract_text() or ""})
        doc = None
    else:
        page_texts = []
        for page in doc:
            page_texts.append({"page": page.number + 1, "text": page.get_text("text")})
        doc.close()

    # Filter by page range
    selected = _filter_pages(page_texts, pages)

    return {
        "input_file": path.name,
        "input_sha256": sha,
        "library": lib,
        "library_version": ver,
        "extracted_at": datetime.datetime.utcnow().isoformat() + "Z",
        "pages_requested": pages or "all",
        "pages": selected,
        "format": fmt,
    }


def _parse_page_spec(spec: str, total: int) -> set[int]:
    """Parse "1", "2-5", or "1,3,5-7" into a set of 1-based page numbers."""
    result = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.update(range(int(a), int(b) + 1))
        else:
            result.add(int(part))
    return {p for p in result if 1 <= p <= total}


def _filter_pages(page_texts: list[dict], spec: str | None) -> list[dict]:
    if not spec:
        return page_texts
    total = len(page_texts)
    keep = _parse_page_spec(spec, total)
    return [p for p in page_texts if p["page"] in keep]


# ---------------------------------------------------------------------------
# Annotation extraction
# ---------------------------------------------------------------------------

# Annotation subtypes we capture
_ANNOT_TYPES = {"Highlight", "Underline", "StrikeOut", "Squiggly", "Text",
                "FreeText", "Square", "Circle", "Line", "Ink"}


def _color_to_hex(color: tuple | None) -> str | None:
    if not color:
        return None
    if len(color) == 3:
        r, g, b = color
        return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))
    return None


def _resolve_highlighted_text(page, annot_rect) -> str:
    """
    Extract the text under a highlight/underline annotation rectangle.
    Uses word-level intersection; handles multi-line highlights.
    """
    import fitz  # type: ignore[import]
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
    rect = fitz.Rect(annot_rect)
    # Expand slightly for edge cases where word bbox just misses the annotation
    rect = rect + (-1, -2, 1, 2)
    return " ".join(w[4] for w in words if fitz.Rect(w[:4]).intersects(rect))


def extract_annotations(path: Path) -> dict:
    sha = _sha256(path)
    doc, lib, ver = _open_fitz(path)
    if doc is None:
        raise RuntimeError(
            "Annotation extraction requires pymupdf.  pip install pymupdf"
        )

    import fitz  # type: ignore[import]
    annotations = []

    for page in doc:
        for annot in page.annots():
            subtype = annot.type[1]
            if subtype not in _ANNOT_TYPES:
                continue

            info = annot.info
            entry: dict = {
                "page": page.number + 1,
                "type": subtype,
                "highlighted_text": None,
                "note": info.get("content") or None,
                "author": info.get("title") or None,
                "created": info.get("creationDate") or None,
                "modified": info.get("modDate") or None,
                "color": _color_to_hex(annot.colors.get("stroke") or annot.colors.get("fill")),
                "rect": [round(v, 1) for v in annot.rect],
            }

            # Resolve the marked text for mark-up annotation types
            if subtype in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
                entry["highlighted_text"] = _resolve_highlighted_text(page, annot.rect) or None

            # FreeText carries its own text
            if subtype == "FreeText":
                entry["highlighted_text"] = annot.get_text() or None

            annotations.append(entry)

    doc.close()

    return {
        "input_file": path.name,
        "input_sha256": sha,
        "library": lib,
        "library_version": ver,
        "extracted_at": datetime.datetime.utcnow().isoformat() + "Z",
        "n_pages": sum(1 for _ in fitz.open(str(path))),
        "n_annotations": len(annotations),
        "annotations": annotations,
    }


# ---------------------------------------------------------------------------
# Provenance sidecar
# ---------------------------------------------------------------------------

def _write_meta(result: dict, out_path: Path) -> None:
    meta = {
        "tool": "pdf-extract",
        "tool_version": TOOL_VERSION,
        "input_file": result.get("input_file"),
        "input_sha256": result.get("input_sha256"),
        "library": result.get("library"),
        "library_version": result.get("library_version"),
        "extracted_at": result.get("extracted_at"),
    }
    # Operation-specific counts
    if "annotations" in result:
        meta["n_annotations"] = result.get("n_annotations")
        meta["n_pages"] = result.get("n_pages")
    if "pages" in result:
        meta["n_pages_extracted"] = len(result.get("pages", []))
        meta["pages_requested"] = result.get("pages_requested")
    meta_path = out_path.with_suffix("").with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _text_output(result: dict) -> str:
    if result.get("format") == "json":
        return json.dumps(result, indent=2)
    # Plain text: join pages with page markers
    parts = []
    for p in result.get("pages", []):
        parts.append(f"--- page {p['page']} ---\n{p['text']}")
    return "\n\n".join(parts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract text, metadata, or annotations from a PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("operation", choices=["text", "metadata", "annotations", "all"],
                        help="what to extract")
    parser.add_argument("input", type=Path, help="input PDF file")
    parser.add_argument("--out", type=Path,
                        help="output file (default: <input>.<op>.json or .txt)")
    parser.add_argument("--pages",
                        help='page range: "3", "2-5", or "1,3,5-7" (for text only)')
    parser.add_argument("--format", choices=["text", "json"], default="json",
                        dest="fmt",
                        help="output format for text operation (default: json)")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"ERROR: file not found: {args.input}", file=sys.stderr)
        return 1

    ops = ["text", "metadata", "annotations"] if args.operation == "all" else [args.operation]
    results = {}

    for op in ops:
        try:
            if op == "metadata":
                results[op] = extract_metadata(args.input)
            elif op == "text":
                results[op] = extract_text(args.input, pages=args.pages, fmt=args.fmt)
            elif op == "annotations":
                results[op] = extract_annotations(args.input)
        except RuntimeError as e:
            print(f"ERROR [{op}]: {e}", file=sys.stderr)
            return 1

    if args.operation == "all":
        # Write all three to one JSON bundle
        out_path = args.out or args.input.with_suffix(".extracted.json")
        bundle = {
            "tool": "pdf-extract",
            "tool_version": TOOL_VERSION,
            "input_file": args.input.name,
            **results,
        }
        out_path.write_text(json.dumps(bundle, indent=2) + "\n")
        _write_meta(results.get("annotations") or results.get("text") or results.get("metadata"),
                    out_path)
        print(f"Wrote: {out_path}", file=sys.stderr)
    else:
        op = ops[0]
        result = results[op]
        if op == "text" and args.fmt == "text":
            suffix = ".txt"
            content = _text_output(result)
        else:
            suffix = f".{op}.json"
            content = json.dumps(result, indent=2) + "\n"
        out_path = args.out or args.input.with_suffix(suffix)
        out_path.write_text(content)
        _write_meta(result, out_path)
        print(f"Wrote: {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
