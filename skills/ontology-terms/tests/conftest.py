"""Pytest fixtures for ontology-terms tests.

Most tests run against artifacts already in the user cache. Network-required
tests are opt-in via the `--network` CLI flag.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CACHE_DIR = Path.home() / ".cache" / "ontology-terms"


def pytest_addoption(parser):
    parser.addoption(
        "--network",
        action="store_true",
        default=False,
        help="run tests that hit live upstream APIs (slow; rate-limited)",
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
def cached_artifacts(cache_dir: Path):
    """All (tsv_path, meta_path, meta_dict) triples currently in the cache."""
    out = []
    if not cache_dir.exists():
        return out
    for tsv in sorted(cache_dir.glob("*.tsv")):
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
def require_any_cache(cached_artifacts):
    if not cached_artifacts:
        pytest.skip(
            "no ontology-terms cached artifacts; run `python scripts/ontology.py "
            "parents GO:0006915` to populate, then re-run tests"
        )
    return cached_artifacts
