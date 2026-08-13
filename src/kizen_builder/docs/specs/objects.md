# Surface: objects, categories & pipeline stages

Objects and categories are **flag-driven** — there is no spec file. Build an
object with fields in three steps:

```bash
kizen objects create --api-name … --name … --object-type …   # then --help for the rest
kizen categories create <object> --name …
kizen fields create <object> --spec-file fields.json         # kizen docs show field
```

## `objects get` is the lookup you want

`kizen objects get <object>` returns categories, every field with its **UUID
inline**, and every choice/status/yesnomaybe field's `options` array as
`{id, name, code}`. **There is no separate call needed for option UUIDs** — this
is the answer to "how do I find the option UUID for X".

It also resolves each relationship field's target to a readable api_name plus
cardinality, so you never hand-resolve a `related_object` UUID.

One thing it does **not** cover:

- Pipeline **stages** are a separate resource, below.

`kizen objects list` includes built-in objects (Contacts, identifier
`client_client`) alongside custom ones. `kizen objects get client_client`
returns their field schema and option UUIDs in the same format as any custom
object.

## Kizen rewrites api_names

Create an object with `api_name: invoice` and Kizen may store `invoices`
(pluralization). Same for field api_names. **Always read back after writing**
(`kizen objects get <object>`) and reference the server's stored name from then
on — a spec that assumes its own api_name survived will resolve against nothing.

## Pipeline stages

A pipeline object's stages are a **separate entity**, not the object's own field
options:

```
GET   /api/pipelines/{object_pk}/stages                  # list, ?ordering=order
POST  /api/pipelines/{object_pk}/stages                  # create: {name, status, order} required
PATCH /api/pipelines/{object_pk}/stages/{id}             # partial update
POST  /api/pipelines/{object_pk}/stages/remove-stage     # delete + migrate: {id, new_stage_id}
PATCH /api/records/{object_identifier}/{entity_id}/move  # move one record: {stage_id}
```

CLI: `kizen objects stages list|create|update|remove <pipeline>`, and
`kizen records move` as the runtime counterpart.

- `status` is one of `open | won | lost | disqualified`.
- **There is no bare DELETE on a stage.** `remove-stage` always migrates the
  removed stage's records onto `new_stage_id`, which is why `objects stages
  remove` requires `--move-to`.
- `object_pk` here is the pipeline's **custom-object UUID** — the same one
  `objects get <pipeline>` returns. You never need the `/api/pipelines`
  collection endpoint; a pipeline resolves through `/api/custom-objects` and
  carries a `stages` list when `object_type == "pipeline"`.

### The mirrored `stage` field is a read-only projection

A pipeline object also has a choice-type field whose options exactly match the
live stage ids (whatever its api_name). It looks editable and is not:
`POST .../fields/{id}/options` against it **returns 200 with a UUID**, but the
option never appears in `/api/pipelines/{id}/stages` nor in the field's own
option list, and the returned UUID 404s on any follow-up.

`kizen fields options add/remove` detects a stage-backed field — by exact
option-id-set equality against the live stages, not by field api_name — and
refuses, rather than reporting the fake success the API hands back. Use
`objects stages` instead.

## See also

- `kizen docs show field` — field spec shape, type-specific blocks, reserved
  api_names, and relationship-field creation.
- `kizen docs show records` — the records CRUD surface, including
  `records move` between stages.
- `kizen docs show layout` — how fields get arranged on the record page.
