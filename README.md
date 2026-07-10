# Collective Capability Runtime

Collective Capability Runtime (CCR) is a JSON-first runtime for coordinating
work across AI agents. It keeps tasks, evidence, disagreements, verification,
and remaining work visible so that several agents can build reusable capability
without treating repeated answers or raw agent count as proof.

CCR does not run an LLM. Agents and tools use its CLI, JSON schemas, SQLite or
PostgreSQL state, and optional HTTP API to exchange auditable work.

## Vision And Measurement

CCR supports protocol-relative ASI-proxy phase formation. In ordinary terms,
this means improving the rate at which a bounded team produces checked,
reusable results under declared authority and resource limits.

Progress is measured against a resource-matched baseline. Relevant measures
include time to checked status, residual half-life, verification yield,
effective independent contributors, error correlation, and communication or
verification cost. More agents or more candidate text alone do not count as
progress.

This protocol-relative state is not real ASI. CCR does not claim consciousness,
model-weight updates, legal authority, or a physical outcome merely because a
report was accepted.

## Install

Published package:

```bash
python -m pip install collective-capability-runtime
ccr agent explain --json
```

Repository checkout:

```bash
uv sync --all-extras
uv run ccr agent explain --json
```

Optional PostgreSQL, API, authentication, and worker support:

```bash
python -m pip install "collective-capability-runtime[distributed]"
```

Optional telemetry:

```bash
python -m pip install "collective-capability-runtime[telemetry]"
```

PIC is an optional finite checker and planning provider:

```bash
python -m pip install percolation-inversion-compiler
ccr provider health --provider pic --json
```

## Five-Minute Start

These commands work after installation. They create a local mission and a
human-readable workbench without calling a provider or network endpoint:

```bash
ccr --root ccr-runtime asi quickstart --profile development --json
ccr --root ccr-runtime mission next --mission mission:quickstart --compact --json
ccr --root ccr-runtime workbench report --mission mission:quickstart --format markdown --out CCR_WORKBENCH.md
ccr --root ccr-runtime residual market --mission mission:quickstart --json
```

Read `CCR_WORKBENCH.md`, then select a blocking residual or verification task.
`settled=false` is a normal report state: it means required work remains.

For a source-checkout example of independent proposals and a resource-matched
experiment, follow
[examples/collective_runtime/README.md](examples/collective_runtime/README.md).

## Choose A Workflow

| Goal | Start with | Guide |
|---|---|---|
| Create a local mission | `ccr asi quickstart` | [Getting Started](docs/getting-started.md) |
| Coordinate independent proposals | `ccr workcell create` | [Collective Workcells](docs/collective-workcells.md) |
| Recover and complete leased work | `ccr task lease` | [Collective Workcells](docs/collective-workcells.md) |
| Resolve a residual with independent evidence | `ccr residual resolve` | [Command Map](docs/command-map.md) |
| Run several workers | `ccr server run`, `ccr worker run` | [Distributed Runtime](docs/distributed-runtime.md) |
| Compare collective and baseline results | `ccr experiment register` | [Measurement Protocol](docs/measurement-protocol.md) |
| Review a possible external operation | `ccr operation preflight` | [Operation Gate](docs/operation-gate.md) |
| Check PIC compatibility | `ccr audit pic` | [PIC Interoperability](INTEROP_PIC.md) |
| Audit a public release | `ccr audit repo` | [Release Audit](AUDIT.md) |

## Core Concepts

- **Task:** a unit of work with dependencies, role, lease, heartbeat, and
  fencing token.
- **Capability packet:** a candidate or checked result with scope, evidence,
  provenance, and residual references.
- **Residual:** explicit unresolved work. Resolution requires a repair artifact
  and independent verifier evidence.
- **Workcell:** independent proposal, reveal, critique, revision, verification,
  and integration stages. Correlated sources count once.
- **Mission:** a target, baseline, packets, tasks, residuals, and reports under
  one declared scope.
- **Experiment:** a preregistered comparison with a task manifest, evaluator,
  resource envelope, seed, and outcome schema.
- **Operation approval:** a time-limited authorization bound to a plan,
  provider, arguments, resources, scope, nonce, and use count.

## Important Output Fields

CCR emits deterministic JSON where possible. Inspect these fields before
choosing the next action:

| Field | Meaning |
|---|---|
| `ok` | The command completed its finite validation or transition. |
| `accepted` | A local checker accepted the supplied evidence. It is not settlement. |
| `settled` | All declared settlement requirements passed. It is usually `false`. |
| `blockers` / `residuals` | Work that must remain visible. |
| `external_execution` | The command performed an external action. |
| `network_call_performed` | The command made a network request. |
| `physical_outcome_proven` | Deprecated compatibility field; always `false`. |
| `physical_outcome_verified` | A trusted signed observation passed scope and time checks. |
| `non_claims` | Statements the report explicitly does not assert. |

Unknown measurements remain unknown. CCR does not replace missing reuse,
hazard, queue, cost, or verifier values with favorable defaults.

## State And External Effects

Local inspection, schema validation, planning, and reporting do not perform
external effects. The following commands intentionally mutate local runtime
state:

| Command family | Local change |
|---|---|
| `asi`, `mission`, `workbench --out` | mission and report artifacts |
| `task lease|heartbeat|complete|fail|cancel|retry` | transactional task state |
| `residual assign|review|resolve|reopen` | residual workflow and evidence |
| `workcell create|submit|advance|integrate` | staged collective work |
| `experiment register|ingest` | preregistration and result artifacts |
| `storage migrate --apply` | additive local database migration |
| `provider import` | candidate evidence, residuals, and task hints |
| `operation approve` | parameter-bound approval artifact |

`ccr operation dispatch --execute` is the external-effect boundary. Network
providers require HTTPS, an exact host allowlist, public-address DNS checks,
redirect denial, byte/time limits, a current preflight, and an unexpired bound
approval. Physical or irreversible operations require distinct approvers,
rollback and hazard controls, and independent verification.

Generic `ccr provider execute` cannot bypass this operation gate. Imported
`safe_commands` are task hints and are never run automatically.

## Storage Profiles

SQLite is the default profile for one machine. Connections close after each
operation, state changes use immediate transactions, and task leases use
monotonic fencing tokens.

PostgreSQL 16+ is the distributed authoritative store. Workers claim tasks
with `FOR UPDATE SKIP LOCKED`, use database time, heartbeat leases, and commit
idempotently. Delivery is at least once; CCR does not claim exactly-once
execution. JSON files are content-addressed exports in this profile.

```bash
ccr --root ccr-runtime storage doctor --json
ccr --root ccr-runtime storage migrate --json
ccr --root ccr-runtime storage reconcile --json
```

## Documentation

- [Documentation Index](docs/README.md): task-oriented navigation
- [Getting Started](docs/getting-started.md): shortest local workflow
- [Command Map](docs/command-map.md): commands, writes, and authority needs
- [Collective Workcells](docs/collective-workcells.md): independent proposals and residual-preserving integration
- [Distributed Runtime](docs/distributed-runtime.md): PostgreSQL, OIDC + DPoP API, and workers
- [Measurement Protocol](docs/measurement-protocol.md): resource-matched experiments
- [Operation Gate](docs/operation-gate.md): approval, dispatch, and observation boundaries
- [Security Audit Checklist](docs/security-audit-checklist.md): NIST AI RMF and OWASP agent controls
- [PIC Interoperability](INTEROP_PIC.md): PIC 1.0 compatibility and non-settlement boundary
- [Security Policy](SECURITY.md): threat model and disclosure process

Search terms: collective intelligence runtime, multi-agent coordination,
distributed AI agents, PostgreSQL task queue, capability packet, residual
ledger, independent verification, ASI-proxy measurement, PIC interoperability,
OIDC DPoP agent API, operation approval, and provenance.

## Public Release Audit

Run the complete local gate before creating a tag or GitHub release:

```bash
uv sync --all-extras
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run python -m compileall -q src tests
uv run pytest
uv run python scripts/check_schema_registry.py
uv run ccr audit repo --json
uv run ccr audit pic --pic-root <PIC_ROOT> --json
uv build
uv run ccr audit release --dist dist --json
uvx twine check dist/*
```

`<PIC_ROOT>` is a trusted local checkout of
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler).
These audit commands do not push, tag, publish, dispatch providers, or prove a
physical outcome.

## Compatibility

The v1 CLI and JSON interfaces remain compatible. New fields are additive.
The safety exception is deliberate: side-effecting provider execution must use
the TRC operation approval and dispatch path. The Python API remains
semi-stable; CLI commands and registered JSON schemas are the public contract.
