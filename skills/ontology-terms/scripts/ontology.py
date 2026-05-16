#!/usr/bin/env python3
"""ontology-terms CLI.

Subcommands:
    parents <term>
    children <term>
    definition <term>
    search <query>

Prints the path of the produced TSV to stdout. Fails loud with a clear stderr
message on any error — no silent fallback to stale or partial data.

Usage examples:
    python ontology.py parents GO:0006915
    python ontology.py children http://purl.obolibrary.org/obo/MONDO_0000408 --source gemma
    python ontology.py definition MP:0001262
    python ontology.py search hippocampus --ontology hp --limit 25
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `from sources import ...` work when invoked as `python scripts/ontology.py`.
sys.path.insert(0, str(Path(__file__).parent))

from sources._common import (  # noqa: E402
    CACHE_DIR,
    cache_paths,
    die,
    infer_ontology,
    is_fresh,
    write_artifact,
)

SUPPORTED_SOURCES = {"ols", "gemma", "obo", "ontobee"}


def _load_source(name: str):
    if name == "ols":
        from sources import ols  # type: ignore[import-not-found]
        return ols
    if name == "gemma":
        from sources import gemma  # type: ignore[import-not-found]
        return gemma
    if name == "obo":
        from sources import obo  # type: ignore[import-not-found]
        return obo
    if name == "ontobee":
        from sources import ontobee  # type: ignore[import-not-found]
        return ontobee
    die(f"unknown source: {name!r}; supported: {sorted(SUPPORTED_SOURCES)}")


def _resolve_ontology(ontology: str | None, term: str | None) -> str:
    if ontology and ontology != "auto":
        return ontology.lower()
    if term:
        return infer_ontology(term)
    die("--ontology auto requires a term; pass --ontology explicitly for search-only queries")


def _run_term_op(operation: str, args) -> Path:
    src = _load_source(args.source)
    ontology = _resolve_ontology(args.ontology, args.term)

    tsv_path, meta_path = cache_paths(operation, args.source, args.term, ontology, "", args.out)
    if not args.refresh and is_fresh(tsv_path, meta_path):
        return tsv_path

    fn = getattr(src, operation, None)
    if fn is None:
        die(f"source {args.source!r} does not implement operation {operation!r}", source=args.source)

    df, source_info = fn(args.term, ontology)
    return write_artifact(
        df=df,
        operation=operation,
        source=args.source,
        input_term=args.term,
        ontology=ontology,
        source_info=source_info,
        cache_dir=CACHE_DIR,
        out=args.out,
    )


def _run_search(args) -> Path:
    src = _load_source(args.source)
    ontology = (args.ontology or "").lower() if args.ontology and args.ontology != "auto" else ""
    extras = f"lim{args.limit}"
    tsv_path, meta_path = cache_paths("search", args.source, args.query, ontology or None, extras, args.out)
    if not args.refresh and is_fresh(tsv_path, meta_path):
        return tsv_path
    df, source_info = src.search(args.query, ontology or None, args.limit)
    return write_artifact(
        df=df,
        operation="search",
        source=args.source,
        input_term=args.query,
        ontology=ontology or "any",
        source_info=source_info,
        cache_dir=CACHE_DIR,
        out=args.out,
        extras=extras,
        extra_meta={"limit": args.limit},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ontology term operations across multiple sources.")
    sub = parser.add_subparsers(dest="op", required=True)

    def add_common(sp):
        sp.add_argument("--source", choices=sorted(SUPPORTED_SOURCES), default="ols")
        sp.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
        sp.add_argument("--out", type=Path, default=None, help="write TSV to this path instead of cache")

    sp_p = sub.add_parser("parents", help="immediate parents of a term")
    sp_p.add_argument("term")
    sp_p.add_argument("--ontology", default="auto")
    add_common(sp_p)

    sp_c = sub.add_parser("children", help="immediate children of a term")
    sp_c.add_argument("term")
    sp_c.add_argument("--ontology", default="auto")
    add_common(sp_c)

    sp_d = sub.add_parser("definition", help="label and definition of a term")
    sp_d.add_argument("term")
    sp_d.add_argument("--ontology", default="auto")
    add_common(sp_d)

    sp_s = sub.add_parser("search", help="search ontology for terms matching a query")
    sp_s.add_argument("query")
    sp_s.add_argument("--ontology", default=None, help="restrict to one ontology slug; default: all")
    sp_s.add_argument("--limit", type=int, default=25)
    add_common(sp_s)

    args = parser.parse_args()

    if args.op in ("parents", "children", "definition"):
        path = _run_term_op(args.op, args)
    else:
        path = _run_search(args)

    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
