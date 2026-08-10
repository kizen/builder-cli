"""Kizen smart-connector local execution runtime, vendored from the dev package.

`script_runner.ChDBScriptRunner` mirrors production connector execution
semantics (the input/output/connector/kizen/meta database model, the column
type mapping, partial-output-on-error, resource limits). We vendor it verbatim
rather than reimplement it so that a connector's SQL behaves identically when
run locally via `kizen smart-connectors run` and when Kizen runs it for real.

See PROVENANCE.md for the upstream source and the (minimal) local deltas.

Importing this *package* (`connector_runtime`) is side-effect-free. Importing
its `script_runner` submodule pulls in `python_calamine` + `charset_normalizer`
at module top and (lazily, inside `ChDBScriptRunner.session`) `chdb` — all part
of the optional `connectors` extra. So the inspection-only CLI paths must import
`script_runner` lazily, inside the run/add-input functions, never at module
top; that keeps `list`/`get`/`executions` dependency-free. Install the
`connectors` extra to actually run scripts locally.
"""
