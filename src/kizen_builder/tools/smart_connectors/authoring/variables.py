"""Authoring: suggested execution variables — ask the server to infer them
from the reference file. Saves nothing."""

from __future__ import annotations

from typing import Any

from kizen_builder.api import smart_connectors as sc_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config

# Keys the write shape (ExecutionVariableRequest) accepts. The suggestion
# endpoint hands back unsaved rows carrying generated ids; those ids mean
# nothing, so they're dropped from the spec block.
_VARIABLE_WIRE_KEYS = (
    "name",
    "data_source",
    "data_type",
    "scope",
    "is_array",
    "array_delimiter",
    "required",
    "input_format",
    "output_format",
    "value",
    "display_order",
)


def suggest_execution_variables(connector: str) -> dict[str, Any]:
    """Ask the server to infer execution variables from the reference file.

    Saves nothing. Returns the raw suggestions plus a ``spec`` block ready to
    paste into a configure-flow spec file.
    """
    config = load_env_config()
    with KizenClient(config) as client:
        suggested = sc_api.generate_execution_variables(client, connector)
    rows = suggested if isinstance(suggested, list) else []
    return {
        "connector": connector,
        "count": len(rows),
        "raw": rows,
        "spec": {
            "connector": connector,
            "execution_variables": [
                {
                    k: v
                    for k, v in row.items()
                    if k in _VARIABLE_WIRE_KEYS and v is not None and v is not False
                }
                for row in rows
            ],
        },
    }
