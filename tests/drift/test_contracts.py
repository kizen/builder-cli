"""Offline unit tests for the extraction helpers in ``contracts.py``.

Unlike the rest of ``tests/drift/``, this module never reaches a live
environment — it feeds ``_type_of``/``_shape`` synthetic, OpenAPI-shaped dicts
directly. No ``drift`` marker, no ``KIZEN_DRIFT_PROFILE``; runs in the default
``uv run pytest`` suite.

Covers the ``$ref``-to-bare-enum resolution added for the enum-values-in-the-
snapshot change: a ref to a named enum component embeds its values the same
way an inline enum already did; a ref to a real object schema is unaffected.
"""

from __future__ import annotations

from tests.drift.contracts import _shape, _type_of


def _components() -> dict:
    return {
        "StatusEnum": {
            "type": "string",
            "enum": ["open", "closed"],
            "description": "* `open` - Open\n* `closed` - Closed",
        },
        "WidgetRequest": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
    }


def test_ref_to_bare_enum_embeds_its_values():
    node = {"$ref": "#/components/schemas/StatusEnum"}
    assert _type_of(node, _components()) == "StatusEnum{open,closed}"


def test_ref_to_object_schema_is_unaffected():
    node = {"$ref": "#/components/schemas/WidgetRequest"}
    assert _type_of(node, _components()) == "WidgetRequest"


def test_ref_resolution_is_opt_in_and_backward_compatible():
    """No ``components`` passed => today's behavior, byte-identical."""
    node = {"$ref": "#/components/schemas/StatusEnum"}
    assert _type_of(node) == "StatusEnum"


def test_ref_to_unknown_component_falls_back_to_name_only():
    node = {"$ref": "#/components/schemas/DoesNotExist"}
    assert _type_of(node, _components()) == "DoesNotExist"


def test_enum_component_with_extra_structural_key_is_not_bare():
    """A ref target that merely has an ``enum`` key but is also, say, an
    object with ``properties`` is not a bare enum — only the ref name is
    recorded, exactly as before this change."""
    components = {
        "NotABareEnum": {
            "type": "object",
            "enum": ["a", "b"],
            "properties": {"x": {"type": "string"}},
        },
    }
    node = {"$ref": "#/components/schemas/NotABareEnum"}
    assert _type_of(node, components) == "NotABareEnum"


def test_shape_threads_components_into_nested_properties():
    node = {
        "type": "object",
        "properties": {
            "status": {"$ref": "#/components/schemas/StatusEnum"},
            "widget": {"$ref": "#/components/schemas/WidgetRequest"},
        },
    }
    shape = _shape(node, _components())
    assert shape["properties"]["status"] == "StatusEnum{open,closed}"
    assert shape["properties"]["widget"] == "WidgetRequest"


def test_inline_enum_formatting_is_unchanged():
    """The pre-existing inline-enum branch (no ``$ref``) — untouched by this
    change, asserted so a future edit to the ref branch can't silently also
    change this one."""
    node = {"type": "string", "enum": ["a", "b"]}
    assert _type_of(node, _components()) == "string{a,b}"
