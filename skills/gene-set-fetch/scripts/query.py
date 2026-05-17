#!/usr/bin/env python3
"""gene-set-fetch — parameterized ad-hoc query CLI.

For named gene sets (TFs, protein-coding) use fetch.py.
This CLI is for queries that are parameterized at runtime:

    python query.py disease <term> [--source open_targets|gwas_catalog|omim]
                                   [--species human|mouse]
                                   [--min-score FLOAT]
                                   [--out PATH] [--refresh]

    python query.py genomic head_to_head [--species human|mouse]
                                         [--chromosome CHR]
                                         [--max-distance N]
                                         [--out PATH] [--refresh]

Prints the path of the produced TSV to stdout. Exits non-zero on failure.

Design rules:
- No literature search / PubMed / text-mining as primary source.
  Disease-gene associations come from curated databases (Open Targets,
  GWAS Catalog, OMIM). If the database doesn't have it, say so and stop.
- No hallucinated gene lists. Every row must come from the upstream source.
- Full provenance: sidecar .meta.json with source URL, version, sha256,
  query parameters recorded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "gene-set-fetch"


def cmd_disease(args: argparse.Namespace) -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    source = args.source

    if source == "open_targets":
        sys.path.insert(0, str(Path(__file__).parent))
        from sources.open_targets import query as ot_query
        path = ot_query(
            disease_term=args.term,
            species=args.species,
            min_score=args.min_score,
            cache_dir=CACHE_DIR,
            out=args.out,
            refresh=args.refresh,
        )
    elif source == "gwas_catalog":
        from sources.gwas_catalog import query as gwas_query
        path = gwas_query(
            disease_term=args.term,
            species=args.species,
            cache_dir=CACHE_DIR,
            out=args.out,
            refresh=args.refresh,
        )
    elif source == "omim":
        from sources.omim import query as omim_query
        path = omim_query(
            disease_term=args.term,
            species=args.species,
            cache_dir=CACHE_DIR,
            out=args.out,
            refresh=args.refresh,
        )
    else:
        print(f"error: unknown source '{source}'", file=sys.stderr)
        return 1

    print(path)
    return 0


def cmd_genomic(args: argparse.Namespace) -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).parent))

    feature = args.feature
    if feature == "head_to_head":
        from sources.ensembl_genomic import query_head_to_head
        path = query_head_to_head(
            species=args.species,
            chromosome=args.chromosome,
            max_distance=args.max_distance,
            cache_dir=CACHE_DIR,
            out=args.out,
            refresh=args.refresh,
        )
    else:
        print(f"error: unknown genomic feature '{feature}'. Supported: head_to_head", file=sys.stderr)
        return 1

    print(path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ad-hoc parameterized gene-set queries. For named sets use fetch.py.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- disease subcommand ---
    p_disease = sub.add_parser(
        "disease",
        help="Genes associated with a disease/trait from a curated database.",
    )
    p_disease.add_argument("term", help="Disease or trait name (e.g. 'Parkinson disease', 'type 2 diabetes')")
    p_disease.add_argument(
        "--source",
        choices=("open_targets", "gwas_catalog", "omim"),
        default="open_targets",
        help=(
            "Source database. open_targets (default): broad disease-gene associations "
            "via Open Targets Platform, includes GWAS, pathway, expression, and other "
            "evidence. gwas_catalog: GWAS Catalog hits only (complex traits). "
            "omim: Mendelian disease-gene (requires OMIM API key in Keychain)."
        ),
    )
    p_disease.add_argument(
        "--species",
        choices=("human", "mouse"),
        default="human",
        help="Species for ID normalization (default: human). Note: disease databases are mostly human-centric.",
    )
    p_disease.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum association score [0,1]. Open Targets only. Default 0 = all associations.",
    )
    p_disease.add_argument("--out", type=Path, default=None, help="Write TSV to this path instead of cache.")
    p_disease.add_argument("--refresh", action="store_true", help="Re-fetch even if cached.")
    p_disease.set_defaults(func=cmd_disease)

    # --- genomic subcommand ---
    p_genomic = sub.add_parser(
        "genomic",
        help="Gene sets defined by genomic structural features.",
    )
    p_genomic.add_argument(
        "feature",
        choices=("head_to_head",),
        help=(
            "head_to_head: bidirectionally-transcribed gene pairs whose TSSs are "
            "within --max-distance bp of each other (divergently transcribed, "
            "shared-promoter-region pairs)."
        ),
    )
    p_genomic.add_argument("--species", choices=("human", "mouse"), default="human")
    p_genomic.add_argument(
        "--chromosome",
        default=None,
        help="Restrict to a single chromosome (e.g. '6', 'X'). Default: all chromosomes.",
    )
    p_genomic.add_argument(
        "--max-distance",
        type=int,
        default=1000,
        help="Maximum TSS-to-TSS distance in bp to call a head-to-head pair (default: 1000).",
    )
    p_genomic.add_argument("--out", type=Path, default=None, help="Write TSV to this path instead of cache.")
    p_genomic.add_argument("--refresh", action="store_true", help="Re-fetch even if cached.")
    p_genomic.set_defaults(func=cmd_genomic)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
