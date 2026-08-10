"""Planners — produce :class:`Plan`s for mutations, never call the API directly.

Every tool in this package follows the pattern::

    def plan_<verb>(env, ...inputs) -> Plan:
        # 1. Pull live state from `env` to check current reality
        # 2. Validate inputs against live state
        # 3. Build one or more PlanOperation(s)
        # 4. Return a Plan

The :class:`Plan` is JSON-serializable and is what gets shown to the user
for approval. Execution happens later via :func:`tools.plans.apply_plan`.

This module's tools never write to Kizen on their own. The only path that
mutates is ``apply_plan`` on a Plan that the user has approved.
"""

from kizen_builder.tools.planners.automations import (
    plan_create_automation,
    plan_update_automation,
)
from kizen_builder.tools.planners.fields import plan_create_field, plan_update_field
from kizen_builder.tools.planners.objects import (
    plan_create_category,
    plan_create_object,
    plan_update_category,
    plan_update_object,
)

__all__ = [
    "plan_create_field",
    "plan_update_field",
    "plan_create_object",
    "plan_update_object",
    "plan_create_category",
    "plan_update_category",
    "plan_create_automation",
    "plan_update_automation",
]
