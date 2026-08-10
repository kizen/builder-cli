# Surface: automation runtime — starting, watching, and controlling runs

Everything about an automation *execution* (a run), as opposed to the
automation's own definition. Runs are runtime state, not schema, so these
commands sit outside the plan→preview→confirm gate.

- The automation **definition** → `kizen docs show automation`
- Editing **one step** of a definition → `kizen docs show automation-step`

## Starting a run

```bash
kizen automations start <api_name> --record <uuid>
kizen automations start <api_name> --record <uuid> --var org_match=true
```

Confirm-free by standing decision: it triggers an *existing* automation on a
record, creating and altering nothing, so there is no plan to preview.

```
POST /api/automation2/automations/<automation-identifier>/start
{
  "record_id": "<uuid>",       # custom-object records
  "client_id":  "<uuid>",      # OR this, for contact (client_client) automations
  "variable_overrides": [ {"variable_name": "org_match", "value": "true"} ]
}
```

- `record_id` and `client_id` are **mutually exclusive** — contacts use
  `client_id`, custom-object records use `record_id`. The CLI routes one
  `--record` to the right key for you.
- `--record` is optional: global (record-less) automations start without it.
- **`variable_overrides` is a list, not a dict** (`StartAutomationRequest` →
  `VariableOverrideRequest`), keyed by the variable's `name` (not id), and
  `value` is always a **string** (nullable) that the server coerces by the
  variable's `data_type`. Verified against the public schema at
  `/api/docs/public/schema` plus a live start.
- Response is `{"execution": {ReadAutomationExecution}}` — or
  `{"execution": null}` if a UUID was passed as the identifier instead of the
  api_name.

## Watching a run

```
GET /api/automation2/automation-execution?automation_id=<uuid>&record_id=<uuid>&size=25
GET /api/automation2/automation-execution/<execution-id>
GET /api/automation2/automation-execution/<execution-id>/history
```

`size` maxes at 100. CLI: `kizen automations runs list <api_name>`, and
`runs view <exec_uuid>` (`--no-steps` for the summary half only).

- Detail response has `status`, `record`, `automation`, `debug_mode`, `created`
  (≈ started) and `updated` (≈ finished). There is **no** `started_at` /
  `finished_at`.
- **No trailing slash** — `…/<execution-id>/` 404s with an HTML page; the
  router only registers the slashless path.
- In `/history`, each row is one step or trigger firing. Type and human
  description live in a nested `step` / `trigger` object (`{type,
  description}`), **not** at the row top level. Timing is `execution_time_ms`
  (null for async steps like `code_step` / `call_llm`) plus `created` /
  `updated`.

## Controlling a run

Confirm-free, same standing decision as `start`. CLI: `kizen automations runs
pause|resume|cancel|skip-and-resume|debug-rerun|debug-restart|debug-step|debug-sendit <exec>`.

```
POST /api/automation2/automation-execution/<id>/pause
POST /api/automation2/automation-execution/<id>/play             # resume
POST /api/automation2/automation-execution/<id>/cancel           # irreversible
POST /api/automation2/automation-execution/<id>/skip-and-resume
POST /api/automation2/automation-execution/<id>/debug-sendit     # run a debug execution to completion
POST /api/automation2/automation-execution/<id>/debug-rerun      # re-run one step, nothing after it scheduled
POST /api/automation2/automation-execution/<id>/debug-restart    # restart from a step, subsequent steps ARE scheduled
POST /api/automation2/automation-execution/<id>/debug-step       # skip or execute one step of a debug execution
```

**Confirmed live 2026-07-22** for pause/play/cancel against a real delayed
execution — status flipped `active` → `paused` → `active` → `cancelled` on the
following GET each time. The `debug-*` verbs are wired from the schema shapes
only, not live-exercised.

### The oddly-heavy shared request body

pause / play / cancel / debug-sendit all take a
`LightReadAutomationExecutionRequest`: `id`, `automation_id`, `client_id`,
`record_id`, `status`, `trigger_history_id`, `debug_mode` — **all marked
required** by the schema, despite the action being implied entirely by the
endpoint rather than by anything in the body.

In practice, echo the execution's own current `GET`, current `status` included.
Sending the *pre-transition* status worked fine in every direction tested, so
the field is presumably read-only in effect despite being schema-required. The
CLI builds this body from a live execution read — don't hand-construct it.

Per-verb bodies:

- **`skip-and-resume`** — `InlineFormRequest`: `{skip_step_id,
  continue_with_branch?}` (`"yes"`/`"no"`). Resumes an execution paused on a
  step failure by skipping that step.
- **`debug-rerun` / `debug-restart`** — `DebugRerunRequest`: `{step_id}`.
- **`debug-step`** — `DebugStepRequest`: `{action: "execute"|"skip"|"debug",
  history_id, continue_with_branch?}`.

All of these returned an empty/`null` body in testing, which is why the CLI
re-`GET`s the execution afterward to report the before/after status.

## Diagnostics

Read-only and paginated:

```
GET /api/automation2/automations/<identifier>/modification-history
  ?date_from=<iso>&date_to=<iso>&event_type=<type>&search=<text>
GET /api/automation2/automations/<identifier>/histories/failures?page=<n>&page_size=<n>
```

CLI: `kizen automations modification-history <api>` / `kizen automations
failures <api>`. `modification-history` accepts many more filters than the CLI
exposes (`custom_object_ids`, `has_comment`, `role_ids`, `team_member`,
`include_related`, `ordering`).

## See also

- `kizen docs show code-steps` — `kizen code test` unit-tests a `code_step`
  script without a run at all; prefer it over starting automations to debug
  script logic.
