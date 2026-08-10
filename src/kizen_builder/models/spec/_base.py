"""Shared naming/enum primitives used across the spec package.

No cross-module imports — this is the base of the dependency graph.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

ApiName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", min_length=1, max_length=100),
]
"""Stable identifier for matching spec entities to Kizen UUIDs across re-runs.

Lowercase, starts with a letter, letters/digits/underscores only.
"""


FieldType = Literal[
    "checkbox",
    "checkboxes",
    "choices",
    "date",
    "datetime",
    "decimal",
    "dropdown",
    "dynamictags",
    "email",
    "files",
    "integer",
    "longtext",
    "money",
    "phonenumber",
    "radio",
    "rating",
    "relationship",
    "selector",
    "status",
    "team_selector",
    "text",
    "timezone",
    "wysiwyg",
    "yesnomaybe",
]
"""All 24 custom-object field types supported by the Kizen API."""


RelationType = Literal[
    "one_to_one",
    "primary",
    "additional",
    "primary_for",
    "additional_for",
]
"""Kizen's own wire-level relation_type enum. `primary`/`primary_for` are a
mirror pair for a one-to-many relation (which side is "one" vs "many");
`additional`/`additional_for` are a mirror pair for many-to-many. Prefer the
clearer `RelationCardinality` values below — this raw enum exists for
authoring specs straight from `kizen automations get`-style API output."""


RelationCardinality = Literal[
    "one_to_one", "one_to_many", "many_to_one", "many_to_many"
]
"""Cardinality of the relation from *this* field's object toward the target,
in the same one-to-one/one-to-many/many-to-one/many-to-many language Kizen's
own UI uses. Resolved to a wire `RelationType` by the planner:
one_to_one -> one_to_one, many_to_one -> primary (this object holds a single
reference to the target; many records here can share it), one_to_many ->
primary_for (this object relates to many target records), many_to_many ->
additional."""
