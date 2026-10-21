"""Shared test fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def config_dir() -> Path:
    """Absolute path to the project's config/ directory."""
    return Path(__file__).resolve().parent.parent / "config"
