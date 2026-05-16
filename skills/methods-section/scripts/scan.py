#!/usr/bin/env python3
"""
methods-section/scripts/scan.py

Scan an analysis directory and emit structured JSON describing:
  - Tools and versions (from lockfiles: requirements*.txt, renv.lock,
    environment.yml/yaml, pyproject.toml)
  - Artifacts stamped with provenance-stamp (*.meta.json sidecars) —
    each with sha256, download/stamp timestamps, source URL, DOI,
    data_version, and analysis params
  - Workflow files (Snakefile, *.nf, *.smk, *.wdl, *.cwl)
  - R and Python runtime versions

The JSON output is the raw material Claude uses to draft a Methods section.
No LLM calls happen here — this script does purely mechanical extraction.

Usage:
    python scan.py <directory> [--max-depth N] [--out FILE]

Output schema:
{
  "scan_root":      str,
  "scanned_at":     str (ISO-8601),
  "python_version": str | null,   # from renv.lock / conda yaml
  "r_version":      str | null,   # from renv.lock R.Version block
  "tools": [
    {
      "name":        str,
      "version":     str | null,
      "language":    "python" | "r" | "other",
      "source_file": str,          # relative path of the lockfile
      "source":      str | null    # CRAN / Bioconductor / PyPI / conda-forge …
    }
  ],
  "artifacts": [
    {
      "file":         str,          # artifact filename
      "meta_file":    str,          # relative path of the .meta.json
      "sha256":       str | null,
      "stamped_at":   str | null,   # when provenance was recorded
      "fetched_at":   str | null,   # when upstream data was downloaded
      "source_url":   str | null,
      "doi":          str | null,
      "data_version": str | null,
      "params":       dict | null
    }
  ],
  "workflows":      [str],          # relative paths
  "lockfiles_found":[str]           # relative paths
}
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Lockfile parsers
# ---------------------------------------------------------------------------

# Matches: package==1.2.3  package>=1.2.3  package~=1.2.3  etc.
_PIP_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"\s*[=~!<>]+\s*([^\s;#,\]]+)",
)
# Matches conda dep lines:  - package=1.2.3  or  - package==1.2.3
_CONDA_DEP_RE = re.compile(r"^\s*-\s+([a-zA-Z0-9_.\-]+)=+([^\s=,]+)")


def parse_requirements_txt(path: Path) -> list[dict]:
    """Parse pip requirements*.txt. Returns list of tool dicts."""
    tools = []
    rel = path.name
    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-") or line.startswith("git+"):
            continue
        m = _PIP_LINE_RE.match(line)
        if m:
            tools.append({
                "name": m.group(1).lower().replace("-", "_"),
                "version": m.group(3),
                "language": "python",
                "source_file": rel,
                "source": "PyPI",
            })
    return tools


def parse_renv_lock(path: Path) -> tuple[list[dict], str | None, str | None]:
    """
    Parse renv.lock JSON.
    Returns (tools_list, r_version | None, python_version | None).
    """
    try:
        data = json.loads(path.read_text(errors="replace"))
    except (json.JSONDecodeError, OSError):
        return [], None, None

    r_version: str | None = None
    python_version: str | None = None

    r_block = data.get("R") or {}
    if isinstance(r_block, dict):
        r_version = r_block.get("Version")

    py_block = data.get("Python") or {}
    if isinstance(py_block, dict):
        python_version = py_block.get("Version")

    tools = []
    rel = path.name
    for pkg_name, pkg in (data.get("Packages") or {}).items():
        if not isinstance(pkg, dict):
            continue
        tools.append({
            "name": pkg.get("Package", pkg_name),
            "version": pkg.get("Version"),
            "language": "r",
            "source_file": rel,
            "source": pkg.get("Source"),
        })
    return tools, r_version, python_version


def parse_conda_yaml(path: Path) -> tuple[list[dict], str | None]:
    """
    Parse conda environment.yaml.
    Returns (tools_list, python_version | None).
    """
    tools = []
    python_version: str | None = None
    in_deps = False
    rel = path.name

    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if stripped == "dependencies:":
            in_deps = True
            continue
        if in_deps:
            if stripped and not stripped.startswith("-") and stripped.endswith(":"):
                in_deps = False
                continue
            m = _CONDA_DEP_RE.match(line)
            if m:
                name = m.group(1).lower()
                version = m.group(2)
                if name == "python":
                    python_version = version
                tools.append({
                    "name": name,
                    "version": version,
                    "language": "python" if name not in ("r-base", "r") else "r",
                    "source_file": rel,
                    "source": "conda",
                })
    return tools, python_version


def parse_pyproject_toml(path: Path) -> list[dict]:
    """
    Extract project.dependencies from pyproject.toml via regex (no TOML parser needed).
    Handles simple `package>=version` style entries.
    """
    text = path.read_text(errors="replace")
    tools = []
    rel = path.name

    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        # Enter the dependencies array
        if re.search(r"^\[?dependencies\]?\s*=\s*\[", stripped):
            in_deps = True
        if in_deps:
            if "]" in stripped and not stripped.startswith('"') and not stripped.startswith("'"):
                in_deps = False
            candidate = stripped.strip('"\'[], ')
            m = _PIP_LINE_RE.match(candidate)
            if m:
                tools.append({
                    "name": m.group(1).lower().replace("-", "_"),
                    "version": m.group(3),
                    "language": "python",
                    "source_file": rel,
                    "source": "PyPI",
                })
    return tools


# ---------------------------------------------------------------------------
# Meta-JSON artifact scanner
# ---------------------------------------------------------------------------


def _find_meta_json(root: Path, max_depth: int | None) -> list[dict]:
    """Return structured entries for every *.meta.json sidecar found."""
    artifacts = []
    for dirpath, dirnames, filenames in os.walk(root):
        if max_depth is not None:
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= max_depth:
                dirnames.clear()
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".")
                       and d not in ("__pycache__", "node_modules")]
        for fname in sorted(filenames):
            if not fname.endswith(".meta.json"):
                continue
            meta_path = Path(dirpath) / fname
            try:
                meta = json.loads(meta_path.read_text(errors="replace"))
            except (json.JSONDecodeError, OSError):
                continue
            artifact_name = meta.get("artifact") or fname.removesuffix(".meta.json")
            entry: dict = {
                "file": artifact_name,
                "meta_file": str(meta_path.relative_to(root)),
                "sha256": None,
                "stamped_at": None,
                "fetched_at": None,
                "source_url": None,
                "doi": None,
                "data_version": None,
                "params": None,
            }
            for sha_key in ("sha256", "output_sha256"):
                if sha_key in meta:
                    entry["sha256"] = meta[sha_key]
                    break
            for ts_key in ("stamped_at", "fetched_at"):
                if ts_key in meta:
                    entry["stamped_at"] = meta[ts_key]
                    break
            entry["fetched_at"] = meta.get("fetched_at")
            for url_key in ("source_url", "url", "gaf_url", "obo_url"):
                if url_key in meta:
                    entry["source_url"] = meta[url_key]
                    break
            entry["doi"] = meta.get("doi")
            for ver_key in ("data_version", "obo_data_version", "gaf_date_generated"):
                if ver_key in meta:
                    entry["data_version"] = meta[ver_key]
                    break
            entry["params"] = meta.get("params")
            artifacts.append(entry)
    return artifacts


# ---------------------------------------------------------------------------
# Workflow detector
# ---------------------------------------------------------------------------

_WORKFLOW_NAMES = {"Snakefile", "snakefile", "workflow.smk"}
_WORKFLOW_EXTS = {".nf", ".smk", ".wdl", ".cwl"}


def _find_workflows(root: Path, max_depth: int | None) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        if max_depth is not None:
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= max_depth:
                dirnames.clear()
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if fname in _WORKFLOW_NAMES or Path(fname).suffix in _WORKFLOW_EXTS:
                found.append(str((Path(dirpath) / fname).relative_to(root)))
    return sorted(found)


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

_SKIP_DIRS = {"__pycache__", "node_modules", ".venv", "venv", ".git", ".tox"}


def scan_directory(root: "str | Path", max_depth: int | None = 4) -> dict:
    """
    Walk *root* and return a structured dict describing tools, artifacts,
    workflows, and runtime versions.
    """
    root = Path(root).resolve()
    tools: list[dict] = []
    lockfiles_found: list[str] = []
    r_version: str | None = None
    python_version: str | None = None

    for dirpath, dirnames, filenames in os.walk(root):
        if max_depth is not None:
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= max_depth:
                dirnames.clear()
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in _SKIP_DIRS]

        for fname in filenames:
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(root))

            if fname in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt"):
                tools.extend(parse_requirements_txt(fpath))
                lockfiles_found.append(rel)

            elif fname == "renv.lock":
                pkgs, rv, pv = parse_renv_lock(fpath)
                tools.extend(pkgs)
                if rv and r_version is None:
                    r_version = rv
                if pv and python_version is None:
                    python_version = pv
                lockfiles_found.append(rel)

            elif fname in ("environment.yml", "environment.yaml"):
                pkgs, pv = parse_conda_yaml(fpath)
                tools.extend(pkgs)
                if pv and python_version is None:
                    python_version = pv
                lockfiles_found.append(rel)

            elif fname == "pyproject.toml":
                pkgs = parse_pyproject_toml(fpath)
                if pkgs:
                    tools.extend(pkgs)
                    lockfiles_found.append(rel)

    # Deduplicate: same name + version + language + source → keep first
    seen: set[tuple] = set()
    unique_tools = []
    for t in tools:
        key = (t.get("name"), t.get("version"), t.get("language"))
        if key not in seen:
            seen.add(key)
            unique_tools.append(t)

    return {
        "scan_root": str(root),
        "scanned_at": datetime.datetime.utcnow().isoformat() + "Z",
        "python_version": python_version,
        "r_version": r_version,
        "tools": unique_tools,
        "artifacts": _find_meta_json(root, max_depth),
        "workflows": _find_workflows(root, max_depth),
        "lockfiles_found": lockfiles_found,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan an analysis directory and emit tool/version/provenance JSON "
            "for methods-section drafting."
        )
    )
    parser.add_argument("directory", type=Path,
                        help="root of the analysis directory to scan")
    parser.add_argument("--max-depth", type=int, default=4,
                        help="maximum directory depth to recurse (default: 4)")
    parser.add_argument("--out", type=Path,
                        help="write JSON to FILE instead of stdout")
    args = parser.parse_args(argv)

    if not args.directory.exists():
        print(f"ERROR: directory not found: {args.directory}", file=sys.stderr)
        return 1

    result = scan_directory(args.directory, max_depth=args.max_depth)
    output = json.dumps(result, indent=2) + "\n"

    if args.out:
        args.out.write_text(output)
        print(f"Wrote {args.out}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
