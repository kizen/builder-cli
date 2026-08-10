# Test fixtures

Real Kizen API output captured via the CLI from internal test environments,
then sanitized (people, emails, env labels, and external product names
replaced; no credentials, business IDs, or signed URLs were ever present).
Internal UUIDs are kept intact so cross-references between files still
resolve (e.g. option UUIDs inside object fields, field UUIDs inside
automation steps).

## Shapes

- `objects/*.json` — `kizen objects get <name> --json` output (tool-level
  shape: `api_name`, `categories`, `fields` with inline `options`).
  `objects/list.json` is `kizen objects list --json`.
- `automations/*.raw.json` — `kizen automations get <name> --raw` output
  (the unmodified API response). `automations/list.json` is the tool-level
  list output.
- `records/`, `executions/`, `team/` — tool-level `--json` output.
  Exceptions: `executions/detail_form_submission.json` and
  `executions/history_form_submission.json` are hand-authored to the OpenAPI
  schemas (`ReadAutomationExecution` / `LightAutomationHistoryWithDescription`)
  rather than captured live. They back `test_runs.py`'s endpoint-path and
  field-mapping regression tests.
- `errors/html_404.html` — the HTML body the API returns on 404 (e.g. a wrong
  path such as the old trailing-slash execution-detail URL), used to test
  error extraction.
- `permissions/*.json` — hand-authored (not captured live) to a trimmed but
  representative shape: `permission_group_detail.json` carries one section
  permission in each wire dialect (`view_all_dashboards` as a bare bool,
  `manage_automations` as `{view, edit, remove}`) plus one contacts block and
  one custom object, each with a field. `permissions_meta_data.json` is the
  matching catalog. `permission_group_list.json`, `role_list.json`, and
  `role_detail.json` round out the read/resolve surface. Invented UUIDs
  follow `conftest.py`'s `00000000-0000-4000-8000-…` convention.

## Coverage

Field types covered across the object fixtures: text, longtext, email,
phonenumber, checkbox, checkboxes, dropdown, status, yesnomaybe, radio,
date, datetime, integer, decimal, money, files, rating, relationship,
team_selector, dynamictags, timezone. (`radio`/`rating` specimens: `patients`
`preferred_contact_method`/`pain_level`, captured live 2026-07-20 — a `rating`
field with no `--option`s given auto-generates a 5-point scale with codes
`"1"`-`"5"`, confirmed live.)

Trigger types covered: manual, new_entity_created, activity_logged,
on_or_around_date, webhook, schedule (unsupported-type error path).
Step types covered: condition, code_step, stop_execution, archive_record,
go_to_automation_step, start_automation, change_field_value,
modify_related_entities, create_related_entity, initialize_variable,
update_variable, call_llm, file_content_extraction, schedule_activity,
delete_scheduled_activity (unsupported-type error path).

## Refreshing

Re-capture with the read-only CLI commands above and re-run the sanitizer
(replacements listed at the top of the script) before committing. Never
commit raw captures directly.
