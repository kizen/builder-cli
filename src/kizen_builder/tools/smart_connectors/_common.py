"""Shared, dependency-free state: the pull/push marker filename, the
current_execution.json column list, and the one UUID-sniffing helper used by
both the inspection and webhook clusters.
"""

from __future__ import annotations

import uuid

# Marker file dropped into a pulled working directory so `run`/`push` know which
# connector + script the directory belongs to without re-passing it each time.
MARKER_NAME = ".kizen-connector.json"

# The columns script_runner expects in data/current_execution.json (mirrors
# META_CURRENT_EXECUTION_COLUMNS in the vendored runtime).
_META_KEYS = [
    "business_id",
    "connector_id",
    "execution_id",
    "trigger_type",
    "triggered_by_id",
    "triggered_by_desc",
    "trigger_auth",
    "fileupload_file_size_bytes",
    "fileupload_file_name",
    "fileupload_file_id",
    "is_dry_run",
    "cadence",
    "timeframe_start",
    "bulkaction_fields",
    "entity_records_set_key",
    "activity_object_id",
]


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
