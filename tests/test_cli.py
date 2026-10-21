"""Tests for the CLI entry point."""

from pathlib import Path

import pytest

from crypto_trendwatching.cli import main
from crypto_trendwatching.config import settings


def test_run_unknown_zone_exits(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "config_dir", config_dir)
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "--zone", "no_such_zone"])
    assert excinfo.value.code == 1


def test_run_zone_and_all_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "--zone", "infrastructure", "--all"])
    assert excinfo.value.code == 2
