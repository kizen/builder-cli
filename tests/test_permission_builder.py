"""Payload construction for permission groups: the leaf enumerator, the two
wire dialects, and the default-group builder.

Pure logic — no HTTP, no client. `enumerate_leaves()` is the one seam every
consumer (the default builder, the randomizer, the CLI table renderer) walks;
these tests exercise it directly against small hand-built group/meta shapes
so both wire dialects (a bare bool vs. `{view, edit, remove}`) are each
pinned down, along with the "container is itself the value" per-field case
`Leaf.current_level` calls out.
"""

from __future__ import annotations

from kizen_builder.tools.permission_builder import (
    Leaf,
    apply_levels,
    build_default_group_payload,
    enumerate_leaves,
    level_index,
)

# ---------------------------------------------------------------------------
# level_index
# ---------------------------------------------------------------------------


def test_level_index_maps_bool_and_string():
    assert level_index(True) == 1  # "view"
    assert level_index(False) == 0  # "none"
    assert level_index(None) == 0
    assert level_index("edit") == 2
    assert level_index("remove") == 3
    assert level_index("not-a-level") == 0


# ---------------------------------------------------------------------------
# the two wire dialects
# ---------------------------------------------------------------------------


def _switch_group_and_meta():
    """A section permission that serializes as a bare bool (a "switch")."""
    meta = {
        "sections": [
            {
                "key": "dashboards_section",
                "label": "Dashboards",
                "permissions": [
                    {
                        "key": "view_all_dashboards",
                        "label": "View All Dashboards",
                        "affordance": "switch",
                        "allowed_access": ["none", "view"],
                        "default": True,
                    }
                ],
            }
        ]
    }
    group = {"dashboards_section": {"enabled": True, "view_all_dashboards": True}}
    return group, meta


def test_bool_dialect_reads_and_writes():
    group, meta = _switch_group_and_meta()
    (leaf,) = [
        lf
        for lf in enumerate_leaves(group, meta)
        if lf.row_key == "view_all_dashboards"
    ]
    assert leaf.current_level == "view"

    leaf.set_level("none")
    assert group["dashboards_section"]["view_all_dashboards"] is False
    assert leaf.current_level == "none"

    leaf.set_level("view")
    assert group["dashboards_section"]["view_all_dashboards"] is True


def _range_group_and_meta():
    """A permission that serializes as `{"view", "edit", "remove"}`."""
    meta = {
        "sections": [
            {
                "key": "automations_section",
                "label": "Automations",
                "permissions": [
                    {
                        "key": "manage_automations",
                        "label": "Manage Automations",
                        "affordance": "range",
                        "allowed_access": ["none", "view", "edit", "remove"],
                        "default": "view",
                    }
                ],
            }
        ]
    }
    group = {
        "automations_section": {
            "enabled": True,
            "manage_automations": {"view": True, "edit": False, "remove": False},
        }
    }
    return group, meta


def test_dict_dialect_reads_and_writes():
    group, meta = _range_group_and_meta()
    (leaf,) = [
        lf for lf in enumerate_leaves(group, meta) if lf.row_key == "manage_automations"
    ]
    assert leaf.current_level == "view"

    leaf.set_level("edit")
    assert group["automations_section"]["manage_automations"] == {
        "view": True,
        "edit": True,
        "remove": False,
    }
    assert leaf.current_level == "edit"

    leaf.set_level("none")
    assert group["automations_section"]["manage_automations"] == {
        "view": False,
        "edit": False,
        "remove": False,
    }


def test_dict_dialect_with_no_wire_key_preserves_sibling_keys():
    """A per-field slot where the leaf's container *is* the value (no
    surrounding wire key) — e.g. a custom-object field `{id, view, edit}`.
    `set_level` must mutate the dialect keys in place without touching `id`."""
    field = {"id": "field-1", "view": True, "edit": False}
    leaf = Leaf(
        area="field",
        block_key="obj-1",
        block_label="object:obj-1",
        category="custom_fields",
        row_key="field-1",
        row_label="field-1",
        affordance="range",
        allowed_access=["none", "view", "edit"],
        _container=field,
        _wire_key=None,
    )
    assert leaf.current_level == "view"

    leaf.set_level("edit")

    assert field == {"id": "field-1", "view": True, "edit": True}


# ---------------------------------------------------------------------------
# enumerate_leaves structure
# ---------------------------------------------------------------------------


def _full_template():
    meta = {
        "order": [
            "dashboards_section",
            "automations_section",
            "custom_object_entities",
            "contacts_section",
        ],
        "sections": [
            {
                "key": "dashboards_section",
                "label": "Dashboards",
                "default": True,
                "permissions": [
                    {
                        "key": "view_all_dashboards",
                        "label": "View All Dashboards",
                        "affordance": "switch",
                        "allowed_access": ["none", "view"],
                        "default": True,
                    }
                ],
            },
            {
                # present in meta but never appears on the group -> no leaves
                "key": "unused_section",
                "label": "Unused",
                "permissions": [],
            },
        ],
        "custom_objects": [
            {
                "key": "records",
                "label": "Records",
                "affordance": "range",
                "allowed_access": ["none", "view", "edit", "remove"],
                "default": "view",
            }
        ],
        "contacts": [
            {
                "key": "records",
                "label": "Records",
                "affordance": "range",
                "allowed_access": ["none", "view", "edit", "remove"],
                "default": "view",
            }
        ],
        "default_contact_fields": {
            "email": {"allowed_access": ["none", "view", "edit"], "default": "edit"},
        },
        "default_custom_object_fields": {},
    }
    group = {
        "id": "group-1",
        "name": "Template",
        "summary": {"nb_none": 0},
        "user_count": 3,
        "role_count": 1,
        "created": "2026-01-01",
        "updated": "2026-01-01",
        "dashboards_section": {"enabled": True, "view_all_dashboards": True},
        # on the group but absent from meta.sections -> skipped, not raised
        "stray_section": {"enabled": True},
        "contacts_section": {
            "records": {"view": True, "edit": False, "remove": False},
            "default_fields": {"email": {"view": True, "edit": True}},
            "custom_fields": [{"id": "cf-1", "view": True, "edit": False}],
        },
        "custom_objects": [
            {
                "custom_object_id": "obj-1",
                "records": {"view": True, "edit": False, "remove": False},
                "fields": [{"id": "of-1", "view": True, "edit": True}],
            }
        ],
    }
    return group, meta


def test_enumerate_leaves_covers_sections_contacts_and_objects_without_fields():
    group, meta = _full_template()
    leaves = list(enumerate_leaves(group, meta, include_fields=False))
    areas = {leaf.area for leaf in leaves}
    assert areas == {"section", "contacts", "object"}
    # a group section with no meta descriptor is skipped, not an error
    assert not any(leaf.block_key == "stray_section" for leaf in leaves)
    # a meta section absent from the group yields nothing
    assert not any(leaf.block_key == "unused_section" for leaf in leaves)
    assert not any(leaf.area == "field" for leaf in leaves)


def test_enumerate_leaves_includes_field_leaves_when_requested():
    group, meta = _full_template()
    leaves = list(enumerate_leaves(group, meta, include_fields=True))
    field_rows = {leaf.row_key for leaf in leaves if leaf.area == "field"}
    assert field_rows == {"email", "cf-1", "of-1"}


# ---------------------------------------------------------------------------
# apply_levels: snapping a disallowed chosen level to what's actually allowed
# ---------------------------------------------------------------------------


def test_apply_levels_snaps_disallowed_level_down_to_nearest_allowed():
    group, meta = _switch_group_and_meta()  # allowed_access is ["none", "view"]
    apply_levels(group, meta, lambda leaf: "remove")
    assert (
        group["dashboards_section"]["view_all_dashboards"] is True
    )  # snapped to "view"


def test_apply_levels_falls_back_to_lowest_allowed_when_nothing_is_at_or_below():
    group, meta = _range_group_and_meta()
    meta["sections"][0]["permissions"][0]["allowed_access"] = ["view", "edit"]
    apply_levels(group, meta, lambda leaf: "none")
    # nothing at-or-below "none" is allowed -> falls back to allowed_access[0]
    assert group["automations_section"]["manage_automations"] == {
        "view": True,
        "edit": False,
        "remove": False,
    }


# ---------------------------------------------------------------------------
# build_default_group_payload
# ---------------------------------------------------------------------------


def test_build_default_group_payload_strips_server_keys_and_renames():
    group, meta = _full_template()
    payload = build_default_group_payload("New Group", group, meta)

    assert payload["name"] == "New Group"
    for key in ("id", "summary", "user_count", "role_count", "created", "updated"):
        assert key not in payload
    # the source template is untouched
    assert group["name"] == "Template"
    assert "id" in group


def test_build_default_group_payload_applies_meta_defaults():
    group, meta = _full_template()
    payload = build_default_group_payload("New Group", group, meta)

    # section default True (bool) -> highest non-none allowed level, "view"
    assert payload["dashboards_section"]["view_all_dashboards"] is True
    # contacts + custom object capability default "view" (string) -> used as-is
    assert payload["contacts_section"]["records"] == {
        "view": True,
        "edit": False,
        "remove": False,
    }
    assert payload["custom_objects"][0]["records"] == {
        "view": True,
        "edit": False,
        "remove": False,
    }
    # default_contact_fields default "edit" (string) applies to the field leaf
    assert payload["contacts_section"]["default_fields"]["email"] == {
        "view": True,
        "edit": True,
    }


def test_coerce_default_bool_false_means_none():
    # Section keys must end in "_section" or `_section_leaves` skips them.
    meta = {
        "sections": [
            {
                "key": "sec_section",
                "label": "Sec",
                "permissions": [
                    {
                        "key": "flag",
                        "label": "Flag",
                        "affordance": "switch",
                        "allowed_access": ["none", "view"],
                        "default": False,
                    }
                ],
            }
        ]
    }
    group = {"sec_section": {"flag": True}}
    payload = build_default_group_payload("New", group, meta)
    assert payload["sec_section"]["flag"] is False


def test_coerce_default_falls_back_to_first_allowed_for_unrecognized_default():
    meta = {
        "sections": [
            {
                "key": "sec_section",
                "label": "Sec",
                "permissions": [
                    {
                        "key": "flag",
                        "label": "Flag",
                        "affordance": "range",
                        "allowed_access": ["view", "edit"],
                        "default": "unexpected-value",
                    }
                ],
            }
        ]
    }
    group = {"sec_section": {"flag": {"view": False, "edit": False}}}
    payload = build_default_group_payload("New", group, meta)
    # "unexpected-value" isn't a level name, so it falls back to allowed[0]
    assert payload["sec_section"]["flag"] == {"view": True, "edit": False}
