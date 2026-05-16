"""Pytest fixtures for gene-statistics tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CACHE_DIR = Path.home() / ".cache" / "gene-statistics"


def pytest_addoption(parser):
    parser.addoption(
        "--network", action="store_true", default=False,
        help="run tests that recompute against live upstream files",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--network"):
        return
    skip_network = pytest.mark.skip(reason="requires --network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)


@pytest.fixture(scope="session")
def cache_dir() -> Path:
    return CACHE_DIR


@pytest.fixture(scope="session")
def mf_artifacts(cache_dir: Path):
    """All (tsv, meta_path, meta_dict) triples for multifunctionality outputs."""
    out = []
    if not cache_dir.exists():
        return out
    for tsv in sorted(cache_dir.glob("multifunctionality__*.tsv")):
        meta_path = tsv.with_suffix(".meta.json")
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        out.append((tsv, meta_path, meta))
    return out


@pytest.fixture()
def require_mf_artifact(mf_artifacts):
    if not mf_artifacts:
        pytest.skip(
            "no multifunctionality artifacts in cache; run "
            "`python scripts/multifunctionality.py` first"
        )
    return mf_artifacts
