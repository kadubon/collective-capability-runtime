# Contributing

Related optional PIC project:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

## Setup

```bash
python -m pip install collective-capability-runtime
uv sync
uv run ccr agent explain --json
```

## Tests

```bash
uv run ruff check .
uv run pytest
uv run ccr audit repo --json
uv build
uvx twine check dist/*
```

## Coding Style

- Use the `src/` layout.
- Keep JSON outputs stable and machine-readable.
- Keep side effects local and explicit.
- Preserve residuals instead of deleting uncertainty.
- Add SPDX headers to Python source files.
- Prefer standard-library implementations unless a dependency removes real risk.

## Schema Changes

Schema changes must update:

- `schemas/*.schema.json`
- examples
- tests
- `SPEC.md`
- `CHANGELOG.md`

Do not perform git operations unless the operator explicitly asks.

## Release Preparation

CCR publishes as `collective-capability-runtime` through GitHub Trusted
Publishing. The release workflow is `.github/workflows/workflow.yml` and must
not require PyPI token, username, or password secrets.
