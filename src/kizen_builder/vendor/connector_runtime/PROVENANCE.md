# connector_runtime — provenance

Vendored from the **Kizen smart-connector development package** ("my-connector-package")
that Kizen generates when you download a connector's local dev bundle.

## Files

| file | upstream | local delta |
|------|----------|-------------|
| `script_runner.py` | dev package `script_runner.py` | **verbatim, no edits** — this is the prod-fidelity execution engine |
| `process_new_input_file.py` | dev package `process_new_input_file.py` | import made relative (`from .script_runner`) and `process_new_input_file(input_path, workdir=None)` parametrized so it can run against an arbitrary working directory instead of the module's own folder |

`script_runner.py` is kept byte-for-byte identical to upstream on purpose: a
connector's SQL must behave the same locally and in production. Do **not** edit
it to fix a local-only concern — parametrize from the calling `tools/` layer
instead. When Kizen ships a new dev package, re-copy `script_runner.py` verbatim
and re-apply the two `process_new_input_file.py` deltas.

The `__main__.py` from the dev package is intentionally NOT vendored; its
`main()` (chdir + read `__config.json` + read `connector.sql` + run) is
reimplemented in `tools/smart_connectors.py` so it can target any workdir.

## Runtime dependencies

`script_runner.py` imports `chdb` (embedded ClickHouse), `python_calamine`, and
`charset_normalizer`. These are declared as the optional `connectors` extra in
`pyproject.toml`, not core deps — `import`ing this package does not pull them in
(`chdb` is loaded lazily inside `ChDBScriptRunner.session`).
