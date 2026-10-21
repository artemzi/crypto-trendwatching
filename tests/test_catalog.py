"""Tests for the stable source catalog numbering."""

from crypto_trendwatching.application.catalog import (
    build_catalog,
    catalog_snapshot,
    resolve_number,
)
from crypto_trendwatching.domain.models import Source


def _source(source_id: str) -> Source:
    return Source(
        id=source_id,
        name=source_id.upper(),
        url=f"https://{source_id}.example.com/",
        region="EN",
        method="fetch_url",
        availability_from_rf="да",
    )


def test_build_catalog_follows_config_order() -> None:
    catalog = build_catalog([_source("a"), _source("b"), _source("c")])
    assert catalog["a"].number == 1
    assert catalog["b"].number == 2
    assert catalog["c"].number == 3
    assert catalog["b"].url == "https://b.example.com/"


def test_resolve_number_handles_unknown_and_none() -> None:
    catalog = build_catalog([_source("a")])
    assert resolve_number(catalog, "a") == 1
    assert resolve_number(catalog, "zzz") is None
    assert resolve_number(catalog, None) is None


def test_catalog_snapshot_is_sorted_by_number() -> None:
    catalog = build_catalog([_source("c"), _source("a"), _source("b")])
    snapshot = catalog_snapshot(catalog)
    assert [entry["number"] for entry in snapshot] == [1, 2, 3]
    assert [entry["source_id"] for entry in snapshot] == ["c", "a", "b"]
