"""CLI surface tests: argument wiring, output formats, exit codes."""

from __future__ import annotations

import json

from typer.testing import CliRunner

import kizen_builder.cli as cli
from kizen_builder.tools import automations as auto_tools
from kizen_builder.tools import forms as form_tools
from kizen_builder.tools import objects as obj_tools
from kizen_builder.tools import permissions as perm_tools
from kizen_builder.tools import plans as plan_tools
from kizen_builder.tools import records as record_tools
from kizen_builder.tools.planners import automations as auto_planners
from kizen_builder.tools.planners import fields as field_planners
from kizen_builder.tools.planners import forms as form_planners
from kizen_builder.tools.planners import objects as object_planners
from kizen_builder.tools.planners import records as record_planners
from tests.conftest import load_fixture

runner = CliRunner()


def test_objects_list_json(monkeypatch):
    fake = [
        {
            "env": "testenv",
            "id": "abc",
            "api_name": "invoice",
            "display_name": "Invoices",
            "entity_name": "Invoice",
            "object_type": "standard",
            "deleted": False,
        }
    ]
    monkeypatch.setattr(obj_tools, "list_objects", lambda: fake)
    result = runner.invoke(cli.app, ["objects", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == fake


def test_objects_list_table(monkeypatch):
    fake = [
        {
            "env": "testenv",
            "id": "abcd1234-x",
            "api_name": "invoice",
            "display_name": "Invoices",
            "entity_name": "Invoice",
            "object_type": "standard",
            "deleted": False,
        }
    ]
    monkeypatch.setattr(obj_tools, "list_objects", lambda: fake)
    result = runner.invoke(cli.app, ["objects", "list"])
    assert result.exit_code == 0
    assert "invoice" in result.stdout
    assert "Invoices" in result.stdout


def test_records_list_forwards_search_and_limit(monkeypatch):
    seen = {}

    def fake_search(object_api_name, filters=None, search=None, limit=100):
        seen.update(object_api_name=object_api_name, search=search, limit=limit)
        return []

    monkeypatch.setattr(record_tools, "search_records", fake_search)
    result = runner.invoke(
        cli.app, ["records", "list", "tax_lot", "--search", "main", "-n", "7"]
    )
    assert result.exit_code == 0
    assert seen == {"object_api_name": "tax_lot", "search": "main", "limit": 7}


def test_automations_get_raw_emits_full_response(monkeypatch):
    raw = load_fixture("automations/two_code_steps.raw.json")
    monkeypatch.setattr(
        auto_tools,
        "get_automation",
        lambda api_name: {"api_name": api_name, "raw": raw},
    )
    result = runner.invoke(
        cli.app, ["automations", "get", "test_two_code_steps", "--raw"]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == raw


def test_records_list_csv_flattens_fields(monkeypatch):
    records = load_fixture("records/list_tax_lot.json")
    monkeypatch.setattr(record_tools, "search_records", lambda *a, **k: records)
    result = runner.invoke(cli.app, ["records", "list", "tax_lot", "-o", "csv"])
    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    header = lines[0].split(",")
    assert header[0] == "id"
    assert "ticker_symbol" in header  # a field was flattened into a column
    assert len(lines) == 1 + len(records)  # header + one row per record


def test_json_flag_and_output_json_are_equivalent(monkeypatch):
    records = load_fixture("records/list_tax_lot.json")
    monkeypatch.setattr(record_tools, "search_records", lambda *a, **k: records)
    a = runner.invoke(cli.app, ["records", "list", "tax_lot", "--json"])
    b = runner.invoke(cli.app, ["records", "list", "tax_lot", "-o", "json"])
    assert a.exit_code == b.exit_code == 0
    assert json.loads(a.stdout) == json.loads(b.stdout) == records


def test_invalid_output_format_is_usage_error(monkeypatch):
    monkeypatch.setattr(obj_tools, "list_objects", lambda: [])
    result = runner.invoke(cli.app, ["objects", "list", "-o", "yaml"])
    assert result.exit_code == 2


def test_runs_list_csv_uses_untruncated_ids(monkeypatch):
    execs = load_fixture("executions/list_record_test.json")
    monkeypatch.setattr(auto_tools, "list_executions", lambda *a, **k: execs)
    result = runner.invoke(
        cli.app, ["automations", "runs", "list", "record_test", "-o", "csv"]
    )
    assert result.exit_code == 0
    # Full execution_id present (table view truncates to 8 chars + ellipsis).
    assert execs[0]["execution_id"] in result.stdout


def test_retired_run_verbs_are_gone(monkeypatch):
    """The old execution(s) verbs and the show/history split no longer exist —
    runs are `list` + `view` now."""
    monkeypatch.setattr(auto_tools, "list_executions", lambda *a, **k: [])
    for argv in (
        ["automations", "executions", "record_test"],
        ["automations", "runs", "show", "x"],
        ["automations", "runs", "history", "x"],
    ):
        assert runner.invoke(cli.app, argv).exit_code != 0


def test_start_var_flags_reach_the_tool(monkeypatch):
    """--vars-json merges with repeatable --var (--var wins on conflict)."""
    captured = {}

    def fake_start(api_name, record_id, *, variables=None):
        captured["variables"] = variables
        return {
            "execution_id": "e1",
            "record_id": record_id,
            "client_id": None,
            "variable_overrides": [],
            "raw": {},
        }

    monkeypatch.setattr(auto_tools, "start_automation", fake_start)
    result = runner.invoke(
        cli.app,
        [
            "automations",
            "start",
            "flow",
            "-r",
            "rec-1",
            "--vars-json",
            '{"a": 1, "b": "x"}',
            "--var",
            "b=override",
            "--var",
            "c=3",
        ],
    )
    assert result.exit_code == 0
    assert captured["variables"] == {"a": 1, "b": "override", "c": "3"}


def test_start_rejects_malformed_var(monkeypatch):
    monkeypatch.setattr(auto_tools, "start_automation", lambda *a, **k: {})
    result = runner.invoke(
        cli.app, ["automations", "start", "flow", "-r", "rec-1", "--var", "novalue"]
    )
    assert result.exit_code != 0


def test_runs_view_rejects_non_uuid(monkeypatch):
    """An api_name (or truncated id) must fail with a pointer to a real id,
    not a bare 404 from the API — and must not even call the tool."""
    called = []
    monkeypatch.setattr(
        auto_tools, "get_execution", lambda *a, **k: called.append(1) or {}
    )
    result = runner.invoke(cli.app, ["automations", "runs", "view", "llm_comparison"])
    assert result.exit_code == 1
    assert "not an execution UUID" in result.stderr
    assert not called  # guarded before any API call


def test_runs_view_no_steps_skips_history(monkeypatch):
    """view fetches summary + step trace; --no-steps skips the history call."""
    uuid = "2461cd64-c82c-406c-a6fd-f27e4918e31e"
    hist_calls = []
    monkeypatch.setattr(
        auto_tools,
        "get_execution",
        lambda *a, **k: {"execution_id": uuid, "status": "completed"},
    )
    monkeypatch.setattr(
        auto_tools,
        "get_execution_history",
        lambda *a, **k: hist_calls.append(1) or [],
    )

    both = runner.invoke(cli.app, ["automations", "runs", "view", uuid])
    assert both.exit_code == 0
    assert len(hist_calls) == 1  # steps fetched by default

    summary_only = runner.invoke(
        cli.app, ["automations", "runs", "view", uuid, "--no-steps"]
    )
    assert summary_only.exit_code == 0
    assert len(hist_calls) == 1  # unchanged: history not fetched again


def test_runs_list_table_shows_full_execution_id(monkeypatch):
    execs = load_fixture("executions/list_record_test.json")
    monkeypatch.setattr(auto_tools, "list_executions", lambda *a, **k: execs)
    result = runner.invoke(cli.app, ["automations", "runs", "list", "record_test"])
    assert result.exit_code == 0
    # Full id present and not the truncated "…" form the old table used.
    assert execs[0]["execution_id"] in result.stdout


def test_config_error_exits_nonzero(monkeypatch):
    from kizen_builder.config import ConfigError

    def boom():
        raise ConfigError("No profile named 'sandbox' in credentials.toml.")

    monkeypatch.setattr(obj_tools, "list_objects", boom)
    result = runner.invoke(cli.app, ["objects", "list"])
    assert result.exit_code == 1
    assert "No profile named 'sandbox'" in result.stderr


def test_apply_reads_plan_from_stdin_with_yes(monkeypatch):
    from kizen_builder.tools.plans import ApplyResult, OperationResult

    applied = {}

    def fake_apply(plan):
        applied["plan_id"] = plan.id
        return ApplyResult(
            plan_id=plan.id,
            env=plan.env,
            results=[
                OperationResult(
                    key=op.key,
                    kind=op.kind,
                    action=op.action,
                    status="ok",
                    server_uuid="srv-1",
                )
                for op in plan.operations
            ],
        )

    monkeypatch.setattr(plan_tools, "apply_plan", fake_apply)

    from kizen_builder.tools.plans import Plan, PlanOperation, plan_to_json

    plan = Plan.build(
        env="testenv",
        summary="test",
        operations=[
            PlanOperation(
                action="create",
                kind="field",
                key="invoice.total",
                preview={},
                payload={"name": "total"},
                parent_object_uuid="11111111-1111-4111-8111-111111111111",
            )
        ],
    )
    result = runner.invoke(
        cli.app, ["apply", "--yes", "--json"], input=plan_to_json(plan)
    )
    assert result.exit_code == 0, result.output
    assert applied["plan_id"] == plan.id
    out = json.loads(result.stdout)
    assert out["results"][0]["status"] == "ok"


def test_apply_rejects_garbage_plan():
    result = runner.invoke(cli.app, ["apply", "--yes"], input="{not json")
    assert result.exit_code == 2
    assert "error parsing plan" in result.stderr


# ---------------------------------------------------------------------------
# mutation verbs (plan → preview → confirm → apply)
# ---------------------------------------------------------------------------


def _fake_plan(action="create"):
    from kizen_builder.tools.plans import Plan, PlanOperation

    return Plan.build(
        env="testenv",
        summary="test plan",
        operations=[
            PlanOperation(
                action=action,
                kind="field",
                key="invoice.total",
                preview={"api_name": "total"},
                payload={"name": "total"},
                parent_object_uuid="11111111-1111-4111-8111-111111111111",
                existing_uuid=None
                if action == "create"
                else "22222222-2222-4222-8222-222222222222",
            )
        ],
    )


def _ok_result(plan):
    from kizen_builder.tools.plans import ApplyResult, OperationResult

    return ApplyResult(
        plan_id=plan.id,
        env=plan.env,
        results=[
            OperationResult(
                key=op.key,
                kind=op.kind,
                action=op.action,
                status="skipped" if op.action == "skip" else "ok",
                server_uuid=None if op.action == "skip" else "srv-1",
            )
            for op in plan.operations
        ],
    )


FIELDS_CREATE_ARGS = [
    "fields",
    "create",
    "invoice",
    "--api-name",
    "total",
    "--name",
    "Total",
    "--type",
    "money",
    "--category",
    "Main",
]


def test_fields_create_dry_run_json_emits_plan_and_never_applies(monkeypatch):
    plan = _fake_plan()
    monkeypatch.setattr(field_planners, "plan_create_field", lambda **kw: plan)
    monkeypatch.setattr(
        plan_tools,
        "apply_plan",
        lambda p: (_ for _ in ()).throw(
            AssertionError("apply_plan called on --dry-run")
        ),
    )
    result = runner.invoke(cli.app, [*FIELDS_CREATE_ARGS, "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    out = json.loads(result.stdout)
    assert out["id"] == plan.id
    assert out["operations"][0]["key"] == "invoice.total"


def test_fields_create_confirm_abort_never_applies(monkeypatch):
    monkeypatch.setattr(field_planners, "plan_create_field", lambda **kw: _fake_plan())
    monkeypatch.setattr(
        plan_tools,
        "apply_plan",
        lambda p: (_ for _ in ()).throw(
            AssertionError("apply_plan called after abort")
        ),
    )
    result = runner.invoke(cli.app, FIELDS_CREATE_ARGS, input="n\n")
    assert result.exit_code == 1
    assert "aborted" in result.output


def test_fields_create_yes_applies_and_emits_result_json(monkeypatch):
    applied = {}

    def fake_apply(plan):
        applied["plan_id"] = plan.id
        return _ok_result(plan)

    monkeypatch.setattr(field_planners, "plan_create_field", lambda **kw: _fake_plan())
    monkeypatch.setattr(plan_tools, "apply_plan", fake_apply)
    result = runner.invoke(cli.app, [*FIELDS_CREATE_ARGS, "--yes", "--json"])
    assert result.exit_code == 0, result.output
    assert applied  # applied without prompting
    out = json.loads(result.stdout)  # stdout is pure result JSON (preview → stderr)
    assert out["results"][0]["status"] == "ok"


def test_update_with_no_diff_skips_without_prompting(monkeypatch):
    """An all-skip plan applies (as no-ops) without a confirmation prompt."""
    monkeypatch.setattr(
        field_planners, "plan_update_field", lambda **kw: _fake_plan(action="skip")
    )
    monkeypatch.setattr(plan_tools, "apply_plan", _ok_result)
    # no --yes and no input: a prompt would fail the invocation
    result = runner.invoke(
        cli.app, ["fields", "update", "invoice", "total", "--name", "Total"]
    )
    assert result.exit_code == 0, result.output
    assert "no changes" in result.output


def test_automations_update_from_stdin_requires_yes(monkeypatch):
    monkeypatch.setattr(
        auto_planners,
        "plan_update_automation",
        lambda spec: _fake_plan(action="update"),
    )
    spec = json.dumps({"api_name": "x", "name": "X", "type": "global", "steps": []})
    result = runner.invoke(cli.app, ["automations", "update"], input=spec)
    assert result.exit_code == 2
    assert "cannot prompt" in result.stderr


def test_automations_create_dry_run_reads_spec_from_stdin(monkeypatch):
    seen = {}

    def fake_planner(spec):
        seen["spec"] = spec
        return _fake_plan()

    monkeypatch.setattr(auto_planners, "plan_create_automation", fake_planner)
    spec = {"api_name": "x", "name": "X", "type": "global", "steps": []}
    result = runner.invoke(
        cli.app,
        ["automations", "create", "--dry-run", "--json"],
        input=json.dumps(spec),
    )
    assert result.exit_code == 0, result.output
    assert seen["spec"] == spec
    assert json.loads(result.stdout)["summary"] == "test plan"


def test_plan_star_commands_are_gone():
    result = runner.invoke(cli.app, ["plan-create-field", "invoice"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# objects create — object type / pipeline flag
# ---------------------------------------------------------------------------


def _capture_object_planner(monkeypatch):
    seen = {}

    def fake(obj_dict):
        seen["obj"] = obj_dict
        return _fake_plan()

    monkeypatch.setattr(object_planners, "plan_create_object", fake)
    return seen


def test_objects_create_defaults_to_standard(monkeypatch):
    seen = _capture_object_planner(monkeypatch)
    result = runner.invoke(
        cli.app,
        [
            "objects",
            "create",
            "--api-name",
            "invoice",
            "--name",
            "Invoices",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen["obj"]["object_type"] == "standard"


def test_objects_create_pipeline_flag(monkeypatch):
    seen = _capture_object_planner(monkeypatch)
    result = runner.invoke(
        cli.app,
        [
            "objects",
            "create",
            "--api-name",
            "deal",
            "--name",
            "Deals",
            "--pipeline",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen["obj"]["object_type"] == "pipeline"


def test_objects_create_object_type_flag(monkeypatch):
    seen = _capture_object_planner(monkeypatch)
    result = runner.invoke(
        cli.app,
        [
            "objects",
            "create",
            "--api-name",
            "deal",
            "--name",
            "Deals",
            "--object-type",
            "pipeline",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen["obj"]["object_type"] == "pipeline"


def test_objects_create_rejects_bad_object_type(monkeypatch):
    _capture_object_planner(monkeypatch)
    result = runner.invoke(
        cli.app,
        [
            "objects",
            "create",
            "--api-name",
            "x",
            "--name",
            "X",
            "--object-type",
            "bogus",
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "object-type" in result.stderr


# ---------------------------------------------------------------------------
# fields create — bulk (spec-file / stdin) mode
# ---------------------------------------------------------------------------


def _capture_fields_planner(monkeypatch):
    seen = {}

    def fake(object_api_name, pairs):
        seen["object"] = object_api_name
        seen["pairs"] = pairs
        return _fake_plan()

    monkeypatch.setattr(field_planners, "plan_create_fields", fake)
    return seen


def test_fields_create_bulk_from_stdin(monkeypatch):
    seen = _capture_fields_planner(monkeypatch)
    spec = [
        {"name": "A", "api_name": "field_a", "field_type": "text", "category": "Main"},
        {
            "name": "B",
            "api_name": "field_b",
            "field_type": "integer",
            "category": "Other",
        },
    ]
    result = runner.invoke(
        cli.app,
        ["fields", "create", "invoice", "--dry-run", "--json"],
        input=json.dumps(spec),
    )
    assert result.exit_code == 0, result.output
    assert seen["object"] == "invoice"
    assert seen["pairs"] == [
        ({"name": "A", "api_name": "field_a", "field_type": "text"}, "Main"),
        ({"name": "B", "api_name": "field_b", "field_type": "integer"}, "Other"),
    ]


def test_fields_create_bulk_from_spec_file(monkeypatch, tmp_path):
    seen = _capture_fields_planner(monkeypatch)
    spec = {
        "category": "Main",
        "fields": [
            {"name": "A", "api_name": "field_a", "field_type": "text"},
        ],
    }
    spec_path = tmp_path / "fields.json"
    spec_path.write_text(json.dumps(spec))
    result = runner.invoke(
        cli.app,
        ["fields", "create", "invoice", "--spec-file", str(spec_path), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    # spec-level category applied to the field that didn't set its own.
    assert seen["pairs"] == [
        ({"name": "A", "api_name": "field_a", "field_type": "text"}, "Main")
    ]


def test_fields_create_bulk_category_flag_is_default(monkeypatch):
    seen = _capture_fields_planner(monkeypatch)
    spec = [{"name": "A", "api_name": "field_a", "field_type": "text"}]
    result = runner.invoke(
        cli.app,
        ["fields", "create", "invoice", "--category", "Fallback", "--dry-run"],
        input=json.dumps(spec),
    )
    assert result.exit_code == 0, result.output
    assert seen["pairs"][0][1] == "Fallback"


def test_fields_create_rejects_flags_and_spec_together(monkeypatch):
    _capture_fields_planner(monkeypatch)
    result = runner.invoke(
        cli.app,
        [
            "fields",
            "create",
            "invoice",
            "--api-name",
            "x",
            "--spec-file",
            "/nonexistent",
        ],
    )
    # --api-name + --spec-file is contradictory; error before reading the file.
    assert result.exit_code == 2
    assert "not both" in result.stderr


def test_fields_create_reserved_name_gives_clean_spec_error():
    """A reserved field api_name surfaces as a clean one-liner, not a raw
    pydantic traceback (the real planner validates before any live call)."""
    result = runner.invoke(
        cli.app,
        [
            "fields",
            "create",
            "patients",
            "--api-name",
            "business_phone",
            "--name",
            "Business Phone",
            "--type",
            "phonenumber",
            "--category",
            "Patient Info",
            "--dry-run",
        ],
    )
    assert result.exit_code == 1
    assert "spec error:" in result.stderr
    assert "Kizen-reserved" in result.stderr
    assert "Traceback" not in result.stderr


def test_fields_create_single_missing_flags_errors(monkeypatch):
    monkeypatch.setattr(field_planners, "plan_create_field", lambda **kw: _fake_plan())
    # No spec, no --api-name, stdin is a tty (no input) → clean usage error.
    result = runner.invoke(cli.app, ["fields", "create", "invoice"])
    assert result.exit_code == 2
    assert "single-field create needs" in result.stderr


def test_records_list_filter_spec_rendered(monkeypatch, kizen):
    seen = {}

    def fake_search(object_api_name, filters=None, search=None, limit=100):
        seen["filters"] = filters
        return []

    monkeypatch.setattr(record_tools, "search_records", fake_search)
    result = runner.invoke(
        cli.app,
        [
            "records",
            "list",
            "policies_policy",
            "--filter",
            '{"all": [{"field": "ftext", "op": "=", "value": "abc"}]}',
        ],
    )
    assert result.exit_code == 0, result.output
    (group,) = seen["filters"]
    (clause,) = group["filters"]
    assert clause["condition"] == "="
    assert clause["value"] == "abc"


def test_records_list_filter_bad_json_exits_2(kizen):
    result = runner.invoke(
        cli.app, ["records", "list", "tax_lot", "--filter", "{not json"]
    )
    assert result.exit_code == 2
    assert "error parsing --filter JSON" in result.stderr


def test_records_list_filter_invalid_spec_exits_2(kizen):
    result = runner.invoke(
        cli.app,
        [
            "records",
            "list",
            "policies_policy",
            "--filter",
            '{"all": [{"field": "ftext", "op": "regex", "value": "x"}]}',
        ],
    )
    assert result.exit_code == 2
    assert "filter error" in result.stderr


def test_records_archive_dry_run_forwards_ids(monkeypatch):
    def fake_plan_archive(object_api_name, record_ids):
        assert object_api_name == "patients"
        assert record_ids == ["rec-1", "rec-2"]
        return plan_tools.Plan.build(
            env="testenv", summary="Archive 2 record(s)", operations=[]
        )

    monkeypatch.setattr(record_planners, "plan_archive_records", fake_plan_archive)
    result = runner.invoke(
        cli.app, ["records", "archive", "patients", "rec-1", "rec-2", "--dry-run"]
    )
    assert result.exit_code == 0, result.output


def test_records_archive_requires_at_least_one_id():
    result = runner.invoke(cli.app, ["records", "archive", "patients"])
    assert result.exit_code == 2
    assert "pass at least one record UUID" in result.stderr


def test_records_unarchive_dry_run_forwards_ids(monkeypatch):
    def fake_plan_unarchive(object_api_name, record_ids):
        assert object_api_name == "patients"
        assert record_ids == ["rec-1"]
        return plan_tools.Plan.build(
            env="testenv", summary="Unarchive 1 record(s)", operations=[]
        )

    monkeypatch.setattr(record_planners, "plan_unarchive_records", fake_plan_unarchive)
    result = runner.invoke(
        cli.app, ["records", "unarchive", "patients", "rec-1", "--dry-run"]
    )
    assert result.exit_code == 0, result.output


def test_records_unarchive_requires_at_least_one_id():
    result = runner.invoke(cli.app, ["records", "unarchive", "patients"])
    assert result.exit_code == 2
    assert "pass at least one record UUID" in result.stderr


# ---------------------------------------------------------------------------
# profiles: init, envs list, checksum refusal surfaced through a command
# ---------------------------------------------------------------------------


def test_init_stores_profile_and_pins_directory(monkeypatch, tmp_path):
    from kizen_builder import config, profiles

    config.set_profile_override(None)
    monkeypatch.chdir(tmp_path)  # pin is written to cwd
    result = runner.invoke(
        cli.app,
        ["init", "--profile", "alpha", "--skip-validation"],
        input="apikey\nAAAA\nuser1\nhttps://app.go.kizen.com\n",
    )
    assert result.exit_code == 0, result.output

    stored = profiles.get_profile("alpha")
    assert stored is not None and stored.business_id == "AAAA"

    # Read the pin file directly (autouse fixture stubs find_pin to None).
    import tomllib

    pin_file = tmp_path / profiles.PIN_RELPATH
    assert pin_file.is_file()
    data = tomllib.loads(pin_file.read_text())
    assert data == {"profile": "alpha", "business_id": "AAAA"}


def test_envs_list_json_marks_pinned_profile(monkeypatch):
    from kizen_builder import profiles

    for name, bid in (("alpha", "AAAA"), ("beta", "BBBB")):
        profiles.write_profile(
            profiles.ProfileCreds(
                name, f"k-{name}", bid, f"u-{name}", "https://app.go.kizen.com"
            )
        )
    monkeypatch.setattr(
        profiles, "load_pin", lambda start=None: profiles.Pin("beta", "BBBB", "/x")
    )

    result = runner.invoke(cli.app, ["envs", "list", "--json"])
    assert result.exit_code == 0, result.output
    rows = {r["label"]: r for r in json.loads(result.stdout)}
    assert rows["beta"]["pinned"] is True
    assert rows["alpha"]["pinned"] is False
    assert rows["beta"]["source"] == "profile"


def test_command_refuses_when_pin_business_id_mismatches(monkeypatch):
    from kizen_builder import config, profiles

    config.set_profile_override(None)
    profiles.write_profile(
        profiles.ProfileCreds("alpha", "k", "AAAA", "u", "https://app.go.kizen.com")
    )
    # Directory claims a different identity than the resolved profile.
    monkeypatch.setattr(
        profiles, "load_pin", lambda start=None: profiles.Pin("alpha", "ZZZZ", "/x")
    )

    result = runner.invoke(cli.app, ["team", "search", "someone"])
    assert result.exit_code == 1
    assert "Refusing" in result.stderr


# ---------------------------------------------------------------------------
# forms & surveys — same factory-built app, smoke-test both command groups
# ---------------------------------------------------------------------------


def test_forms_list_json(monkeypatch):
    fake = [
        {
            "env": "testenv",
            "id": "abc",
            "name": "Contact Us",
            "api_name": "contact_us",
            "n_submissions": 3,
            "template_type": "modern",
            "deleted": False,
        }
    ]
    seen = {}

    def fake_list(*, base_path=None, search=None):
        seen["base_path"] = base_path
        return fake

    monkeypatch.setattr(form_tools, "list_forms", fake_list)
    result = runner.invoke(cli.app, ["forms", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == fake
    assert seen["base_path"] == "/api/forms"


def test_surveys_list_json_uses_surveys_base_path(monkeypatch):
    fake = [
        {
            "env": "testenv",
            "id": "abc",
            "name": "NPS",
            "api_name": "nps",
            "n_submissions": 1,
            "template_type": "modern",
            "deleted": False,
        }
    ]
    seen = {}

    def fake_list(*, base_path=None, search=None):
        seen["base_path"] = base_path
        return fake

    monkeypatch.setattr(form_tools, "list_forms", fake_list)
    result = runner.invoke(cli.app, ["surveys", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == fake
    assert seen["base_path"] == "/api/surveys"


def test_forms_get_table_shows_fields(monkeypatch):
    fake = {
        "env": "testenv",
        "id": "abc",
        "name": "Contact Us",
        "api_name": "contact_us",
        "description": None,
        "template_type": "modern",
        "related_object": "client_client",
        "n_submissions": 0,
        "fields": [
            {
                "id": "f1",
                "api_name": "email",
                "display_name": "Email",
                "field_type": "email",
                "is_required": True,
                "is_hidden": False,
                "order": 0,
                "options": None,
            }
        ],
        "raw": {},
    }
    monkeypatch.setattr(
        form_tools,
        "get_form",
        lambda identifier, base_path=None, include_fields=True: fake,
    )
    result = runner.invoke(cli.app, ["forms", "get", "contact_us"])
    assert result.exit_code == 0, result.output
    assert "Contact Us" in result.stdout
    assert "email" in result.stdout


def test_forms_create_dry_run(monkeypatch):
    def fake_plan_create(spec, *, base_path=None, kind=None):
        assert spec["name"] == "X"
        assert spec["related_object"] == "client_client"
        assert base_path == "/api/forms"
        assert kind == "form"
        return plan_tools.Plan.build(
            env="testenv", summary="Create form 'X'", operations=[]
        )

    monkeypatch.setattr(form_planners, "plan_create_form", fake_plan_create)
    result = runner.invoke(
        cli.app,
        [
            "forms",
            "create",
            "--name",
            "X",
            "--related-object",
            "client_client",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output


def test_forms_fields_list_is_cli_wired(monkeypatch):
    def fake_get_form(identifier, *, base_path=None, include_fields=True):
        assert identifier == "contact_us"
        assert base_path == "/api/forms"
        return {"name": "Contact Us", "fields": []}

    monkeypatch.setattr(form_tools, "get_form", fake_get_form)
    result = runner.invoke(cli.app, ["forms", "fields", "list", "contact_us"])
    assert result.exit_code == 0, result.output


def test_forms_delete_dry_run(monkeypatch):
    def fake_plan_delete(identifier, *, base_path=None, kind=None):
        assert identifier == "contact_us"
        assert base_path == "/api/forms"
        assert kind == "form"
        return plan_tools.Plan.build(
            env="testenv", summary="Delete form 'X'", operations=[]
        )

    monkeypatch.setattr(form_planners, "plan_delete_form", fake_plan_delete)
    result = runner.invoke(cli.app, ["forms", "delete", "contact_us", "--dry-run"])
    assert result.exit_code == 0, result.output


def test_forms_duplicate_dry_run(monkeypatch):
    def fake_plan_duplicate(identifier, *, name=None, base_path=None, kind=None):
        assert identifier == "contact_us"
        assert name == "Copy"
        assert base_path == "/api/forms"
        assert kind == "form"
        return plan_tools.Plan.build(
            env="testenv", summary="Duplicate form 'X'", operations=[]
        )

    monkeypatch.setattr(form_planners, "plan_duplicate_form", fake_plan_duplicate)
    result = runner.invoke(
        cli.app, ["forms", "duplicate", "contact_us", "--name", "Copy", "--dry-run"]
    )
    assert result.exit_code == 0, result.output


def test_perms_group_renders_resolution_warnings_on_stderr(monkeypatch):
    """`describe_group`'s name resolution is best-effort and reports what it
    couldn't resolve. Those warnings go to stderr so stdout stays pure result
    data in every format; `--json` also carries them in the payload."""
    view = {
        "id": "g1",
        "name": "Sample Group",
        "user_count": 1,
        "role_count": 1,
        "summary": {},
        "blocks": [],
        "warnings": ["could not resolve object and field names (boom)"],
    }
    monkeypatch.setattr(perm_tools, "resolve_group", lambda ref: {"id": "g1"})
    monkeypatch.setattr(
        perm_tools, "describe_group", lambda gid, include_fields=False: view
    )

    result = runner.invoke(cli.app, ["permissions", "group", "Sample Group", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == view  # stdout is pure result JSON
    assert "warning: could not resolve object and field names" in result.stderr
