"""Tests for the record-layout `custom_content` block builder.

Pins the shape confirmed live 2026-07-21 from a real layout authored
through the actual Kizen layout builder (see `kizen docs show reference`,
"Record Layout API" -> "custom_content blocks"):
  * the wrapper is {id, label, type: "custom_content", metadata: {blockJson}}
    with NO internalName/displayName keys (those are `fields`-block-specific);
  * blockJson is a NESTED OBJECT, not a JSON-encoded string (unlike a
    form/survey's page_data);
  * the tree's Root node carries no container*-prefixed props at all,
    unlike a form page's Root.
The builder is pure, so no live-API stubbing is needed.
"""

from __future__ import annotations

from kizen_builder.tools.form_ui import cell, row, section, text_block
from kizen_builder.tools.layouts import custom_content_block


def test_custom_content_block_wrapper_shape():
    block = custom_content_block([section([row([cell([text_block("<p>hi</p>")])])])])
    assert block["type"] == "custom_content"
    assert block["label"] == "Custom Content"
    assert "internalName" not in block
    assert "displayName" not in block
    assert isinstance(block["id"], str) and block["id"]
    assert isinstance(block["metadata"]["blockJson"], dict)


def test_custom_content_root_has_no_container_prefixed_props():
    block = custom_content_block([section([row([cell([text_block("<p>hi</p>")])])])])
    root_props = block["metadata"]["blockJson"]["ROOT"]["props"]
    assert not any(k.startswith("container") for k in root_props)
    assert root_props["backgroundColor"] == "rgba(255,255,255,1)"
    assert root_props["hasShadow"] is True


def test_custom_content_label_is_overridable():
    block = custom_content_block(
        [section([row([cell([text_block("<p>hi</p>")])])])], label="My Block"
    )
    assert block["label"] == "My Block"
