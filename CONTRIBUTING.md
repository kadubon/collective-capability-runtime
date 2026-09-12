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

If publishing fails before upload, correct the publishing infrastructure on
`main`, then dispatch `workflow.yml` with the existing published release tag.
The workflow checks out that tag and verifies its package version, preserving
the release source instead of moving the tag. Check PyPI for partial uploads
before retrying; do not replace existing distribution files.


## Verified growth opt-in (v1.8)

Use the separate `ccr.growth_profile.v1` registration with
`policy=verified_growth_v1` to enable receiver-specific service accounting and
finite dependency-bundle allocation. Existing v1 optimizer schemas and signing
bytes remain unchanged. See [Verified Growth](docs/verified-growth.md) for the
complete register, check, reserve, lease, signed outcome, reuse, replay and
frozen-comparison path. Service observations, planning forecasts and causal or
statistical improvement are distinct. Growth does not grant admission, approval
or settlement authority. Unresolved attribution and invalidated evidence remain
visible; synthetic records cannot establish production performance.
