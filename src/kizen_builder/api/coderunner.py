"""Code Runner endpoint — run a Python script in the code_step sandbox.

``POST /api/coderunner/run`` executes a script in the same secure Lambda
sandbox that automation ``code_step`` steps use, standalone: no automation,
no record, no PUT. It creates nothing in the env, so like ``automations
start`` it is a runtime action, not a schema mutation.

The request/response shapes are ``CodeRunnerRequestRequest`` /
``CodeRunnerResponse``. See :mod:`kizen_builder.tools.coderunner` for the
``{t, v}`` encoding and the tool-level normalization of the response.
"""

from __future__ import annotations

from typing import Any

from kizen_builder.api.client import KizenClient


def run_code(client: KizenClient, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/coderunner/run. Returns the parsed CodeRunnerResponse.

    ``payload`` is the fully-formed wire body (``runtime``, ``user_script``,
    ``inputs``, ``output_types``, ``secrets``). Non-2xx responses raise
    :class:`~kizen_builder.api.client.KizenAPIError`; validation failures come
    back as HTTP 400 with a field-keyed error dict attached to
    ``KizenAPIError.body``.
    """
    return client.post("/api/coderunner/run", json=payload)
