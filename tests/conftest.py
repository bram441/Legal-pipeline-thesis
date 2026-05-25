"""Pytest configuration: IDP integration tests skip when idp_engine is unavailable."""

from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_idp: test needs idp_engine installed (integration)",
    )


def pytest_collection_modifyitems(config, items):
    try:
        import idp_engine  # noqa: F401
    except ImportError:
        skip = pytest.mark.skip(reason="idp_engine not installed")
        for item in items:
            if "requires_idp" in item.keywords:
                item.add_marker(skip)
