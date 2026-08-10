"""JSON filter specs: from_spec compilation, normalization, CLI rendering."""

from __future__ import annotations

import pytest

from kizen_builder.filtering import (
    field_type_ops,
    from_spec,
    normalize_filter_config,
    render_search_filters,
)
from tests.filter_stub import StubClient


def _clauses(spec, obj="policies_policy"):
    groups = render_search_filters(spec, obj, client=StubClient())
    return [c for g in groups for c in g["filters"]]


def test_spec_condition_compiles_and_resolves():
    (clause,) = _clauses({"all": [{"field": "fdropdown", "op": "=", "value": "dd1"}]})
    assert clause["type"] == "fields_v2"
    assert clause["field"].startswith('"custom"::')
    # option label resolved to its uuid
    assert clause["value"] == "82cd3986-8f04-4de3-acde-9c7f96aa73de"


def test_spec_nested_groups():
    groups = render_search_filters(
        {
            "all": [
                {"field": "ftext", "op": "contains", "value": "x"},
                {
                    "any": [
                        {"field": "finteger", "op": ">", "value": 5},
                        {"field": "finteger", "op": "is_blank"},
                    ]
                },
            ]
        },
        "policies_policy",
        client=StubClient(),
    )
    assert len(groups) == 2
    assert groups[0]["and"] is True
    assert groups[1]["and"] is False


def test_spec_no_value_op_rejects_value():
    with pytest.raises(ValueError, match='takes no "value"'):
        from_spec({"field": "ftext", "op": "is_blank", "value": True})


def test_spec_list_op_requires_list():
    with pytest.raises(ValueError, match="requires a list"):
        from_spec({"field": "fdropdown", "op": "is_any_of", "value": "dd1"})


def test_spec_unknown_op_lists_valid_ops():
    with pytest.raises(ValueError, match="Valid ops:"):
        from_spec({"field": "ftext", "op": "regex", "value": "x"})


def test_spec_group_must_be_only_key():
    with pytest.raises(ValueError, match="exactly"):
        from_spec({"all": [], "any": []})


def test_spec_ui_unsupported_condition_rejected():
    """UI-supportability validation still applies to spec-built filters."""
    with pytest.raises(ValueError, match="does not support"):
        _clauses({"all": [{"field": "flongtext", "op": "contains", "value": "x"}]})


def test_raw_query_passes_through():
    raw = {
        "and": True,
        "query": [
            {
                "and": True,
                "filters": [
                    {
                        "type": "fields",
                        "field": "name",
                        "condition": "=",
                        "value": "x",
                        "subtype": "non_custom",
                    }
                ],
            }
        ],
    }
    groups = render_search_filters(raw, "policies_policy", client=StubClient())
    assert groups[0]["filters"][0]["field"] == "name"
    assert groups[0]["id"] == "query-0"  # normalization added the id


# ---------------------------------------------------------------------------
# normalize_filter_config
# ---------------------------------------------------------------------------


def test_normalize_assigns_missing_group_ids_and_keeps_existing():
    cfg = normalize_filter_config(
        {
            "query": [
                {"and": True, "filters": []},
                {"id": "query-custom", "and": False, "filters": []},
            ]
        }
    )
    assert [g["id"] for g in cfg["query"]] == ["query-0", "query-custom"]
    assert cfg["and"] is True
    assert cfg["invalid"] is False


def test_normalize_rejects_null_clause_value():
    with pytest.raises(ValueError, match="null"):
        normalize_filter_config(
            {"query": [{"filters": [{"condition": "is_blank", "value": None}]}]}
        )


def test_normalize_preserves_unknown_clause_keys():
    clause = {
        "type": "variable",
        "lhs_variable_name": "score",
        "condition": "<=",
        "rhs_value": "5",
        "view_model": [],
    }
    cfg = normalize_filter_config({"query": [{"filters": [clause]}]})
    assert cfg["query"][0]["filters"][0] == clause


def test_normalize_rejects_missing_query():
    with pytest.raises(ValueError, match='"query"'):
        normalize_filter_config({"and": True})


def test_field_type_ops_text():
    ops = field_type_ops("text")
    assert "contains" in ops
    assert "starts_with" in ops
    assert "is_any_of" not in ops  # not a text-field op
    assert "is_checked" not in ops  # checkbox-only, must not bleed into text


def test_field_type_ops_checkbox_gets_is_checked_alias():
    ops = field_type_ops("checkbox")
    assert ops == ["=", "is_checked", "not_checked"]


def test_field_type_ops_no_arg_lists_every_field_type():
    all_ops = field_type_ops()
    assert "text" in all_ops
    assert "dropdown" in all_ops
    assert all_ops["text"] == field_type_ops("text")


def test_field_type_ops_unknown_type_lists_valid_choices():
    with pytest.raises(ValueError, match="unknown field_type"):
        field_type_ops("bogus")


def test_field_type_ops_every_listed_op_actually_compiles():
    """Every op field_type_ops() advertises for a type must be usable in a
    real --filter spec against that type — the whole point of deriving this
    from the op tables instead of hand-maintaining a second list."""
    from tests.filter_stub import StubClient

    sample_values = {
        "=": "x",
        "!=": "x",
        "<": 1,
        "<=": 1,
        ">": 1,
        ">=": 1,
        "contains": "x",
        "not_contains": "x",
        "starts_with": "x",
        "ends_with": "x",
        "not_starts_with": "x",
        "not_ends_with": "x",
        "month_equals": 1,
        "is_any_of": ["dd1"],
        "not_any_of": ["dd1"],
        "has_any": ["dd1"],
        "between": [1, 2],
    }
    no_value_ops = {"is_blank", "not_blank", "is_me", "is_checked", "not_checked"}
    field_by_type = {
        "text": "ftext",
        "checkbox": "fcheckbox",
        "dropdown": "fdropdown",
    }
    for field_type, field in field_by_type.items():
        for op in field_type_ops(field_type):
            spec = {"field": field, "op": op}
            if op not in no_value_ops:
                spec["value"] = sample_values[op]
            render_search_filters(
                {"all": [spec]}, "policies_policy", client=StubClient()
            )
