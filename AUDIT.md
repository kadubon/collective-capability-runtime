# CCR v1 Repository Audit

Related optional PIC project:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

Date: 2026-06-30

## Scope

This audit covers the repository-level v1 readiness checks exposed by:

```bash
uv run ccr audit repo --json
uv run ccr audit pic --pic-root <PIC_ROOT> --json
uv run ccr provider health --provider pic --json
```

`<PIC_ROOT>` is a placeholder for a local PIC source checkout, such as
`../percolation-inversion-compiler`. Public files must not contain
user-specific local paths.

The audit checks README positioning, docs/security/agent guidance, required JSON
schemas, CLI surface, CI presence, SPDX headers, provider safety language, and
non-claim preservation. It also checks PyPI Trusted Publishing readiness for
`.github/workflows/workflow.yml` and prevents generated phase runtime artifacts
from being shipped as source examples.

PIC compatibility audit checks the optional PIC source root, installed package
and CLI availability, expected v0.6.0 commands, report fields, provider mapping,
safe-command handling, and the rule that PIC output never settles CCR by itself.

Public release audit checks source files and built wheel/sdist archives for
local path leakage, generated runtime artifacts, caches, build state, private-key
blocks, and assignment-like credentials:

```bash
uv build
uv run ccr audit release --dist dist --json
uvx twine check dist/*
```

## First-time agent guide

Purpose: run repository and PIC audits before trusting a local CCR checkout for
agent work or release publication.

First commands:

```bash
ccr audit repo --json
ccr audit pic --pic-root <PIC_ROOT> --json
ccr provider health --provider pic --json
```

Safe boundary: audits inspect files, docs, schemas, workflows, provider routes,
and compatibility markers; they do not execute provider safe commands.

Expected outputs: audit reports contain `ok`, finding counts, blocking flags,
finding ids, and `residual_ready` objects for every issue.

Failure/residual handling: a failed audit is actionable protocol state; preserve
the finding and repair it before release or settlement promotion.

Provider import: audit validates the import boundary but does not import or
execute provider reports itself.

Phase formation cycle: repository audit checks that phase formation examples,
schemas, docs, CI, and non-claims remain aligned before agents rely on them.

What not to claim: a passing audit means the release gates are satisfied; it is
not proof of real ASI, external authority, or provider execution.

## Current Findings

Blocking findings: none after the v1 implementation pass.

Non-blocking findings: none expected after SPDX header cleanup.

Residual policy: any future audit finding is emitted with a `residual_ready`
object so agents can preserve the issue without corrupting runtime state.

## Acceptance Commands

```bash
uv sync --all-extras
uv run ruff check .
uv run pytest
uv run ccr audit repo --json
uv run ccr audit pic --pic-root <PIC_ROOT> --json
uv run ccr --root examples/phase_formation phase form --profile development --json
uv build
uv run ccr audit release --dist dist --json
uvx twine check dist/*
```

## Non-Claims Preserved

CCR does not prove real ASI, create real ASI, self-modify models, update model
weights, grant execution authority, bypass safety, or convert PIC/provider
output into settled capability by itself.
