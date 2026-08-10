"""Tools for automation-scoped messages (notify_member_via_email step content).

See :mod:`kizen_builder.api.messages` for why this is a separate resource
from the step itself, and why it must be seeded from a real template.
"""

from __future__ import annotations

from typing import Any

from kizen_builder.api import messages as messages_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.automations import get_automation
from kizen_builder.utils import is_uuid


def list_templates() -> list[dict[str, Any]]:
    """List email templates available to base a notify_member_via_email
    step's message on (see `kizen automations messages create`)."""
    config = load_env_config()
    with KizenClient(config) as client:
        return messages_api.list_templates(client)


def resolve_template(client: KizenClient, name_or_id: str) -> dict[str, Any]:
    """Resolve a template name or UUID to its full detail record.

    The list endpoint's items omit ``content``/``craft_json`` (confirmed
    live: a message created from a by-name match 400'd on a blank
    ``content``) — always follow up with a detail GET.
    """
    if is_uuid(name_or_id):
        return messages_api.get_template(client, name_or_id)
    templates = messages_api.list_templates(client)
    matches = [
        t for t in templates if (t.get("name") or "").lower() == name_or_id.lower()
    ]
    if not matches:
        available = [t.get("name") for t in templates]
        raise LookupError(
            f"no email template named '{name_or_id}'. Available: {available}"
        )
    if len(matches) > 1:
        ids = ", ".join(m["id"] for m in matches)
        raise ValueError(f"{len(matches)} templates named '{name_or_id}': {ids}")
    return messages_api.get_template(client, matches[0]["id"])


def create_automation_message(
    automation_api_name: str, template: str
) -> dict[str, Any]:
    """Create an automation-scoped message from an email template, ready to
    reference from a notify_member_via_email step's `email_template_id`.

    ``template`` is a template name or UUID (see :func:`list_templates`).
    Kizen's builder UI "select email" picker only recognizes messages
    created this way (seeded from a real template via ``base_message_id``) —
    a message authored from raw content alone shows as unselected even
    though a step technically references it.
    """
    config = load_env_config()
    with KizenClient(config) as client:
        automation_id = get_automation(automation_api_name)["id"]
        tmpl = resolve_template(client, template)
        created = messages_api.create_automation_message_from_template(
            client, automation_id, tmpl
        )
    return {"env": config.name, "automation_api_name": automation_api_name, **created}
