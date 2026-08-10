"""Envelope renderers: one expression -> the three consumer wire shapes."""

from __future__ import annotations

from kizen_builder.filtering import (
    All,
    Any,
    Field,
    as_custom_filters,
    as_filter_config,
    as_search_body,
    filter_context,
)
from tests.filter_stub import StubClient


def _expr():
    return All(
        Field("ftext") == "abc",
        Any(Field("fdropdown") == "dd1", Field("fdropdown") == "dd2"),
    )


def _with_stub(fn):
    with filter_context("policies_policy", client=StubClient()):
        return fn()


def test_search_body_shape():
    body = _with_stub(lambda: as_search_body(_expr()))
    assert set(body) == {"query", "and"}
    assert body["and"] is True
    assert len(body["query"]) == 2
    # groups in the search body carry no ids
    assert all("id" not in g for g in body["query"])


def test_filter_config_adds_sequential_group_ids_and_invalid():
    cfg = _with_stub(lambda: as_filter_config(_expr()))
    assert cfg["invalid"] is False
    assert [g["id"] for g in cfg["query"]] == ["query-0", "query-1"]
    # group content preserved alongside the id
    assert cfg["query"][0]["filters"][0]["condition"] == "="


def test_custom_filters_wrapper():
    wrapped = _with_stub(lambda: as_custom_filters(_expr()))
    inner = wrapped["custom_filters"]
    assert [g["id"] for g in inner["query"]] == ["query-0", "query-1"]
    assert inner["and"] is True


def test_bare_condition_is_wrapped_in_single_group():
    cfg = _with_stub(lambda: as_filter_config(Field("ftext") == "abc"))
    assert [g["id"] for g in cfg["query"]] == ["query-0"]
    (clause,) = cfg["query"][0]["filters"]
    assert clause["condition"] == "="
    assert clause["value"] == "abc"


def test_no_null_values_in_rendered_clauses():
    """reference.md: `value` may never be null in filter_config."""
    cfg = _with_stub(
        lambda: as_filter_config(
            All(Field("ftext").is_blank(), Field("ftext").not_blank())
        )
    )
    clauses = [c for g in cfg["query"] for c in g["filters"]]
    assert all(c["value"] is not None for c in clauses)


def test_search_body_accepts_pre_rendered_dict():
    """Callers holding a raw group dict (e.g. from a spec file) can pass it through."""
    raw = {"and": True, "query": [{"and": True, "filters": []}]}
    assert as_search_body(raw) == {"query": raw["query"], "and": True}
