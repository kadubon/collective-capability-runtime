# Security Policy

Related optional PIC provider:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

Installing PIC does not grant CCR execution authority or settlement authority.

## Threat Model

CCR assumes packets, tasks, reports, residuals, provider payloads, provider
configs, and safe commands may be malicious, stale, malformed, or overclaiming.
All external content remains candidate-only until validated and promoted through
CCR policy.

CCR does not claim real ASI detection, real ASI creation, model self-rewrite,
model weight update, execution authority, or safety bypass.

## First-time agent guide

Purpose: use this document to identify which CCR actions are inspection,
local-artifact mutation, provider execution, or overclaim risk.

First commands:

```bash
ccr agent explain --json
ccr audit repo --json
ccr provider health --provider pic --json
ccr provider plan --provider pic --action verify_packet --packet <packet_id> --json
```

Safe boundary: default operation is dry-run and local-first; external HTTP or
PIC execution requires an explicit command path, explicit config where
applicable, and operator authority.

Expected outputs: security-relevant failures return JSON with `ok=false`,
provider health, failure reports, residuals, or `residual_ready` objects.

Failure/residual handling: preserve malicious, malformed, stale, unsafe,
authority-gap, and missing-provider cases as residual evidence.

Provider import: provider import is not provider execution; `safe_commands`
become review tasks only.

Phase formation cycle: phase diagnostics may identify better next work, but
they do not prove real ASI or authorize execution.

What not to claim: never claim that a packet, provider report, phase candidate,
or safe command bypasses safety or grants authority.

## Default Execution Boundary

The default mode is dry-run. CCR does not execute PIC, HTTP, shell, or other
provider actions unless the operator explicitly runs a CCR command that includes
the required execution flag.

Planning commands must not perform hidden network behavior:

```bash
ccr verify --provider pic --packet <packet_id> --json
ccr provider plan --provider http --action webhook --file payload.json --json
ccr phase form --profile development --json
```

Local JSON and SQLite artifacts may be written by mutating CCR commands. External
side effects are forbidden by default.

## PIC Provider

PIC is optional. CCR checks availability dynamically. Missing PIC returns JSON
with exit code 2 and a provider-missing residual-ready object, not a crash.

```bash
ccr provider health --provider pic --json
ccr audit pic --pic-root <PIC_ROOT> --json
```

When PIC execution is requested, CCR:

- uses an argv list
- uses `shell=False`
- applies a bounded timeout
- captures stdout and stderr
- stores the report under `reports/pic/`

PIC `accepted=true` does not imply CCR `settled`. PIC `settled=true` is still
subject to CCR integration, phase, baseline, and residual gates.

PIC safe commands are recommendations for inspection, never execution authority.

## HTTP Provider

The HTTP provider performs no network call during `plan`. Execution requires all
of the following:

- `ccr provider execute`
- an explicit `--execute` flag
- an explicit JSON config file
- `allow_execute=true` in that config
- an endpoint beginning with `http://` or `https://`
- an allowlisted method (`GET` or `POST`)
- a bounded `timeout_seconds`
- a bounded `byte_limit`

Outbound headers named `authorization` or `cookie` are not forwarded by the
provider helper. Responses are capped by `byte_limit`. Provider execution
returns an audit report under `reports/providers/<provider>/`.

HTTP provider failures return residual-ready JSON. A failed provider call must
not be silently promoted into packet, graph, or phase evidence.

## Provider Imports

Provider reports may contain unsafe command suggestions. CCR maps:

- `candidate_only_reasons` to residuals
- `settled_blockers` to blocking residuals
- `safe_commands` to task hints under `tasks/open`

Safe commands are not executed automatically.

## Public Release Boundary

Public release artifacts must not contain local home paths, user-specific
machine identifiers, generated CCR runtime state, SQLite databases, cache
directories, private-key material, or assignment-like credentials.

Release hygiene is checked after building distributions:

```bash
uv build
ccr audit release --dist dist --json
uvx twine check dist/*
```

The audit scans source files and wheel/sdist contents. Provider safe commands,
PIC reports, and HTTP payloads remain data only; they must not become hidden
execution authority during packaging or publication.

## Malicious Packet and Residual Handling

CCR validates packet and task JSON against local schemas. Invalid objects are not
stored by submit commands. Validation failures return residual-ready objects so
agents can preserve the failure without corrupting runtime state.

Residuals are append-preserved. Blocking residuals prevent settlement by
default. `settled=false` is expected diagnostic state.

## Baseline and Phase Overclaim Risk

`phase graph`, `phase observe`, `phase threshold`, `phase compare`, `phase form`,
and `phase certify` are protocol-relative diagnostics. They do not prove real
ASI, oracle truth, physical outcome truth, or future execution.

Resource-envelope mismatches become residual-ready blockers. Candidate-only or
duplicate packet volume is not positive phase contribution.

## Supply Chain

CCR uses a small dependency footprint and a local-file runtime. CI should run:

```bash
uv sync --all-extras
uv run ruff check .
uv run pytest
uv run ccr audit repo --json
```

Report security issues through the repository issue tracker or a private
advisory channel when available.
