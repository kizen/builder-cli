"""Plan creation for automation-scoped messages.

See :mod:`kizen_builder.api.messages` for why notify_member_via_email steps
need a real, template-backed message resource rather than inline content.
"""

from __future__ import annotations

from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.automations import get_automation
from kizen_builder.tools.messages import resolve_template
from kizen_builder.tools.plans import Plan, PlanError, PlanOperation


def plan_create_automation_message(automation_api_name: str, template: str) -> Plan:
    """Plan creating an automation-scoped message from an email template.

    The result's UUID is what a notify_member_via_email step's
    `email_template_id` should reference — Kizen's builder UI "select
    email" picker only recognizes a message seeded from a real template
    (via `base_message_id`) as selected.
    """
    config = load_env_config()
    try:
        automation = get_automation(automation_api_name)
    except LookupError as e:
        raise PlanError(str(e)) from e
    with KizenClient(config) as client:
        try:
            tmpl = resolve_template(client, template)
        except (LookupError, ValueError) as e:
            raise PlanError(str(e)) from e

    payload = {"automation_id": automation["id"], "template": tmpl}
    op = PlanOperation(
        action="create",
        kind="automation_message",
        key=f"{automation_api_name}:{tmpl.get('name')}",
        preview={
            "env": config.name,
            "automation": automation_api_name,
            "template": tmpl.get("name"),
            "template_id": tmpl.get("id"),
            "subject": tmpl.get("subject"),
        },
        payload=payload,
    )
    return Plan.build(
        env=config.name,
        summary=(
            f"Create automation message on '{automation_api_name}' "
            f"from template '{tmpl.get('name')}'"
        ),
        operations=[op],
    )
