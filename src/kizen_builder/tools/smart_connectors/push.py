"""Dev loop: ``push`` — write the local connector.sql back onto the draft SQL
script, and optionally publish the draft live. Always previews a diff first.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from kizen_builder.api import smart_connectors as sc_api
from kizen_builder.api.client import KizenClient
from kizen_builder.config import load_env_config
from kizen_builder.tools.plans import PlanError
from kizen_builder.tools.smart_connectors._common import MARKER_NAME


def _read_marker(workdir: Path) -> dict[str, Any]:
    marker_path = workdir / MARKER_NAME
    if not marker_path.exists():
        raise FileNotFoundError(
            f"no {MARKER_NAME} in {workdir} — pass the connector explicitly, or "
            f"run from a directory produced by `smart-connectors pull`."
        )
    return json.loads(marker_path.read_text())


def plan_push(
    workdir: str | os.PathLike[str] = ".",
    *,
    connector: str | None = None,
    script_id: str | None = None,
) -> dict[str, Any]:
    """Compute what a push would change: the current remote draft's SQL vs the
    local connector.sql, as a preview the CLI can render + confirm.

    Guards against the marker going stale behind the CLI's back: if
    ``script_id`` has since been promoted live, a PATCH against it would
    silently no-op (the server 200s without applying the change, then
    ``publish`` 400s with a generic "already live"), so that's rejected here
    with a clear error instead of surfacing downstream. If it's still a draft
    but no longer the connector's *current* one — another stray draft has
    accumulated ahead of it — that's surfaced as a warning rather than a hard
    failure, since an explicit ``--script`` may be intentional.

    Returns ``{connector, script_id, changed, local_sql, remote_sql, diff,
    script_status, current_draft_id, warning}``.
    """
    wd = Path(workdir).resolve()
    from_marker = connector is None or script_id is None
    if from_marker:
        marker = _read_marker(wd)
        connector = (
            connector or marker.get("connector_id") or marker.get("connector_api_name")
        )
        script_id = script_id or marker.get("script_id")
    if connector is None or script_id is None:
        raise PlanError(
            f"could not determine connector/script from {MARKER_NAME} in {wd} — "
            "pass --connector/--script explicitly."
        )

    sql_path = wd / "connector.sql"
    if not sql_path.exists():
        raise FileNotFoundError(f"no connector.sql in {wd}.")
    local_sql = sql_path.read_text()

    config = load_env_config()
    with KizenClient(config) as client:
        remote = sc_api.get_sql_script(client, connector, script_id)
        detail = sc_api.get_smart_connector(client, connector)
    remote_sql = remote.get("user_script") or ""
    status = remote.get("status")
    current_draft_id = (detail.get("last_draft_script") or {}).get("id")

    if status and status != "draft":
        source = "the pull marker" if from_marker else "--script"
        hint = (
            f" The connector's current draft is {current_draft_id}."
            if current_draft_id and current_draft_id != script_id
            else ""
        )
        raise PlanError(
            f"script {script_id} (from {source}) is now '{status}', not a "
            f"draft — pushing to it would silently no-op instead of updating "
            f"anything.{hint} Re-run `pull` to pick up the current draft, or "
            f"pass --script explicitly."
        )

    warning = None
    if current_draft_id and current_draft_id != script_id:
        warning = (
            f"script {script_id} is a draft, but it's no longer the "
            f"connector's current one ({current_draft_id}) — likely a stray "
            f"draft left behind by an earlier session. Pushing here won't "
            f"reach what `pull`/other tooling will see next. Re-run `pull`, "
            f"or pass --script {current_draft_id} if that's the intended target."
        )

    import difflib

    diff = "".join(
        difflib.unified_diff(
            remote_sql.splitlines(keepends=True),
            local_sql.splitlines(keepends=True),
            fromfile=f"remote {status or 'draft'} {script_id}",
            tofile="local connector.sql",
        )
    )
    return {
        "connector": connector,
        "script_id": script_id,
        "script_status": status,
        "current_draft_id": current_draft_id,
        "changed": remote_sql != local_sql,
        "local_sql": local_sql,
        "remote_sql": remote_sql,
        "diff": diff,
        "warning": warning,
    }


def apply_push(
    connector: str,
    script_id: str,
    local_sql: str,
    *,
    publish: bool = False,
) -> dict[str, Any]:
    """Write local_sql onto the draft script (PATCH), optionally publish it.

    ``publish`` requires a successful output sample generated *for the SQL
    just written* — a sample from a previous version of the script doesn't
    count, so this re-checks ``state`` after the PATCH rather than trusting
    one taken before it. Without this, ``publish`` 400s with a generic
    "Output sample file is not generated yet" that gives no hint that
    ``generate-sample`` is the actual missing step.
    """
    config = load_env_config()
    with KizenClient(config) as client:
        updated = sc_api.update_sql_script(
            client, connector, script_id, {"user_script": local_sql}
        )
        result = {
            "updated_script_id": updated.get("id") or script_id,
            "published": False,
        }
        if publish:
            current = sc_api.get_sql_script(client, connector, script_id)
            state = current.get("state")
            if state != "success":
                raise PlanError(
                    f"can't publish script {script_id}: no successful output "
                    f"sample for the SQL just pushed (state: {state or 'none'}). "
                    f"Run `smart-connectors generate-sample` first, then "
                    f"`push --publish` again."
                )
            pub = sc_api.publish_sql_script(client, connector, script_id)
            result["published"] = True
            result["published_id"] = pub.get("id")
    return result
