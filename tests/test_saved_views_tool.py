"""tools/saved_views.py: the read layer for filter groups, quick filters, and
column templates — `resolve_object_id`, `list_saved_views`, and
`find_saved_view`'s UUID-vs-name resolution (including the "list is leaner
than detail" defensive re-fetch documented in
`docs/specs/saved-views.md`'s wire-format section).

`get_object` is monkeypatched directly (the same live-lookup seam
`patch_live_lookups` in conftest.py uses for other planners) rather than
respx-mocking its whole list/categories/fields chain — that chain is already
covered by test_objects_tool.py. Only the saved-view endpoints themselves are
respx-mocked here.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from kizen_builder.tools import saved_views as sv_tools
from tests.conftest import FAKE_BASE_URL

OBJ_ID = "ceed733b-9dd9-4bf9-8c52-8ba1ac41da45"
FG_ID = "00000000-0000-4000-8000-000000000fb1"


@pytest.fixture(autouse=True)
def fake_object(monkeypatch):
    monkeypatch.setattr(sv_tools, "get_object", lambda api_name: {"id": OBJ_ID})


def test_resolve_object_id_returns_uuid():
    assert sv_tools.resolve_object_id("patients") == OBJ_ID


@respx.mock
def test_list_saved_views_resolves_object_then_lists():
    route = respx.get(
        f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/filter-groups"
    ).mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": FG_ID}], "next": None}
        )
    )
    out = sv_tools.list_saved_views("patients", "filter-groups")
    assert out == [{"id": FG_ID}]
    assert route.call_count == 1


@respx.mock
def test_list_saved_views_passes_search_and_ordering():
    route = respx.get(
        f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/quick-filters"
    ).mock(return_value=httpx.Response(200, json={"results": [], "next": None}))
    sv_tools.list_saved_views(
        "patients", "quick-filters", search="open", ordering="-name"
    )
    request = route.calls[0].request
    assert request.url.params["search"] == "open"
    assert request.url.params["ordering"] == "-name"


@respx.mock
def test_find_saved_view_by_uuid_gets_directly():
    route = respx.get(
        f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/filter-groups/{FG_ID}"
    ).mock(return_value=httpx.Response(200, json={"id": FG_ID, "name": "Big deals"}))
    view = sv_tools.find_saved_view("patients", "filter-groups", FG_ID)
    assert view["name"] == "Big deals"
    assert route.call_count == 1


@respx.mock
def test_find_saved_view_by_name_lists_then_gets_full_detail():
    """A name match against the (leaner) list response is followed by one
    more GET-by-id for full detail — the list item alone isn't trusted."""
    list_route = respx.get(
        f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/filter-groups"
    ).mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": FG_ID, "name": "Big deals"}], "next": None}
        )
    )
    detail_route = respx.get(
        f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/filter-groups/{FG_ID}"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": FG_ID,
                "name": "Big deals",
                "owner": None,
                "hidden": False,
                "sharing_settings": {},
            },
        )
    )
    view = sv_tools.find_saved_view("patients", "filter-groups", "Big deals")
    assert view["sharing_settings"] == {}
    assert list_route.call_count == 1
    assert detail_route.call_count == 1


@respx.mock
def test_find_saved_view_by_name_not_found_raises():
    respx.get(f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/filter-groups").mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": FG_ID, "name": "Other"}], "next": None}
        )
    )
    with pytest.raises(LookupError, match="no saved view named 'Big deals'"):
        sv_tools.find_saved_view("patients", "filter-groups", "Big deals")


@respx.mock
def test_find_saved_view_by_name_ambiguous_raises():
    other_id = "00000000-0000-4000-8000-000000000fb2"
    respx.get(f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/filter-groups").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": FG_ID, "name": "Dup"},
                    {"id": other_id, "name": "Dup"},
                ],
                "next": None,
            },
        )
    )
    with pytest.raises(LookupError, match="matches 2 saved views"):
        sv_tools.find_saved_view("patients", "filter-groups", "Dup")


def test_looks_like_uuid():
    assert sv_tools._looks_like_uuid(FG_ID) is True
    assert sv_tools._looks_like_uuid("Big deals") is False
