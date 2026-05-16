---
name: pdf-extract
description: >
  Reproducible PDF extraction with no LLM calls: body text (page-tagged),
  document metadata (title, authors, DOI, year — from XMP, docinfo, and
  first-page heuristics), and annotations (highlights, sticky notes,
  underlines, strikethroughs) with highlighted text resolved from the text
  stream. Every output ships with a *_meta.json provenance sidecar recording
  input sha256, library name+version, and extraction timestamp so results
  can be re-verified later. Primary library: pymupdf (fitz); text-only
  fallback: pypdf. Use this skill whenever a user asks to read a PDF, extract
  annotations or highlights, retrieve a paper's DOI or metadata, or parse
  reference lists from an offline file.
---

# pdf-extract

Extracts three things from a PDF, all reproducible from a script:

| Operation | What you get |
|---|---|
| `metadata` | Title, author(s), DOI, year, keywords, page count — from XMP, docinfo, and first-page heuristics |
| `text` | Body text per page, optionally filtered to a page range |
| `annotations` | Every highlight, sticky note, underline, etc. — with the marked text resolved from the text stream |
| `all` | All three in one JSON bundle |

Every output file is accompanied by a `*_meta.json` sidecar that records
the input sha256, library name+version, and extraction timestamp.

## Usage

```bash
# Install the primary library
pip install pymupdf          # AGPL; best annotation support
pip install pypdf            # MIT; text + metadata only (no annotations)

# Extract document metadata
python scripts/extract.py metadata paper.pdf

# Extract text (JSON, with page numbers)
python scripts/extract.py text paper.pdf

# Extract text as plain text, pages 3-8 only
python scripts/extract.py text paper.pdf --format text --pages 3-8

# Extract annotations (highlights, notes, underlines)
python scripts/extract.py annotations paper.pdf

# Extract everything at once
python scripts/extract.py all paper.pdf --out paper.extracted.json

# Redirect to a specific path
python scripts/extract.py metadata paper.pdf --out paper_meta.json
```

## Output formats

### `metadata` → `paper.metadata.json`

```json
{
  "title": "The Impact of Multifunctional Genes...",
  "author": "Gillis, Jesse; Pavlidis, Paul",
  "doi": "10.1371/journal.pone.0017258",
  "year": 2011,
  "keywords": null,
  "abstract": null,
  "creator": "LaTeX",
  "producer": "pdfTeX-1.40.21",
  "created": "2011-02-17",
  "n_pages": 11,
  "input_file": "gillis2011.pdf",
  "input_sha256": "a3b4c5...",
  "library": "pymupdf",
  "library_version": "1.24.2",
  "extracted_at": "2025-01-15T10:00:00Z"
}
```

DOI is taken from, in order: XMP metadata, docinfo subject field, plain-text
search of the first page.  Year is extracted from the first four-digit number
in 1900–2099 on the first page.  Title falls back to the largest-font text
block on page 1 if docinfo is absent.

### `text` → `paper.text.json`

```json
{
  "pages": [
    {"page": 1, "text": "Title\nAbstract...\n"},
    {"page": 2, "text": "Introduction...\n"}
  ],
  "pages_requested": "all",
  "input_sha256": "...",
  "library": "pymupdf",
  "extracted_at": "..."
}
```

`--format text` writes a plain-text file with `--- page N ---` markers.
`--pages` accepts `"3"`, `"2-5"`, or `"1,3,5-7"`.

### `annotations` → `paper.annotations.json`

```json
{
  "n_annotations": 5,
  "annotations": [
    {
      "page": 2,
      "type": "Highlight",
      "highlighted_text": "The method outperforms all baselines...",
      "note": null,
      "author": "pzoot",
      "created": "D:20250115100000Z",
      "color": "#ffff00",
      "rect": [72.0, 240.3, 480.1, 252.8]
    },
    {
      "page": 3,
      "type": "Text",
      "highlighted_text": null,
      "note": "Check this claim against the supplementary.",
      "author": "pzoot",
      "created": "D:20250115100500Z",
      "color": null,
      "rect": [72.0, 310.0, 86.0, 324.0]
    }
  ],
  "input_sha256": "...",
  "library": "pymupdf",
  "extracted_at": "..."
}
```

**Annotation types captured**: `Highlight`, `Underline`, `StrikeOut`,
`Squiggly`, `Text` (sticky note), `FreeText`, `Square`, `Circle`, `Line`,
`Ink`.

Highlighted text is resolved from the text stream by intersecting the
annotation's bounding rectangle with the page's word list.  Multi-line
highlights are joined with spaces.  If the PDF uses scanned images instead
of text (i.e. no text layer), `highlighted_text` will be `null`.

## Provenance sidecar (`*_meta.json`)

Every output file gets a sidecar with:

```json
{
  "tool": "pdf-extract",
  "tool_version": "0.1.0",
  "input_file": "paper.pdf",
  "input_sha256": "a3b4c5...",
  "library": "pymupdf",
  "library_version": "1.24.2",
  "extracted_at": "2025-01-15T10:00:00Z",
  "n_annotations": 5
}
```

The sha256 is computed over the raw PDF bytes.  Re-running the script on the
same PDF produces the same sha256; a different hash means the file changed.

## Composing with other skills

- **citation-validator**: pipe `text` output's references section through
  `validate.py` to check bibliography entries.
- **provenance-stamp**: `write_meta()` accepts the sha256 and metadata from
  this skill's output as `inputs`.
- **methods-section**: the `extracted_at` and `doi` fields from `metadata`
  can be folded into the Methods paragraph as data source provenance.

## Dependencies

- `pymupdf` ≥ 1.18 — required for annotations; text + metadata also use it
- `pypdf` ≥ 3.0 — optional text + metadata fallback when pymupdf is absent

pymupdf is AGPL-3.0.  For fully MIT-licensed operation (text and metadata
only, no annotations), use `pypdf` alone.

## Known limitations

- **Scanned PDFs** (image-only): `highlighted_text` will be `null` because
  there is no text layer.  Run an OCR tool (e.g. `ocrmypdf`) first to add
  one.
- **Encrypted PDFs**: will raise an error.  Decrypt first with `qpdf`.
- **Title heuristic**: falls back to the largest-font span on page 1.  For
  PDFs where the journal logo is larger than the title this can return the
  wrong text.  Prefer the XMP/docinfo title when available.
- **Year extraction**: takes the first four-digit number in 1900–2099 on
  page 1.  Will pick up a grant number or issue date if the year appears
  later.
- **Line-wrapped DOIs**: DOIs split across a line break in the PDF text
  stream won't be reassembled.
