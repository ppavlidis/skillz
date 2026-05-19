---
name: citation-validator
description: >
  Validate bibliography citations against CrossRef to detect hallucinated
  references. For each citation checks: (1) does the DOI exist? (2) does
  the stated metadata (title, year, first author) match CrossRef's record?
  Accepts BibTeX (.bib), LaTeX bibliographies (.tex with thebibliography
  environment, .bbl), Word (.docx, via python-docx), PDF (.pdf, via
  pymupdf), plain-text / Markdown reference lists, and Google Docs URLs. Primary
  source: CrossRef REST API (the DOI registrar — a 404 definitively means
  the DOI was never registered). Outputs a TSV report with per-citation
  status, similarity scores, and flags. v0.2 planned: relevance check —
  does the paper content match the context in which it is cited? Use this
  skill whenever a user asks to check references, validate a bibliography,
  find hallucinated citations, or spot fake DOIs.
---

# citation-validator

LLMs hallucinate citations. The pattern is consistent: plausible author
names, plausible journals, plausible years — but the paper doesn't exist,
or the DOI belongs to a completely different paper.  This skill checks both.

## Citation taxonomy (Topaz et al. 2026 / CITADEL)

| Status | Meaning | Action |
|---|---|---|
| `VERIFIED` | DOI resolved; title/year/author match ≥ 85% | Accept |
| `VERIFIED_NO_DOI` | No DOI given; title search found a matching paper | Accept; add the DOI |
| `PHANTOM` | DOI given but not registered anywhere — entirely fabricated | **Delete or replace** |
| `CHIMERA` | DOI resolves to a real paper, but title < 50% match — real DOI attached to fabricated content | **Investigate — likely hallucination** |
| `CORRUPTED` | DOI resolves, title 50–85% or metadata partly wrong — real paper, bad fields | Verify manually |
| `SUSPICIOUS` | Weak title match (65–85%) in title-search path | Review manually |
| `NOT_FOUND` | No DOI; title search returned no close match across all sources | Manual verification required |
| `UNVERIFIABLE` | API/network error | Retry or check manually |

`PHANTOM` and `CHIMERA` are the two strong hallucination signals
(Topaz et al., *Lancet* 2026 — fabricated citations accelerating 12× from 2023 to 2026).

## Three levels of validation

| Level | What's checked | Cost |
|---|---|---|
| **Level 1: DOI existence** | Is the DOI registered with CrossRef? | Fast, ~0.5s/citation |
| **Level 2: Metadata match** | Does stated title/year/author match record across CrossRef + OpenAlex + PubMed? | Same call + fallback |
| **Level 3: Relevance check** | Does the paper's content match the context where it's cited? | Expensive; requires abstract + document; v0.2 |

v0.1 ships Levels 1 and 2.  Level 3 is designed below.

## Recommended workflow (pre-submission)

The primary use case is checking your own bibliography before journal submission.
The most reliable input is a BibTeX export from your reference manager (Zotero, Mendeley, etc.) — DOIs are already present, parsing is exact.

```bash
# Best: export .bib from Zotero, then:
python scripts/validate.py refs.bib --email you@example.com

# Also works: paste bibliography from Word / Google Docs into a .txt file
python scripts/validate.py refs.txt --email you@example.com

# PDF input (experimental — see caveats below)
python scripts/validate.py paper.pdf --email you@example.com
```

## Usage

```bash
# Validate a BibTeX file
python scripts/validate.py refs.bib

# Plain text bibliography (numbered list, APA, Vancouver, …)
python scripts/validate.py refs.txt --format text

# Provide your email for CrossRef polite pool (faster, recommended)
python scripts/validate.py refs.bib --email you@example.com

# Force re-query (bypass cache)
python scripts/validate.py refs.bib --refresh

# Write report to specific path
python scripts/validate.py refs.bib --out report.tsv
```

Reads from stdin with `-` as the input path.

### PDF input caveats

PDF extraction is best-effort.  Known failure modes:

- **Two-column layouts**: text is extracted column-interleaved; most references parse incorrectly.
- **Figure captions after references**: filtered, but edge cases remain.
- **Truncated DOIs**: line-wrapped DOIs in PDFs are cut at the break; the truncated form is not valid and yields a false PHANTOM.
- **Running headers/footers**: PLOS, BMC, OUP page headers embedded between references are stripped, but non-standard footers may slip through.

For any of these, exporting the bibliography from your reference manager as `.bib` or plain text is far more reliable.

## Status codes

See taxonomy table above.

## Output columns

| column | meaning |
|---|---|
| `key` | BibTeX key or reference number |
| `status` | see taxonomy table |
| `flags` | comma-separated: `DOI_NOT_FOUND`, `TITLE_MISMATCH`, `YEAR_MISMATCH`, `AUTHOR_MISMATCH` |
| `confidence` | 0–1; how confident the status assignment is |
| `stated_title` / `stated_doi` / `stated_year` / `stated_first_author` | from input |
| `db_title` / `db_doi` / `db_year` / `db_first_author` | from the database that matched |
| `source` | which database verified this: `crossref`, `openalex`, `pubmed`, `arxiv` |
| `title_similarity` | 0–1 fuzzy match after Unicode normalisation and punctuation stripping |
| `year_match` | True / False / None |
| `author_match` | True / False / None |
| `notes` | error messages or other annotations |

A sidecar `*.meta.json` records input sha256, tool version, timestamp, and per-status counts.

## Supported input formats

**BibTeX** (auto-detected for `.bib`):
```bibtex
@article{love2014,
  title   = {Moderated estimation of fold change...},
  author  = {Love, Michael I and Huber, Wolfgang},
  year    = {2014},
  doi     = {10.1186/s13059-014-0550-8},
}
```
Uses `bibtexparser` if installed; falls back to a built-in regex parser. Both
handle `doi =` and `url = {https://doi.org/...}` fields. The doi field is
normalised from any form (`https://doi.org/`, `doi:`, bare) to the canonical
`10.xxxx/yyy` form.

**Plain text / Markdown** (`--format text`, auto-detected for everything else):
```
1. Love MI, Huber W, Anders S (2014). Moderated estimation... doi:10.1186/s13059-014-0550-8
```
Splits on blank lines or leading numbered/bulleted patterns. Extracts DOIs
from anywhere in the block via regex; title and author are best-effort.
For plain-text input, having DOIs in the bibliography is strongly recommended.

**LaTeX** (`--format latex`, auto-detected for `.tex` and `.bbl`):
```latex
\begin{thebibliography}{9}
\bibitem{love2014}
Love, M.~I., Huber, W., and Anders, S. (2014).
\newblock Moderated estimation of fold change ... with DESeq2.
\newblock \emph{Genome Biology}, 15(12):550.
\newblock \doi{10.1186/s13059-014-0550-8}.
\end{thebibliography}
```
Finds the ``thebibliography`` environment (or scans the whole file for
``.bbl`` inputs that omit the wrapper), splits on ``\bibitem``, strips
LaTeX markup (``\textit``, ``\emph``, ``\href``, accented-letter macros
like ``\"o``, ``\ss``, ``\'e``), then runs the cleaned text through the
plain-text parser. Each citation keeps its original ``\bibitem`` key.
This is the right input format when the user has a journal-formatted
manuscript with an inline bibliography (rather than a separate ``.bib``).

**Word (.docx)** (auto-detected for `.docx`):
Extracts paragraphs via `python-docx` (optional dependency; the helper
raises with an install hint if missing) and feeds them to the plain-
text parser. One Word paragraph = one citation block. This is the path
to use when a collaborator sends their bibliography as a Word doc —
no copy-paste-to-`.txt` step needed.

**PDF** (`.pdf`): extracts text via PyMuPDF (or pypdf fallback), then
runs the plain-text parser. Best-effort; known weakness on two-column
layouts where the columns interleave. Prefer `.bib` / `.tex` / `.docx`
when available.

## CrossRef API notes

- CrossRef is the DOI registrar. An HTTP 404 on a DOI lookup definitively
  means the DOI was never registered — not just "not in this database."
- Uses `query.bibliographic` for title search (`query.title` is deprecated).
- Polite pool: include `--email` to use a dedicated CrossRef server (faster
  with no published rate cap vs. the anonymous shared pool).
- Rate-limiting: 0.5s minimum between requests (well within polite pool).
- Results are cached in `~/.cache/citation-validator/crossref/`. Use
  `--refresh` to bypass the cache.

### arXiv DOIs (`10.48550/arXiv.*`)

arXiv registers DOIs with DataCite, not CrossRef — CrossRef returns 404 for
all `10.48550/arXiv.*` DOIs regardless of whether the paper exists.  The
validator detects this prefix and falls back to the arXiv export API
(`https://export.arxiv.org/abs/{id}`) for verification: 200 → `VERIFIED`
(with `ARXIV_DOI` flag), 404 → `DOI_NOT_FOUND`, network error → `UNVERIFIABLE`.

**Biolit integration path**: if `biolit` is available in the environment, it
can resolve arXiv DOIs via its own DOI pipeline (which already handles
DataCite) and may also fetch abstracts for arXiv papers.  Once biolit exposes
a public `resolve(doi)` function, the arXiv fallback here can delegate to it.

## Level 3: Relevance check (v0.2)

The third validation dimension: does the cited paper's *content* actually
support the claim made at the point of citation?  A real paper with a
correctly matched DOI can still be misused — cited for a claim it doesn't
make, or cited in the wrong context.

Planned design:
```bash
python scripts/validate.py refs.bib \
    --check-relevance manuscript.md \
    --ss-api-key YOUR_KEY          # Semantic Scholar free key for abstract fetch
```

Approach:
1. Parse the manuscript to extract citation contexts: the sentence(s)
   surrounding each `\cite{key}` or inline reference.
2. Fetch abstract for each paper: CrossRef sometimes deposits abstracts;
   Semantic Scholar has better coverage (`/graph/v1/paper/DOI:{doi}?fields=abstract`).
3. Compare context vs. abstract using sentence-level embedding similarity
   (likely `sentence-transformers` or a call to an LLM for the judgment).
4. Flag: `CONTEXT_MISMATCH` when similarity is below threshold.

This is expensive (one LLM or embedding call per citation context) and
has a higher false-positive rate than DOI validation.  Kept optional.

**Biolit integration path**: biolit already resolves DOIs and fetches paper
metadata.  Once biolit exposes an `abstract(doi)` function, the Level 3
abstract fetching step can delegate to it.  The comparison logic
(context embedding vs. abstract embedding) would still live here.

## Dependencies

- Python 3.9+
- `requests` — CrossRef HTTP calls
- `bibtexparser` — optional; improves BibTeX parsing (fallback built-in)
- `python-docx` — optional; required to read `.docx` (Word) bibliographies
- `pymupdf` (a.k.a. `fitz`) — optional; required to read `.pdf` input

## Design contract

1. **CrossRef 404 = hallucinated DOI.** CrossRef is the registrar — there is
   no other authority. This is the most reliable signal in the tool.
2. **Metadata mismatch is also a strong signal.** An LLM sometimes attaches
   a real DOI to a different (hallucinated) paper. `METADATA_MISMATCH` catches
   this: the DOI resolves, but the title it resolves to doesn't match.
3. **Personal use; occasional false positives are OK.** The thresholds
   (`TITLE_MATCH = 0.85`) are tuned for low false negatives (don't miss
   hallucinations) at the cost of some false positives (flag borderline-
   matching legitimate citations). Titles with subtitles, Unicode characters,
   or unusual punctuation may hit `SUSPICIOUS` even when real.
4. **`query.title` is deprecated.** All searches use `query.bibliographic`.
5. **Plain-text input quality depends on DOIs being present.** Without DOIs,
   the validator falls back to fuzzy title search, which is less reliable.
   Encourage users to export bibliography with DOIs from their reference
   manager before running.
6. **Cache is your friend.** The cache at `~/.cache/citation-validator/` means
   re-running on the same bibliography after editing is fast.

## Related tools

- **Citation-Hallucination-Detection** (github.com/Vikranth3140/Citation-Hallucination-Detection)
  — research prototype, JSONL input, multi-source pipeline; more complex to run
- **CheckIfExist** (arxiv:2602.15871) — web tool, batch BibTeX upload; no CLI
- **habanero** (Python) — CrossRef API wrapper; lookup only, not a validator
