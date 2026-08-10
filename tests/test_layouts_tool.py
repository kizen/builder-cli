"""tools/layouts.py and api/layouts.py: the block builders, the read layer
(`list_layouts` / `get_layout`), and the id-injection walk.

`_fetch_layouts` calls `get_object` and then builds its own `KizenClient`, so
these go through respx against `FAKE_BASE_URL` with `get_object` monkeypatched
directly — the same live-lookup seam `patch_live_lookups` uses for planners,
and the same split `tests/test_saved_views_tool.py` makes (that object
list/categories/fields chain is already covered by test_objects_tool.py).

`custom_content_block` is covered by tests/test_layout_custom_content.py and
the planner by tests/test_dashboard_layout_payloads.py; neither is re-asserted
here.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from kizen_builder.api import layouts as layout_api
from kizen_builder.api.client import KizenClient
from kizen_builder.tools import layouts as layout_tools
from tests.conftest import FAKE_BASE_URL

OBJ_ID = "00000000-0000-4000-8000-0000000001a0"
LAYOUT_ID = "00000000-0000-4000-8000-0000000001a1"
LAYOUT_ID_2 = "00000000-0000-4000-8000-0000000001a2"
CAT_A = "00000000-0000-4000-8000-0000000001b1"
CAT_B = "00000000-0000-4000-8000-0000000001b2"
CAT_C = "00000000-0000-4000-8000-0000000001b3"

LAYOUT_CONFIG = [
    {
        "columns": [
            {
                "width": "half-width",
                "items": [
                    {
                        "type": "fields",
                        "internalName": "Vitals",
                        "displayName": "",
                        "metadata": {"autoInclude": False, "included": [CAT_A]},
                    }
                ],
            },
            {"width": "half-width", "items": [{"type": "timeline"}]},
        ]
    }
]

STANDARD_VIEW = {
    "id": LAYOUT_ID,
    "name": "Standard View",
    "active": True,
    "order": 0.0,
    "config": LAYOUT_CONFIG,
}


@pytest.fixture
def fake_object(monkeypatch):
    monkeypatch.setattr(layout_tools, "get_object", lambda api_name: {"id": OBJ_ID})


@pytest.fixture
def client(env_config):
    with KizenClient(env_config) as c:
        yield c


def _mock_layout_list(body=None):
    return respx.get(f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/layouts").mock(
        return_value=httpx.Response(
            200, json=body if body is not None else {"results": [STANDARD_VIEW]}
        )
    )


# ---------------------------------------------------------------------------
# explicit_block
# ---------------------------------------------------------------------------


def test_explicit_block_pairs_labels_with_category_ids_in_order():
    block = layout_tools.explicit_block("Vitals", [CAT_A, CAT_B], ["A", "B"])
    assert block["type"] == "fields"
    assert block["internalName"] == "Vitals"
    assert block["displayName"] == ""
    meta = block["metadata"]
    assert meta["autoInclude"] is False
    assert meta["included"] == [CAT_A, CAT_B]
    assert meta["excluded"] == []
    assert meta["chosenCategories"] == [
        {"label": "A", "value": CAT_A},
        {"label": "B", "value": CAT_B},
    ]


def test_explicit_block_generates_a_unique_id_per_call():
    a = layout_tools.explicit_block("X", [CAT_A], ["A"])
    b = layout_tools.explicit_block("X", [CAT_A], ["A"])
    assert a["id"] != b["id"]


def test_explicit_block_display_name_override():
    block = layout_tools.explicit_block("X", [CAT_A], ["A"], display_name="Shown")
    assert block["displayName"] == "Shown"


def test_explicit_block_copies_cat_ids_rather_than_aliasing_the_caller_list():
    """`included` is built with list(), so mutating the caller's list
    afterwards must not retroactively change an already-built block."""
    cat_ids = [CAT_A]
    block = layout_tools.explicit_block("X", cat_ids, ["A"])
    cat_ids.append(CAT_B)
    assert block["metadata"]["included"] == [CAT_A]


def test_explicit_block_mismatched_lengths_raise_value_error():
    with pytest.raises(ValueError, match="same length .*got 2 and 1"):
        layout_tools.explicit_block("X", [CAT_A, CAT_B], ["A"])


# ---------------------------------------------------------------------------
# auto_block
# ---------------------------------------------------------------------------


def test_auto_block_excludes_every_category_except_the_shown_one():
    """auto_block's whole point is picking up newly-added fields, so it
    auto-includes and derives `excluded` from the full category list."""
    block = layout_tools.auto_block("Supplies", CAT_B, "B", [CAT_A, CAT_B, CAT_C])
    meta = block["metadata"]
    assert meta["autoInclude"] is True
    assert meta["included"] == []
    assert meta["excluded"] == [CAT_A, CAT_C]
    assert meta["chosenCategories"] == [{"label": "B", "value": CAT_B}]


def test_auto_block_excluded_is_empty_when_shown_is_the_only_category():
    block = layout_tools.auto_block("Only", CAT_A, "A", [CAT_A])
    assert block["metadata"]["excluded"] == []


def test_auto_block_tolerates_a_shown_id_absent_from_the_full_list():
    block = layout_tools.auto_block("X", CAT_C, "C", [CAT_A, CAT_B])
    assert block["metadata"]["excluded"] == [CAT_A, CAT_B]


# ---------------------------------------------------------------------------
# api.layouts — envelope normalization is the whole uncovered block
# ---------------------------------------------------------------------------


@respx.mock
def test_api_list_layouts_unwraps_a_drf_results_envelope(client):
    _mock_layout_list()
    assert layout_api.list_layouts(client, OBJ_ID) == [STANDARD_VIEW]


@respx.mock
def test_api_list_layouts_accepts_a_bare_list(client):
    _mock_layout_list(body=[STANDARD_VIEW])
    assert layout_api.list_layouts(client, OBJ_ID) == [STANDARD_VIEW]


@respx.mock
def test_api_list_layouts_returns_empty_for_an_unrecognized_envelope(client):
    """Anything that is neither a `results` dict nor a list degrades to an
    empty list rather than propagating a shape the callers can't walk."""
    _mock_layout_list(body={"detail": "unexpected"})
    assert layout_api.list_layouts(client, OBJ_ID) == []


@respx.mock
def test_api_update_layout_puts_to_the_untrailing_slashed_path(client):
    route = respx.put(
        f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/layouts/{LAYOUT_ID}"
    ).mock(return_value=httpx.Response(200, json={"id": LAYOUT_ID}))
    out = layout_api.update_layout(client, OBJ_ID, LAYOUT_ID, {"name": "X"})
    assert out == {"id": LAYOUT_ID}
    assert route.call_count == 1
    assert route.calls[0].request.url.path.endswith(f"/layouts/{LAYOUT_ID}")


# ---------------------------------------------------------------------------
# list_layouts
# ---------------------------------------------------------------------------


@respx.mock
def test_list_layouts_summarizes_each_layout_with_a_block_count(fake_object):
    _mock_layout_list()
    assert layout_tools.list_layouts("patients") == [
        {
            "id": LAYOUT_ID,
            "name": "Standard View",
            "active": True,
            "order": 0.0,
            "block_count": 2,
        }
    ]


@respx.mock
def test_list_layouts_returns_empty_when_the_object_has_none(fake_object):
    _mock_layout_list(body={"results": []})
    assert layout_tools.list_layouts("patients") == []


# ---------------------------------------------------------------------------
# get_layout
# ---------------------------------------------------------------------------


@respx.mock
def test_get_layout_defaults_to_the_first_layout(fake_object):
    _mock_layout_list(
        body={"results": [STANDARD_VIEW, {"id": LAYOUT_ID_2, "name": "Other"}]}
    )
    out = layout_tools.get_layout("patients")
    assert out["id"] == LAYOUT_ID
    assert out["name"] == "Standard View"
    assert out["config"] == LAYOUT_CONFIG
    assert out["raw"] == STANDARD_VIEW


@respx.mock
def test_get_layout_by_name_selects_the_matching_one(fake_object):
    _mock_layout_list(
        body={
            "results": [
                STANDARD_VIEW,
                {"id": LAYOUT_ID_2, "name": "Other", "config": []},
            ]
        }
    )
    out = layout_tools.get_layout("patients", "Other")
    assert out["id"] == LAYOUT_ID_2
    assert out["blocks"] == []


@respx.mock
def test_get_layout_summarizes_blocks_with_position_and_metadata(fake_object):
    _mock_layout_list()
    blocks = layout_tools.get_layout("patients")["blocks"]
    assert blocks == [
        {
            "group": 0,
            "column": 0,
            "width": "half-width",
            "type": "fields",
            "internalName": "Vitals",
            "displayName": "",
            "autoInclude": False,
            "included": [CAT_A],
        },
        {
            "group": 0,
            "column": 1,
            "width": "half-width",
            "type": "timeline",
            "internalName": None,
            "displayName": None,
            "autoInclude": None,
            "included": None,
        },
    ]


@respx.mock
def test_get_layout_defaults_name_when_the_record_omits_it(fake_object):
    _mock_layout_list(body={"results": [{"id": LAYOUT_ID}]})
    out = layout_tools.get_layout("patients")
    assert out["name"] == "Standard View"
    assert out["config"] == []


@respx.mock
def test_get_layout_raises_when_the_object_has_no_layouts(fake_object):
    _mock_layout_list(body={"results": []})
    with pytest.raises(LookupError, match="no layouts found for object 'patients'"):
        layout_tools.get_layout("patients")


@respx.mock
def test_get_layout_unknown_name_lists_what_is_available(fake_object):
    _mock_layout_list()
    with pytest.raises(LookupError, match="no layout named 'Nope'"):
        layout_tools.get_layout("patients", "Nope")


# ---------------------------------------------------------------------------
# inject_layout_ids
# ---------------------------------------------------------------------------


def test_inject_layout_ids_fills_every_nesting_level():
    config = [{"columns": [{"items": [{"type": "fields"}, {"type": "timeline"}]}]}]
    out = layout_tools.inject_layout_ids(config)
    assert out is config  # documented as in-place
    (group,) = out
    assert "id" in group
    for column in group["columns"]:
        assert "id" in column
        for item in column["items"]:
            assert "id" in item


def test_inject_layout_ids_preserves_ids_that_already_exist():
    """Re-saving a layout must not renumber it — the API keys off these ids,
    so regenerating them would orphan the existing blocks."""
    config = [
        {
            "id": "group-1",
            "columns": [{"id": "col-1", "items": [{"id": "item-1"}, {}]}],
        }
    ]
    out = layout_tools.inject_layout_ids(config)
    assert out[0]["id"] == "group-1"
    assert out[0]["columns"][0]["id"] == "col-1"
    items = out[0]["columns"][0]["items"]
    assert items[0]["id"] == "item-1"
    assert "id" in items[1] and items[1]["id"] != "item-1"


def test_inject_layout_ids_handles_missing_columns_and_items_keys():
    config = [{}, {"columns": [{}]}]
    out = layout_tools.inject_layout_ids(config)
    assert all("id" in group for group in out)
    assert "id" in out[1]["columns"][0]


def test_inject_layout_ids_on_empty_config_is_a_noop():
    assert layout_tools.inject_layout_ids([]) == []
