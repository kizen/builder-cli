"""Records API: search pagination/limit behavior and request shapes.

Regression context: `records list <obj> -n 3` used to walk the ENTIRE object
in pages of 3 because search_records paginated to completion regardless of
how many results the caller wanted.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from kizen_builder.api import records as records_api
from kizen_builder.api.client import KizenClient
from tests.conftest import FAKE_BASE_URL, load_fixture

SEARCH_URL = f"{FAKE_BASE_URL}/api/records/tax_lot/search"


@pytest.fixture
def client(env_config):
    with KizenClient(env_config) as c:
        yield c


def _page(results, next_url=None, count=None):
    return {
        "results": results,
        "next": next_url,
        "count": count if count is not None else len(results),
    }


@respx.mock
def test_search_stops_paginating_at_limit(client):
    """With limit=3 and page_size=3, exactly one request should be enough."""
    records = [{"id": f"r{i}", "name": f"rec {i}"} for i in range(3)]
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json=_page(records, next_url="https://kizen.test/page2", count=5000)
        )
    )
    out = records_api.search_records(client, "tax_lot", page_size=3, limit=3)
    assert len(out) == 3
    assert route.call_count == 1


@respx.mock
def test_search_paginates_until_limit(client):
    pages = [
        _page([{"id": "a"}, {"id": "b"}], next_url="x", count=5),
        _page([{"id": "c"}, {"id": "d"}], next_url="y", count=5),
        _page([{"id": "e"}], next_url=None, count=5),
    ]
    route = respx.post(SEARCH_URL).mock(
        side_effect=[httpx.Response(200, json=p) for p in pages]
    )
    out = records_api.search_records(client, "tax_lot", page_size=2, limit=3)
    # The last page may overshoot the limit (callers truncate); the point is
    # that pagination STOPS once enough records are in hand.
    assert [r["id"] for r in out] == ["a", "b", "c", "d"]
    assert route.call_count == 2  # third page never fetched


@respx.mock
def test_search_no_limit_fetches_all_pages(client):
    pages = [
        _page([{"id": "a"}], next_url="x", count=2),
        _page([{"id": "b"}], next_url=None, count=2),
    ]
    route = respx.post(SEARCH_URL).mock(
        side_effect=[httpx.Response(200, json=p) for p in pages]
    )
    out = records_api.search_records(client, "tax_lot", page_size=1)
    assert [r["id"] for r in out] == ["a", "b"]
    assert route.call_count == 2


@respx.mock
def test_search_body_wraps_filter_groups(client):
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_page([]))
    )
    groups = [{"and": True, "filters": [{"type": "fields_v2", "condition": "="}]}]
    records_api.search_records(client, "tax_lot", filters=groups)
    body = json.loads(route.calls.last.request.content)
    assert body == {"query": groups, "and": True}


@respx.mock
def test_search_text_param_forwarded(client):
    route = respx.post(SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_page([]))
    )
    records_api.search_records(client, "tax_lot", search="main st")
    url = route.calls.last.request.url
    assert url.params["search"] == "main st"


@respx.mock
def test_get_record_includes_hidden_fields(client):
    fixture = load_fixture("records/get_tax_lot.json")
    route = respx.get(f"{FAKE_BASE_URL}/api/records/tax_lot/abc-123").mock(
        return_value=httpx.Response(200, json=fixture)
    )
    out = records_api.get_record(client, "tax_lot", "abc-123")
    assert route.calls.last.request.url.params["include_hidden_fields"] == "true"
    assert out == fixture


def test_tools_layer_truncates_and_forwards_limit(monkeypatch):
    """tools.search_records must pass its limit down so the API layer stops."""
    from kizen_builder.tools import records as record_tools

    seen: dict = {}

    def fake_api_search(
        client, object_identifier, filters=None, search=None, page_size=100, limit=None
    ):
        seen["page_size"] = page_size
        seen["limit"] = limit
        return [{"id": str(i)} for i in range(min(limit or 999, 999))]

    monkeypatch.setattr(record_tools.records_api, "search_records", fake_api_search)
    out = record_tools.search_records("tax_lot", limit=3)
    assert len(out) == 3
    assert seen["limit"] == 3
