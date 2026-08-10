"""Tool functions Claude (or any caller) invokes against a Kizen environment.

Every tool takes ``env: str`` as its first argument — a local credential label
configured via ``kizen init``. There is no global "current env" state; each
call discloses the target env explicitly so it's impossible to fire at the
wrong environment by accident.

Tool returns are plain Python dicts/lists ready for JSON serialization. The
CLI layer wraps these for terminal use; future MCP/Claude-plugin layers can
wrap the same functions without modification.
"""
