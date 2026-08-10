"""SchemaClient: endpoint wiring, name/UUID resolution, caching."""

from __future__ import annotations

import httpx
import pytest
import respx

from kizen_builder.api.client import KizenClient
from kizen_builder.api.schema import SchemaClient
from tests.conftest import FAKE_BASE_URL

OBJ_ID = "7cb5ce29-bf20-4f0f-bdc9-412a8c777ff8"
CONTACTS_ID = "aba65b8f-946a-4113-8b69-cbbfb6257a1f"

OBJECT_LIST = {
    "results": [
        {"id": OBJ_ID, "name": "policies_policy", "object_name": "Policies"},
        {"id": CONTACTS_ID, "name": "client_client", "object_name": "Contacts"},
    ],
    "next": None,
}

FIELDS = [
    {
        "id": "field-1",
        "name": "ftext",
        "field_type": "text",
        "is_default": False,
        "options": [],
    }
]


@pytest.fixture
def schema(env_config):
    with KizenClient(env_config) as client:
        yield SchemaClient(client)


@respx.mock
def test_custom_object_resolves_api_name(schema):
    respx.get(f"{FAKE_BASE_URL}/api/custom-objects").mock(
        return_value=httpx.Response(200, json=OBJECT_LIST)
    )
    obj = schema.custom_object("policies_policy")
    assert obj["id"] == OBJ_ID


@respx.mock
def test_custom_object_unknown_name_lists_available(schema):
    respx.get(f"{FAKE_BASE_URL}/api/custom-objects").mock(
        return_value=httpx.Response(200, json=OBJECT_LIST)
    )
    with pytest.raises(LookupError, match="client_client"):
        schema.custom_object("nope")


@respx.mock
def test_custom_object_uuid_fetches_directly(schema):
    route = respx.get(f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}").mock(
        return_value=httpx.Response(200, json={"id": OBJ_ID, "name": "policies_policy"})
    )
    obj = schema.custom_object(OBJ_ID)
    assert obj["name"] == "policies_policy"
    assert route.call_count == 1


@respx.mock
def test_get_field_uses_settings_search_and_caches(schema):
    respx.get(f"{FAKE_BASE_URL}/api/custom-objects").mock(
        return_value=httpx.Response(200, json=OBJECT_LIST)
    )
    fields_route = respx.get(
        f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}/fields/settings-search"
    ).mock(return_value=httpx.Response(200, json=FIELDS))

    by_name = schema.get_field("policies_policy", "ftext")
    by_id = schema.get_field("policies_policy", "field-1")
    missing = schema.get_field("policies_policy", "nope")

    assert by_name["id"] == "field-1"
    assert by_id["name"] == "ftext"
    assert missing is None
    assert fields_route.call_count == 1  # cached across the three lookups


@respx.mock
def test_field_tags_path_differs_for_contacts(schema):
    respx.get(f"{FAKE_BASE_URL}/api/custom-objects/{OBJ_ID}").mock(
        return_value=httpx.Response(200, json={"id": OBJ_ID, "name": "policies_policy"})
    )
    respx.get(f"{FAKE_BASE_URL}/api/custom-objects/{CONTACTS_ID}").mock(
        return_value=httpx.Response(
            200, json={"id": CONTACTS_ID, "name": "client_client"}
        )
    )
    pipeline_route = respx.get(
        f"{FAKE_BASE_URL}/api/pipelines/{OBJ_ID}/fields/tag-field/tags"
    ).mock(return_value=httpx.Response(200, json={"results": [], "next": None}))
    client_route = respx.get(f"{FAKE_BASE_URL}/api/client/fields/tag-field/tags").mock(
        return_value=httpx.Response(200, json={"results": [], "next": None})
    )

    schema.get_field_tags(OBJ_ID, "tag-field")
    assert pipeline_route.call_count == 1

    schema.get_field_tags(CONTACTS_ID, "tag-field")
    assert client_route.call_count == 1


@respx.mock
def test_all_pages_follows_next_links(schema):
    page2 = f"{FAKE_BASE_URL}/api/subscription-list?page=2"
    respx.get(f"{FAKE_BASE_URL}/api/subscription-list").mock(
        side_effect=[
            httpx.Response(200, json={"results": [{"id": "a"}], "next": page2}),
            httpx.Response(200, json={"results": [{"id": "b"}], "next": None}),
        ]
    )
    lists = schema.get_subscription_lists()
    assert [x["id"] for x in lists] == ["a", "b"]
