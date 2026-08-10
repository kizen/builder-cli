# Spec shape: permission-group shaping ops

**Consumed by:** `kizen permissions group-create --settings-file <f>`.

A group is created at a **base** (`--base default` = fresh group at Kizen's
default levels, or `--base clone --from <group>` = copy an existing group).
The `--settings-file` is an optional **JSON list of shaping ops** applied
*after* creation to raise/lower specific permissions.

> To see the current level structure of a group (section/object/field keys and
> the levels each accepts), read a live one: `kizen permissions group <name>`
> (add `--fields` for per-field rows, `--raw` for wire JSON).

---

## Quick example

```json
[
  { "type": "object",  "object_id": "<object_uuid>", "key": "records", "level": "edit" },
  { "type": "field",   "object_id": "<object_uuid>", "field_id": "<field_uuid>", "level": "view" },
  { "type": "section", "section_key": "automations", "value": true }
]
```

```bash
kizen permissions group-create --name "Sales Ops" --settings-file ops.json --dry-run
```

## Op shapes

| `type` | Keys | Effect |
|--------|------|--------|
| `object` | `object_id`, `key`, `level` | Set an object-level permission (e.g. `records`, `custom_fields`) to `level`. |
| `field`  | `object_id`, `field_id`, `level` | Set a per-field control to `level`. |
| `section` | `section_key`, `value` | Toggle/set an app-section permission. |

`level` is a level **name** (`none`, `view`, `edit`, `remove`, …) or its integer
index — the valid range per control comes from that control's `allowed_access`
(visible in `permissions group <name>`).

## Gotchas

- **Names, not UUIDs, everywhere they can be** — `--from` takes a group name or
  UUID. But `object_id`/`field_id` inside ops are **UUIDs**; get them from
  `kizen objects get <api_name> -o json` and `kizen permissions group <name>`.
- Roles attach permission groups — see `kizen roles create/update --group ...`.

---

# Wire format & API behavior

Three related surfaces:

- **`/api/role`** — a Role bundles `permissions` (app-level string flags),
  `permission_groups` (a list of group UUIDs), and `default_for_new_users`.
  Roles are what team members are assigned.
- **`/api/permission-group`** — a named bundle of per-entity access levels:
  custom objects + their fields, contacts, and ~20 feature "sections"
  (homepages, dashboards, settings, …).
- **`/api/permissions/meta-data`** — the catalog: which sections/capabilities
  exist, their `label`, `affordance` (`range` slider / `switch` / `checkbox`),
  `allowed_access`, `default`, `category`, display `order`, and the cross-field
  `rule`s.

## Access levels

Integers **0–3 = none / view / edit / remove**, matching the UI columns
None / View / Create·Edit / Delete·All and the group `summary` counts
(`nb_none`/`nb_view`/`nb_edit`/`nb_remove`).

**On the wire a single permission serializes inconsistently** — some as a bare
bool, others as `{"view": bool, "edit": bool, "remove": bool}`. **Never
synthesize the shape.** The CLI reads an existing group as a shape *template*
and only resets leaf values, which is why `group-create` needs a `--base`.

## Write model (verified live)

- **Create needs the FULL structure.** `POST /api/permission-group` with just
  `{name}` 400s (`"Custom Objects missing: …"` / `"enabled: required"`). It must
  include every custom object (plus its fields), every `*_section`, and
  contacts. `kizen permissions group-create` builds this from the meta defaults,
  or `--base clone` copies an existing group as-is.
- **Sections** are written with `PATCH /api/permission-group/{id}` and the
  **complete** section dict — partials 400
  (`"customize_homepages: This field is required."`).
- **Custom object + field perms** go through a different endpoint:
  `PATCH /api/permission-group/{id}/object-update` with
  `{custom_object: {id}, field?: {id}, key?, permission_level: 0-3}`.
- **A full PUT** `/api/permission-group/{id}` replaces the whole structure, but
  is subject to cross-field **rules** — e.g. `associated_records ≥ all_records`,
  `unarchive_all ≤ unarchive_associated`, `create_record` needs
  `associated ≥ edit`, `bulk_data_upload` needs `create_record`. `object-update`
  and section PATCH normalize dependents for you; a hand-built full PUT must
  satisfy them or it 400s. The meta `rule` field encodes these.
- **Role create quirk:** an explicit empty `permissions: []` is rejected
  (`"This list may not be empty."`) — **omit the key** and it stores `[]`.
- **List vs detail:** the list endpoint zeroes `summary` and omits real counts;
  the detail GET has `summary`, while `user_count`/`role_count` come from the
  list entry. Getting both means two calls.

## Command surface

`kizen roles list|get|create|update|delete` and `kizen permissions
groups|group|meta|group-create|group-delete`. **Names are accepted anywhere a
role or group is referenced** — resolved to a UUID, with an available-list on a
miss. `kizen permissions group <name> [--fields]` renders the sectioned slider
view that mirrors the permission editor.

## See also

- `kizen permissions meta` — the live catalog (sections, capabilities, defaults).
- `kizen docs show objects` — where object/field UUIDs come from.
