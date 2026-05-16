"""Pytest configuration for citation-validator tests."""
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--network", action="store_true", default=False,
        help="run tests that query the CrossRef API",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--network"):
        return
    skip = pytest.mark.skip(reason="requires --network (live CrossRef queries)")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
