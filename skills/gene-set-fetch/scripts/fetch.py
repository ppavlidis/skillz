#!/usr/bin/env python3
"""gene-set-fetch CLI.

Resolves a named gene set to a TSV + sidecar .meta.json in the user cache.

Usage:
    python fetch.py <set_name> [--ensembl-release N] [--refresh] [--out PATH]

Prints the path of the produced TSV to stdout. Exits non-zero with a clear
stderr message if anything fails — no silent fallbacks.

NOTE: This is the v0.1 CLI scaffold. The fetcher modules under fetchers/ are
stubs; see SKILL.md "Design contract" before implementing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).parent / "registry.yaml"
CACHE_DIR = Path.home() / ".cache" / "gene-set-fetch"


def load_registry() -> dict:
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_set(name: str, registry: dict, ensembl_release: int, refresh: bool, out: Path | None) -> Path:
    """Resolve a set name to a TSV file path. Dispatches to fetcher or composer."""
    sets = registry.get("sets", {})
    if name not in sets:
        available = ", ".join(sorted(sets.keys()))
        raise SystemExit(
            f"error: unknown set '{name}'\n"
            f"available: {available}"
        )

    recipe = sets[name]

    if "compose" in recipe:
        # Recursively resolve members, then apply set algebra.
        from compose import compose_sets  # local import to keep CLI thin

        member_paths = [
            resolve_set(member, registry, ensembl_release, refresh, None)
            for member in recipe["compose"]["members"]
        ]
        return compose_sets(
            name=name,
            op=recipe["compose"]["op"],
            member_paths=member_paths,
            species=recipe["species"],
            ensembl_release=ensembl_release,
            cache_dir=CACHE_DIR,
            out=out,
            refresh=refresh,
        )

    if "source" in recipe:
        # Dispatch to the named fetcher module.
        source = recipe["source"]
        try:
            fetcher = __import__(f"fetchers.{source}", fromlist=["fetch"])
        except ImportError as e:
            raise SystemExit(
                f"error: fetcher 'fetchers.{source}' not available\n"
                f"  ({e})\n"
                f"  inspect or extend scripts/fetchers/ to add it"
            )
        return fetcher.fetch(
            name=name,
            species=recipe["species"],
            args=recipe.get("args", {}),
            ensembl_release=ensembl_release,
            cache_dir=CACHE_DIR,
            out=out,
            refresh=refresh,
        )

    raise SystemExit(f"error: set '{name}' has neither 'source' nor 'compose'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a named gene set (human, mouse, or rat) with provenance."
    )
    parser.add_argument("set_name", nargs="?", help="The set to fetch; see registry.yaml for the catalog.")
    parser.add_argument(
        "--ensembl-release",
        type=int,
        default=None,
        help="Ensembl release for ID normalization. Defaults to registry default.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch even if a cached artifact exists.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the TSV to this path instead of the cache.",
    )
    parser.add_argument(
        "--format",
        choices=("tsv", "json"),
        default="tsv",
        help="Output format. TSV is canonical; JSON is convenience for piping.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available set names and exit.",
    )
    args = parser.parse_args()

    registry = load_registry()

    if args.list:
        for name in sorted(registry.get("sets", {}).keys()):
            print(name)
        return 0

    if not args.set_name:
        parser.error("set_name is required (or use --list to see available sets)")

    ensembl_release = args.ensembl_release or registry.get("defaults", {}).get("ensembl_release", 113)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    path = resolve_set(
        name=args.set_name,
        registry=registry,
        ensembl_release=ensembl_release,
        refresh=args.refresh,
        out=args.out,
    )

    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
