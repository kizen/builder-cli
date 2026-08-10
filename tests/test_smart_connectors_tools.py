"""Tools-layer tests for smart-connectors: pull/push orchestration + run.

The pull tests stub the vendored normalizer so they don't need the optional
``connectors`` extra; the run test is skipped unless ``chdb`` is installed.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from kizen_builder.tools import smart_connectors as sct
from kizen_builder.tools.plans import PlanError
from kizen_builder.tools.smart_connectors import pull as sc_pull
from tests.conftest import FAKE_BASE_URL

BASE = f"{FAKE_BASE_URL}/api/smart-connectors"

DETAIL = {
    "id": "conn-uuid",
    "api_name": "upload_counties",
    "name": "Upload Counties",
    "connector_type": "spreadsheet",
    "status": "operational",
    "sql_parameters": {},
    "integration_secrets": [],
    "last_draft_script": {"id": "draft-1", "status": "draft"},
    "live_script": {"id": "live-1", "status": "live"},
}

DRAFT_SCRIPT = {
    "id": "draft-1",
    "status": "draft",
    "user_script": "SELECT * FROM input.records;",
    "config_metadata": {
        "input_tables": [
            {
                "name": "records.csv",
                "file_id": "file-1",
                "database": "input",
                "page_idx": 0,
                "file_path": None,
                "table_name": "records",
                "columns_mapping": [{"col": "a", "type": "str"}],
            }
        ],
        "seed_tables": [],
        "triggered": {"trigger_auth": "session", "fileupload_file_name": "records.csv"},
    },
}


@pytest.fixture
def no_normalize(monkeypatch):
    """Stub the vendored normalizer (which needs the extra) to a no-op.

    Patched on `smart_connectors.pull`, the module that both defines
    `_normalize_input` and calls it. Patching the package facade instead would
    silently miss: `pull_connector` resolves the bare name against its own
    module globals, not the re-export.
    """
    calls = []
    monkeypatch.setattr(
        sc_pull, "_normalize_input", lambda p, wd: calls.append((p, wd)) or ""
    )
    return calls


@respx.mock
def test_pull_assembles_workdir(tmp_path, no_normalize):
    respx.get(f"{BASE}/upload_counties").mock(
        return_value=httpx.Response(200, json=DETAIL)
    )
    respx.get(f"{BASE}/upload_counties/sql-scripts/draft-1").mock(
        return_value=httpx.Response(200, json=DRAFT_SCRIPT)
    )
    respx.get(f"{FAKE_BASE_URL}/api/files/file-1/download").mock(
        return_value=httpx.Response(
            200,
            content=b"a\n1\n",
            headers={"content-disposition": 'inline; filename="records.csv"'},
        )
    )
    dest = tmp_path / "wd"
    res = sct.pull_connector("upload_counties", dest=str(dest))

    assert (dest / "connector.sql").read_text() == "SELECT * FROM input.records;"
    cfg = json.loads((dest / "__config.json").read_text())
    assert cfg["input_tables"][0]["table_name"] == "records"
    assert cfg["integration_secrets"] == []
    assert "sql_parameters" in cfg and "integration_secret_filenames" in cfg

    cur = json.loads((dest / "data" / "current_execution.json").read_text())
    assert cur["business_id"]  # filled from env config
    assert cur["connector_id"] == "conn-uuid"
    assert cur["trigger_auth"] == "session"

    marker = json.loads((dest / sct.MARKER_NAME).read_text())
    assert marker["connector_id"] == "conn-uuid"
    assert marker["script_id"] == "draft-1"

    assert res["inputs_downloaded"] == ["records.csv"]
    # normalizer was invoked on the downloaded file
    assert no_normalize and no_normalize[0][0].endswith("records.csv")
    assert (dest / "data" / "records.csv").read_bytes() == b"a\n1\n"


@respx.mock
def test_pull_live_selects_live_script(tmp_path, no_normalize):
    live = {**DRAFT_SCRIPT, "id": "live-1", "status": "live"}
    respx.get(f"{BASE}/upload_counties").mock(
        return_value=httpx.Response(200, json=DETAIL)
    )
    respx.get(f"{BASE}/upload_counties/sql-scripts/live-1").mock(
        return_value=httpx.Response(200, json=live)
    )
    respx.get(f"{FAKE_BASE_URL}/api/files/file-1/download").mock(
        return_value=httpx.Response(200, content=b"a\n1\n")
    )
    res = sct.pull_connector(
        "upload_counties", dest=str(tmp_path / "wd"), use_live=True
    )
    assert res["script_id"] == "live-1"
    assert res["script_status"] == "live"


@respx.mock
def test_pull_refuses_nonempty_dir(tmp_path, no_normalize):
    respx.get(f"{BASE}/upload_counties").mock(
        return_value=httpx.Response(200, json=DETAIL)
    )
    respx.get(f"{BASE}/upload_counties/sql-scripts/draft-1").mock(
        return_value=httpx.Response(200, json=DRAFT_SCRIPT)
    )
    dest = tmp_path / "wd"
    dest.mkdir()
    (dest / "something").write_text("x")
    with pytest.raises(FileExistsError):
        sct.pull_connector("upload_counties", dest=str(dest))


@respx.mock
def test_pull_warns_on_seed_and_secret(tmp_path, no_normalize):
    detail = {
        **DETAIL,
        "connector_type": "direct_api_connection",
        "integration_secrets": ["my_api"],
    }
    script = {
        **DRAFT_SCRIPT,
        "config_metadata": {
            "input_tables": [
                {"table_name": "t", "columns_mapping": [], "file_id": None}
            ],
            "seed_tables": [{"name": "seed.csv", "table_name": "seed"}],
            "triggered": {},
        },
    }
    respx.get(f"{BASE}/upload_counties").mock(
        return_value=httpx.Response(200, json=detail)
    )
    respx.get(f"{BASE}/upload_counties/sql-scripts/draft-1").mock(
        return_value=httpx.Response(200, json=script)
    )
    res = sct.pull_connector("upload_counties", dest=str(tmp_path / "wd"))
    joined = " ".join(res["warnings"])
    assert "seed table" in joined
    assert "integration secret" in joined
    assert "direct_api_connection" in joined
    assert res["inputs_downloaded"] == []


@respx.mock
def test_plan_push_detects_change(tmp_path):
    wd = tmp_path / "wd"
    (wd / "data").mkdir(parents=True)
    (wd / "connector.sql").write_text("SELECT 2;")
    (wd / sct.MARKER_NAME).write_text(
        json.dumps({"connector_id": "conn-uuid", "script_id": "draft-1"})
    )
    respx.get(f"{BASE}/conn-uuid/sql-scripts/draft-1").mock(
        return_value=httpx.Response(
            200, json={"id": "draft-1", "status": "draft", "user_script": "SELECT 1;"}
        )
    )
    respx.get(f"{BASE}/conn-uuid").mock(return_value=httpx.Response(200, json=DETAIL))
    plan = sct.plan_push(str(wd))
    assert plan["changed"] is True
    assert "SELECT 2;" in plan["diff"]
    assert plan["connector"] == "conn-uuid"
    assert plan["warning"] is None


@respx.mock
def test_plan_push_unchanged(tmp_path):
    wd = tmp_path / "wd"
    (wd / "data").mkdir(parents=True)
    (wd / "connector.sql").write_text("SELECT 1;")
    (wd / sct.MARKER_NAME).write_text(
        json.dumps({"connector_id": "conn-uuid", "script_id": "draft-1"})
    )
    respx.get(f"{BASE}/conn-uuid/sql-scripts/draft-1").mock(
        return_value=httpx.Response(
            200, json={"id": "draft-1", "status": "draft", "user_script": "SELECT 1;"}
        )
    )
    respx.get(f"{BASE}/conn-uuid").mock(return_value=httpx.Response(200, json=DETAIL))
    plan = sct.plan_push(str(wd))
    assert plan["changed"] is False
    assert plan["diff"] == ""


@respx.mock
def test_plan_push_rejects_a_marker_that_went_live(tmp_path):
    """The marker's script_id was promoted live behind the CLI's back — pushing
    to it would silently no-op (200 with no applied change), so this must
    fail fast instead."""
    wd = tmp_path / "wd"
    (wd / "data").mkdir(parents=True)
    (wd / "connector.sql").write_text("SELECT 2;")
    (wd / sct.MARKER_NAME).write_text(
        json.dumps({"connector_id": "conn-uuid", "script_id": "live-1"})
    )
    respx.get(f"{BASE}/conn-uuid/sql-scripts/live-1").mock(
        return_value=httpx.Response(
            200, json={"id": "live-1", "status": "live", "user_script": "SELECT 1;"}
        )
    )
    respx.get(f"{BASE}/conn-uuid").mock(return_value=httpx.Response(200, json=DETAIL))
    with pytest.raises(PlanError, match="now 'live', not a draft"):
        sct.plan_push(str(wd))


@respx.mock
def test_plan_push_warns_when_marker_points_at_a_stray_draft(tmp_path):
    """A newer draft than the one the marker knows about has since been
    created (e.g. by get-file-template) — pushing here still writes
    somewhere, just not where `pull` would next look."""
    wd = tmp_path / "wd"
    (wd / "data").mkdir(parents=True)
    (wd / "connector.sql").write_text("SELECT 2;")
    (wd / sct.MARKER_NAME).write_text(
        json.dumps({"connector_id": "conn-uuid", "script_id": "old-draft"})
    )
    respx.get(f"{BASE}/conn-uuid/sql-scripts/old-draft").mock(
        return_value=httpx.Response(
            200, json={"id": "old-draft", "status": "draft", "user_script": "SELECT 1;"}
        )
    )
    respx.get(f"{BASE}/conn-uuid").mock(return_value=httpx.Response(200, json=DETAIL))
    plan = sct.plan_push(str(wd))
    assert plan["changed"] is True
    assert "draft-1" in plan["warning"]


@respx.mock
def test_apply_push_updates_and_publishes(tmp_path):
    patch = respx.patch(f"{BASE}/conn-uuid/sql-scripts/draft-1").mock(
        return_value=httpx.Response(200, json={"id": "draft-1"})
    )
    respx.get(f"{BASE}/conn-uuid/sql-scripts/draft-1").mock(
        return_value=httpx.Response(200, json={"id": "draft-1", "state": "success"})
    )
    pub = respx.post(f"{BASE}/conn-uuid/sql-scripts/draft-1/publish").mock(
        return_value=httpx.Response(200, json={"id": "draft-1"})
    )
    result = sct.apply_push("conn-uuid", "draft-1", "SELECT 9;", publish=True)
    assert patch.called and pub.called
    assert result["published"] is True
    body = json.loads(patch.calls.last.request.content)
    assert body["user_script"] == "SELECT 9;"


@respx.mock
def test_apply_push_blocks_publish_without_a_successful_sample():
    """publish 400s with a generic 'Output sample file is not generated yet'
    otherwise — this should fail fast with a message pointing at the actual
    missing step instead of surfacing that passthrough error."""
    patch = respx.patch(f"{BASE}/conn-uuid/sql-scripts/draft-1").mock(
        return_value=httpx.Response(200, json={"id": "draft-1"})
    )
    respx.get(f"{BASE}/conn-uuid/sql-scripts/draft-1").mock(
        return_value=httpx.Response(200, json={"id": "draft-1", "state": None})
    )
    pub = respx.post(f"{BASE}/conn-uuid/sql-scripts/draft-1/publish")
    with pytest.raises(PlanError, match="generate-sample"):
        sct.apply_push("conn-uuid", "draft-1", "SELECT 9;", publish=True)
    assert patch.called
    assert not pub.called


def test_events_requires_uuid(monkeypatch):
    with pytest.raises(LookupError):
        sct.list_events("not-a-uuid")


def test_run_missing_workdir(tmp_path):
    with pytest.raises(FileNotFoundError):
        sct.run_connector(str(tmp_path))


def test_run_executes_sql_when_chdb_present(tmp_path):
    pytest.importorskip("chdb")
    wd = tmp_path / "wd"
    data = wd / "data"
    data.mkdir(parents=True)
    (data / "records.csv").write_text("id,val\n1,hello\n2,world\n")
    (data / "current_execution.json").write_text("{}")
    (wd / "connector.sql").write_text(
        "CREATE TABLE output.out ENGINE = Log AS SELECT * FROM input.records;"
    )
    (wd / "__config.json").write_text(
        json.dumps(
            {
                "input_tables": [
                    {
                        "name": "records.csv",
                        "database": "input",
                        "page_idx": 0,
                        "table_name": "records",
                        "columns_mapping": [
                            {"col": "id", "type": "str"},
                            {"col": "val", "type": "str"},
                        ],
                    }
                ],
                "seed_tables": [],
                "integration_secrets": [],
                "sql_parameters": {},
                "integration_secret_filenames": [],
            }
        )
    )
    meta = sct.run_connector(str(wd))
    assert meta["stats"]["num_rows"] == 2
    assert any(f["file_name"] == "out.csv" for f in meta["output_files"])
    assert Path(meta["output_files"][0]["file_path"]).exists()
