"""Read paragraph text from a `.docx` (Microsoft Word) file.

Used by the validator to accept Word bibliographies directly (avoiding
the copy-paste-to-.txt step that was the previous workflow). Output
is a plain string with one paragraph per `\\n\\n`-separated block —
the same shape `parse_text` expects, so the existing block-splitter
sees one citation per Word paragraph.

Falls back loudly: `python-docx` is an optional dependency; if missing
we raise with a clear install hint rather than silently producing
empty output.
"""
from __future__ import annotations
from pathlib import Path


def extract_text(path: Path) -> str:
    """Extract paragraph text from ``path`` (a .docx file).

    Returns a plain string with paragraphs separated by ``\\n\\n`` so
    the existing text parser sees one citation per Word paragraph.
    """
    try:
        from docx import Document
    except ImportError as e:
        raise RuntimeError(
            "Reading .docx input requires python-docx. Install with: "
            "pip install python-docx"
        ) from e

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n\n".join(paragraphs)
