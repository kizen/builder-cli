"""Fetch external entity name→UUID mappings from the Kizen API.

These are entities referenced by name in automation specs (email templates,
activity types, tags, forms, surveys) that aren't tracked by the main
custom-object state. `kizen lookup` populates these caches.

NOTE: Several endpoint paths below need verification against the live Kizen API
or its full OpenAPI spec. Run `kizen lookup --dry-run` to test connectivity and
adjust paths if you get 404s.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from kizen_builder.api.client import KizenClient


def _paginate(client: KizenClient, path: str) -> list[dict[str, Any]]:
    """Transparently paginate a DRF-style list endpoint."""
    items: list[dict[str, Any]] = []
    current: str | None = path
    while current:
        resp = client.get(current)
        if isinstance(resp, dict) and "results" in resp:
            items.extend(resp["results"])
            nxt = resp.get("next")
            if nxt:
                parts = urlsplit(nxt)
                current = parts.path + (f"?{parts.query}" if parts.query else "")
            else:
                current = None
        elif isinstance(resp, list):
            items.extend(resp)
            current = None
        else:
            break
    return items


def list_email_templates(client: KizenClient) -> list[dict[str, Any]]:
    """List all email templates. Returns dicts with 'id' and 'name'/'title' fields.

    Endpoint needs verification — common candidates:
      GET /api/emails/templates
      GET /api/email-templates
    """
    return _paginate(client, "/api/emails/templates")


def list_activity_types(client: KizenClient) -> list[dict[str, Any]]:
    """List all activity types/categories. Returns dicts with 'id' and 'name'.

    Endpoint needs verification — common candidates:
      GET /api/activities
      GET /api/activity-types
    """
    return _paginate(client, "/api/activities")


def list_tags(client: KizenClient) -> list[dict[str, Any]]:
    """List all contact tags. Returns dicts with 'id' and 'name'.

    Endpoint needs verification — common candidates:
      GET /api/tags
      GET /api/client/tags
    """
    return _paginate(client, "/api/tags")


def list_forms(client: KizenClient) -> list[dict[str, Any]]:
    """List all forms. Returns dicts with 'id' and 'name'.

    Endpoint needs verification — common candidates:
      GET /api/forms
      GET /api/activities (activity type = form)
    """
    return _paginate(client, "/api/forms")


def list_surveys(client: KizenClient) -> list[dict[str, Any]]:
    """List all surveys. Returns dicts with 'id' and 'name'.

    Endpoint needs verification — common candidates:
      GET /api/surveys
      GET /api/activities (activity type = survey)
    """
    return _paginate(client, "/api/surveys")
