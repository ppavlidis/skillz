#!/usr/bin/env python3
"""
provenance-stamp: write and verify *_meta.json sidecars for analysis artifacts.

Every artifact-producing script should call write_meta() after saving its
output.  The sidecar records enough information for a reviewer to
reproduce the result: what was downloaded, when, from where, at which
version, with what parameters, and what hash the output has.

Library usage (import into your script):
    from stamp import write_meta, compute_sha256, verify
    meta = write_meta(
        "output.tsv",
        source_url="https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene2go.gz",
        doi="10.1093/nar/gkac1052",
        data_version="2026-05-01",
        fetched_at="2026-05-01T14:23:00Z",
        params={"species": "human", "aspect": "BP"},
    )

CLI subcommands:
    python stamp.py stamp  <artifact>
                           [--input PATH ...]
                           [--source-url URL]
                           [--doi DOI]
                           [--data-version VER]
                           [--fetched-at ISO_DATETIME]
                           [--param KEY VALUE] ...
    python stamp.py verify <artifact>
    python stamp.py show   <artifact>
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

TOOL_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def compute_sha256(path: "str | Path") -> str:
    """Return lowercase hex SHA-256 of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _meta_path_for(artifact: Path) -> Path:
    return artifact.parent / (artifact.name + ".meta.json")


def _iso_now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# write_meta
# ---------------------------------------------------------------------------


def write_meta(
    artifact: "str | Path",
    *,
    inputs: "list[str | Path] | None" = None,
    params: "dict | None" = None,
    source_url: "str | None" = None,
    doi: "str | None" = None,
    data_version: "str | None" = None,
    fetched_at: "str | None" = None,
    out: "str | Path | None" = None,
    **extra,
) -> dict:
    """
    Write a *_meta.json sidecar alongside *artifact* and return the meta dict.

    Parameters
    ----------
    artifact      Path to the file to stamp (must exist).
    inputs        Input file paths whose sha256s are recorded in the sidecar.
    params        Arbitrary key→value analysis parameters (species, aspect, …).
    source_url    URL the artifact was derived from.
    doi           DOI or other persistent resource identifier (e.g. "10.1093/nar/gkac1052").
    data_version  The upstream source's own version string or date
                  (e.g. "2026-05-01", "releases/2024-01-17", "release-113").
                  Distinct from stamped_at (which records when *we* stamped).
    fetched_at    ISO-8601 timestamp of when the source data was downloaded.
                  Defaults to stamped_at when not supplied.
    out           Explicit path for the .meta.json; defaults to artifact + '.meta.json'.
    **extra       Any additional top-level fields (pipeline, organism, …).
    """
    artifact = Path(artifact)
    if not artifact.exists():
        raise FileNotFoundError(f"artifact not found: {artifact}")

    now = _iso_now()
    meta: dict = {
        "artifact": artifact.name,
        "sha256": compute_sha256(artifact),
        "stamped_at": now,
        "fetched_at": fetched_at if fetched_at is not None else now,
        "tool_version": TOOL_VERSION,
    }
    if source_url is not None:
        meta["source_url"] = source_url
    if doi is not None:
        meta["doi"] = doi
    if data_version is not None:
        meta["data_version"] = data_version
    if inputs:
        meta["inputs"] = {str(p): compute_sha256(p) for p in inputs}
    if params:
        meta["params"] = dict(params)
    meta.update(extra)

    out_path = Path(out) if out else _meta_path_for(artifact)
    out_path.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


# ---------------------------------------------------------------------------
# read_meta / verify
# ---------------------------------------------------------------------------


def read_meta(artifact: "str | Path") -> dict:
    """Read the *_meta.json sidecar for *artifact*. Raises FileNotFoundError if absent."""
    meta_path = _meta_path_for(Path(artifact))
    if not meta_path.exists():
        raise FileNotFoundError(f"no sidecar found: {meta_path}")
    return json.loads(meta_path.read_text())


def verify(artifact: "str | Path") -> bool:
    """
    Return True if the artifact's current sha256 matches the sidecar.
    Raises FileNotFoundError if the artifact or sidecar is absent.
    Raises KeyError if the sidecar has no recognisable sha256 field.
    """
    meta = read_meta(artifact)
    recorded = meta.get("sha256") or meta.get("output_sha256")
    if not recorded:
        raise KeyError("sidecar has no 'sha256' or 'output_sha256' field")
    return compute_sha256(artifact) == recorded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_stamp(args) -> int:
    try:
        meta = write_meta(
            args.artifact,
            inputs=args.inputs or None,
            params=dict(args.param) if args.param else None,
            source_url=args.source_url,
            doi=args.doi,
            data_version=args.data_version,
            fetched_at=args.fetched_at,
            out=args.out,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(meta, indent=2))
    return 0


def _cmd_verify(args) -> int:
    try:
        ok = verify(args.artifact)
    except (FileNotFoundError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if ok:
        print(f"OK  {args.artifact}")
        return 0
    print(f"FAIL  {args.artifact}  (sha256 mismatch)", file=sys.stderr)
    return 1


def _cmd_show(args) -> int:
    try:
        meta = read_meta(args.artifact)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(meta, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Write / verify / show *_meta.json provenance sidecars.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- stamp ----
    p_stamp = sub.add_parser("stamp", help="write a .meta.json sidecar")
    p_stamp.add_argument("artifact", type=Path)
    p_stamp.add_argument("--input", dest="inputs", action="append", type=Path,
                         metavar="PATH", help="input file to record sha256 of (repeat for multiple)")
    p_stamp.add_argument("--source-url", metavar="URL", help="upstream URL")
    p_stamp.add_argument("--doi", metavar="DOI", help="DOI or persistent resource identifier")
    p_stamp.add_argument("--data-version", metavar="VER",
                         help="upstream version/date string (e.g. 2026-05-01, release-113)")
    p_stamp.add_argument("--fetched-at", metavar="ISO",
                         help="ISO-8601 timestamp when source was downloaded")
    p_stamp.add_argument("--out", type=Path, metavar="PATH",
                         help="explicit output path for the .meta.json")
    p_stamp.add_argument("--param", nargs=2, action="append", metavar=("KEY", "VALUE"),
                         help="add a key=value param entry (repeat for multiple)")

    # ---- verify ----
    p_verify = sub.add_parser("verify", help="check artifact sha256 against sidecar")
    p_verify.add_argument("artifact", type=Path)

    # ---- show ----
    p_show = sub.add_parser("show", help="print the .meta.json sidecar")
    p_show.add_argument("artifact", type=Path)

    args = parser.parse_args(argv)
    dispatch = {"stamp": _cmd_stamp, "verify": _cmd_verify, "show": _cmd_show}
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
