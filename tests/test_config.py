"""Tests for the config loader (topics.yaml / sources.yaml)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from crypto_trendwatching.application.config_loader import load_sources, load_zones
from crypto_trendwatching.domain.models import Source


def test_load_zones_returns_ten_enabled_zones(config_dir: Path) -> None:
    zones = load_zones(config_dir / "topics.yaml")
    assert len(zones) == 10
    assert zones[0].id == "infrastructure"
    assert all(zone.enabled for zone in zones)


def test_load_sources_filters_disabled(config_dir: Path) -> None:
    sources = load_sources(config_dir / "sources.yaml")
    ids = {source.id for source in sources}
    assert "serper" not in ids
    assert "perplexity" not in ids
    assert "theblock" in ids
    assert "cbr" in ids


def test_rss_sources_have_feed_url(config_dir: Path) -> None:
    sources = load_sources(config_dir / "sources.yaml")
    rss_sources = [s for s in sources if s.method == "rss"]
    assert rss_sources
    assert all(s.feed_url for s in rss_sources)


def test_rss_source_without_feed_url_rejected() -> None:
    with pytest.raises(ValidationError):
        Source(
            id="broken",
            name="Broken",
            url="https://example.com/",
            region="EN",
            method="rss",
            availability_from_rf="да",
        )
