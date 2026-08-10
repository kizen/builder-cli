"""Authoring: ``set-input`` — upload the reference file, attach it, and (by
default) regenerate the draft script + config from its columns."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from kizen_builder.api import files as files_api
from kizen_builder.api import smart_connectors as sc_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.plans import PlanError
from kizen_builder.tools.smart_connectors.authoring._helpers import (
    _SAMPLE_FILE_SHAPES,
    _connector_ref,
    _object_lookup,
)

# Re-attaching a *different* file to a connector that already has one leaves
# config_metadata.triggered.fileupload_file_id stuck on the original, and the
# live executor then reads the old file's bytes against the new schema
# (ClickHouse UNKNOWN_IDENTIFIER). Confirmed live 2026-07-28; a Kizen platform
# bug, not something this CLI can work around — so the CLI refuses by default.
_SWAP_WARNING = (
    "replacing a connector's reference file is a known-broken operation in "
    "Kizen: config_metadata.triggered.fileupload_file_id stays pinned to the "
    "ORIGINAL file no matter how many times the new id is patched, and live "
    "executions then read the old file's bytes against the new schema and fail "
    "with a ClickHouse UNKNOWN_IDENTIFIER error. Build a fresh connector with "
    "the final file as its first-ever upload instead. Pass allow_replace "
    "(--force) only if you know this connector will never run live."
)


def plan_set_input(
    connector: str,
    file_path: str | os.PathLike[str],
    *,
    regenerate: bool = True,
    allow_replace: bool = False,
) -> dict[str, Any]:
    """Preview attaching a local file to a connector as its reference file.

    Refuses to replace an existing reference file unless ``allow_replace`` —
    see ``_SWAP_WARNING``.
    """
    src = Path(file_path)
    if not src.is_file():
        raise FileNotFoundError(f"{src} is not a file")

    config = load_env_config()
    with KizenClient(config) as client:
        detail = sc_api.get_smart_connector(client, connector)

    existing = detail.get("source_file") or {}
    if existing.get("id") and not allow_replace:
        raise PlanError(
            f"'{detail.get('api_name')}' already has the reference file "
            f"'{existing.get('name')}' attached — {_SWAP_WARNING}"
        )

    draft = detail.get("last_draft_script") or {}
    if regenerate and not draft.get("id"):
        raise PlanError(
            f"'{detail.get('api_name')}' has no draft SQL script to write the "
            f"generated template onto — pass regenerate=False (--no-regenerate) "
            f"to just attach the file"
        )

    ctype = detail.get("connector_type")
    return {
        "env": config.name,
        "connector": _connector_ref(detail),
        "connector_api_name": detail.get("api_name"),
        "connector_type": ctype,
        "file": str(src),
        "file_size": src.stat().st_size,
        "replacing": existing.get("name") or None,
        "regenerate": regenerate,
        "script_id": draft.get("id"),
        "sql_version": draft.get("sql_version"),
        "expected_shape": _SAMPLE_FILE_SHAPES.get(ctype or ""),
    }


_CREATE_OUTPUT_TABLE = re.compile(
    r"create\s+table\s+output\.(?P<table>\w+)\b[^;]*;\s*", re.IGNORECASE
)


def _drop_phantom_output_tables(
    user_script: str, real_objects: set[str]
) -> tuple[str, list[str]]:
    """Remove generated ``create table output.X`` statements where X isn't an object.

    The webhook template ships a second statement building
    ``output.webhooks`` — a debug echo of the input, since ``webhooks`` is not a
    Kizen object. Leaving it in makes sample generation crash, so it goes. Kept
    general (any output table with no matching object) rather than special-cased
    to webhooks, because that's the actual rule: an output table is a load
    target, and a load target has to exist.

    Only ever applied to a freshly generated template — the ``[^;]*`` span would
    mis-split hand-written SQL with a semicolon inside a string literal.
    Returns ``(script, dropped_table_names)``.
    """
    dropped: list[str] = []

    def _keep(match: re.Match[str]) -> str:
        table = match.group("table")
        if table in real_objects:
            return match.group(0)
        dropped.append(table)
        return ""

    return _CREATE_OUTPUT_TABLE.sub(_keep, user_script), dropped


def apply_set_input(plan: dict[str, Any]) -> dict[str, Any]:
    """Upload the file, attach it, and (by default) regenerate the draft script.

    The S3 upload + File registration, then the connector's ``source_file_id``,
    then the generated ``user_script`` / ``config_metadata`` onto the draft.
    Generation is server-side and reads the file's real columns, so it has to
    happen after the attach.

    Two things about ``get-file-template`` make the last step fiddlier than a
    PATCH (both confirmed live 2026-07-30):

    * It **creates a new draft script** carrying the generated template, so the
      draft that existed at plan time is superseded. Writing to that stale id
      would leave the template on a script nothing looks at, so the target is
      re-read here rather than taken from the plan.
    * The draft it creates comes back at ``sql_version: 1.3.x`` regardless of
      what the connector's draft was on. That's a silent downgrade, and for a
      webhook connector it's fatal — sample generation 500s below 4.1.x. So the
      version is restored when it regressed, before anything runs.
    """
    config = load_env_config()
    with KizenClient(config) as client:
        uploaded = files_api.upload_file(
            client, plan["file"], source=files_api.SMART_CONNECTOR_IMPORT
        )
        sc_api.update_smart_connector(
            client, plan["connector"], {"source_file_id": uploaded["id"]}
        )

        result: dict[str, Any] = {
            "file_id": uploaded["id"],
            "file_name": uploaded.get("name"),
            "connector": plan["connector_api_name"],
            "regenerated": False,
        }
        if not plan.get("regenerate"):
            return result

        template = sc_api.get_file_template(client, plan["connector"], uploaded["id"])
        if not template.get("user_script"):
            raise PlanError(
                "the server returned an empty template for this file. The file's "
                "shape is validated per connector type — "
                f"{plan.get('expected_shape') or 'see `kizen docs show reference`'}"
            )

        refreshed = sc_api.get_smart_connector(client, plan["connector"])
        draft = refreshed.get("last_draft_script") or {}
        script_id = draft.get("id") or plan["script_id"]

        by_api, _ = _object_lookup(client)
        user_script, dropped = _drop_phantom_output_tables(
            template["user_script"], set(by_api)
        )

        script_payload: dict[str, Any] = {"user_script": user_script}
        if template.get("config_metadata") is not None:
            script_payload["config_metadata"] = template["config_metadata"]
        was, now = plan.get("sql_version"), draft.get("sql_version")
        if was and now and was != now:
            script_payload["sql_version"] = was
        updated = sc_api.update_sql_script(
            client, plan["connector"], script_id, script_payload
        )

        cfg = template.get("config_metadata") or {}
        result.update(
            {
                "regenerated": True,
                "script_id": script_id,
                "new_draft": script_id != plan["script_id"],
                "sql_version": updated.get("sql_version") or now,
                "sql_version_restored": was
                if "sql_version" in script_payload
                else None,
                "dropped_output_tables": dropped,
                "sql_lines": len(user_script.splitlines()),
                "input_tables": [
                    t.get("name") or t.get("table_name")
                    for t in (cfg.get("input_tables") or [])
                ],
                "seed_tables": [
                    t.get("name") or t.get("table_name")
                    for t in (cfg.get("seed_tables") or [])
                ],
            }
        )
    return result
