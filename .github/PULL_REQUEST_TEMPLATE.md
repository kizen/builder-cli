## What & why

<!-- What does this change, and why does it matter? Link an issue if there is one. -->

## Checklist

- [ ] Tests are green locally (`uv run pytest`), and I ran the wheel tier too if I touched packaging (`pyproject.toml`, `docs/specs/`, anything under `src/kizen_builder/docs/`).
- [ ] `CHANGELOG.md` is updated under `[Unreleased]` if a user of the CLI would notice this change. Internal refactors don't need an entry.
- [ ] No customer or test-environment names anywhere — code, tests, docs, commit messages. Neutral placeholders only.
- [ ] If this adds a new file under `src/kizen_builder/docs/`, it's covered by a `package-data` glob in `pyproject.toml` (`tests/test_docs_packaging.py` enforces this, but check before pushing).
- [ ] If this adds a new surface or cross-cutting doc topic, it's listed in `specs/README.md` / `reference.md`'s router table (or `GUIDE_TOPICS` for cross-cutting topics).
