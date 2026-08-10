"""api/external_refs.py: thin httpx wrappers for external-reference lookups
(email templates, activity types, tags, forms, surveys) that `kizen lookup`
uses to populate name->UUID caches for automation-spec references.

Exercises the shared `_paginate()` helper across its three response shapes
(DRF `{results, next}` envelope, a followed `next` link, a bare list, and an
unrecognized shape) plus each `list_*` function's endpoint path — the module
was at 0% coverage (31/31 statements missed) before this file.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from kizen_builder.api import external_refs
from kizen_builder.api.client import KizenClient
from tests.conftest import FAKE_BASE_URL


@pytest.fixture
def client(env_config):
    with KizenClient(env_config) as c:
        yield c


@respx.mock
def test_paginate_single_page_dict_envelope(client):
    respx.get(f"{FAKE_BASE_URL}/api/emails/templates").mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": "1", "name": "Welcome"}], "next": None}
        )
    )
    out = external_refs.list_email_templates(client)
    assert out == [{"id": "1", "name": "Welcome"}]


@respx.mock
def test_paginate_follows_next_link_across_pages(client):
    respx.get(f"{FAKE_BASE_URL}/api/activities").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [{"id": "1"}],
                    "next": "https://kizen.test/api/activities?page=2",
                },
            ),
            httpx.Response(200, json={"results": [{"id": "2"}], "next": None}),
        ]
    )
    out = external_refs.list_activity_types(client)
    assert [i["id"] for i in out] == ["1", "2"]


@respx.mock
def test_paginate_bare_list_response(client):
    respx.get(f"{FAKE_BASE_URL}/api/tags").mock(
        return_value=httpx.Response(200, json=[{"id": "1", "name": "vip"}])
    )
    out = external_refs.list_tags(client)
    assert out == [{"id": "1", "name": "vip"}]


@respx.mock
def test_paginate_unrecognized_shape_returns_empty(client):
    respx.get(f"{FAKE_BASE_URL}/api/forms").mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )
    out = external_refs.list_forms(client)
    assert out == []


@respx.mock
def test_paginate_empty_results_page_stops(client):
    respx.get(f"{FAKE_BASE_URL}/api/forms").mock(
        return_value=httpx.Response(200, json={"results": [], "next": None})
    )
    out = external_refs.list_forms(client)
    assert out == []


@respx.mock
def test_list_surveys_hits_surveys_endpoint(client):
    route = respx.get(f"{FAKE_BASE_URL}/api/surveys").mock(
        return_value=httpx.Response(200, json={"results": [], "next": None})
    )
    external_refs.list_surveys(client)
    assert route.called


@respx.mock
def test_list_forms_hits_forms_endpoint(client):
    route = respx.get(f"{FAKE_BASE_URL}/api/forms").mock(
        return_value=httpx.Response(200, json=[])
    )
    external_refs.list_forms(client)
    assert route.called


@respx.mock
def test_list_email_templates_hits_email_templates_endpoint(client):
    route = respx.get(f"{FAKE_BASE_URL}/api/emails/templates").mock(
        return_value=httpx.Response(200, json=[])
    )
    external_refs.list_email_templates(client)
    assert route.called


@respx.mock
def test_list_activity_types_hits_activities_endpoint(client):
    route = respx.get(f"{FAKE_BASE_URL}/api/activities").mock(
        return_value=httpx.Response(200, json=[])
    )
    external_refs.list_activity_types(client)
    assert route.called


@respx.mock
def test_list_tags_hits_tags_endpoint(client):
    route = respx.get(f"{FAKE_BASE_URL}/api/tags").mock(
        return_value=httpx.Response(200, json=[])
    )
    external_refs.list_tags(client)
    assert route.called
