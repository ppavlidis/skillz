#!/usr/bin/env python3
"""gene-annotations CLI.

Subcommands:
    genes_with_annotation <go_term>
    annotations_of_gene   <gene>

Prints the path of the produced TSV to stdout. Fails loud with clear stderr
on any error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sources._common import (  # noqa: E402
    CACHE_DIR,
    cache_paths,
    die,
    is_fresh,
    normalize_go_term,
    write_artifact,
)

SUPPORTED_SOURCES = {"goa", "gaf"}


def _load_source(name: str):
    if name == "goa":
        from sources import goa  # type: ignore[import-not-found]
        return goa
    if name == "gaf":
        from sources import gaf  # type: ignore[import-not-found]
        return gaf
    die(f"unknown source: {name!r}; supported: {sorted(SUPPORTED_SOURCES)}")


def _run_genes_with_annotation(args) -> Path:
    src = _load_source(args.source)
    if not hasattr(src, "genes_with_annotation"):
        die(f"source {args.source!r} does not implement genes_with_annotation", source=args.source)
    go_term = normalize_go_term(args.term)
    tsv_path, meta_path = cache_paths(
        "genes_with_annotation", args.source, go_term, args.species,
        propagated=(not args.direct), out=args.out,
    )
    if not args.refresh and is_fresh(tsv_path, meta_path):
        return tsv_path
    df, info = src.genes_with_annotation(go_term, args.species, args.direct)
    return write_artifact(
        df=df, operation="genes_with_annotation", source=args.source,
        species=args.species, propagated=(not args.direct),
        input_value=args.term, input_resolved=go_term,
        source_info=info, cache_dir=CACHE_DIR, out=args.out,
    )


def _run_annotations_of_gene(args) -> Path:
    src = _load_source(args.source)
    if not hasattr(src, "annotations_of_gene"):
        die(f"source {args.source!r} does not implement annotations_of_gene", source=args.source)
    # v0.1: GOA source always returns DIRECT annotations for this op; the
    # cache key tag reflects what the user asked for so a future v0.2 that
    # actually propagates won't collide with v0.1 direct-only artifacts.
    tsv_path, meta_path = cache_paths(
        "annotations_of_gene", args.source, args.gene, args.species,
        propagated=(not args.direct), out=args.out,
    )
    if not args.refresh and is_fresh(tsv_path, meta_path):
        return tsv_path
    df, info = src.annotations_of_gene(args.gene, args.species, args.direct)
    resolved_input = args.gene
    ri = info.extras.get("resolved_input")
    if isinstance(ri, str):
        resolved_input = ri
    elif isinstance(ri, dict) and isinstance(ri.get("resolved_input"), str):
        resolved_input = ri["resolved_input"]
    return write_artifact(
        df=df, operation="annotations_of_gene", source=args.source,
        species=args.species, propagated=(not args.direct),
        input_value=args.gene, input_resolved=resolved_input,
        source_info=info, cache_dir=CACHE_DIR, out=args.out,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Gene ↔ GO annotation lookups.")
    sub = parser.add_subparsers(dest="op", required=True)

    def common(sp):
        sp.add_argument("--source", choices=sorted(SUPPORTED_SOURCES), default="goa")
        sp.add_argument("--species", choices=sorted(["human", "mouse"]), default="human")
        sp.add_argument("--direct", action="store_true", help="direct annotations only; disable propagation")
        sp.add_argument("--refresh", action="store_true", help="re-fetch even if cached")
        sp.add_argument("--out", type=Path, default=None)

    sp_g = sub.add_parser("genes_with_annotation", help="genes annotated to a GO term")
    sp_g.add_argument("term")
    common(sp_g)

    sp_a = sub.add_parser("annotations_of_gene", help="GO terms annotated to a gene")
    sp_a.add_argument("gene")
    common(sp_a)

    args = parser.parse_args()
    if args.op == "genes_with_annotation":
        path = _run_genes_with_annotation(args)
    else:
        path = _run_annotations_of_gene(args)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
