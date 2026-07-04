# Collective Capability Runtime

Collective Capability Runtime (CCR) is a local, JSON-first command-line
runtime for coordinating AI-agent work. It helps agents turn scattered work into
auditable capability packets, tasks, residuals, verification reports, mission
reports, and static workbench pages.

In simpler terms: CCR is a shared evidence and task layer for agent teams. It
does not run an LLM for you. It records what agents propose, what was checked,
what is still blocked, and what the next safe local action should be.

CCR is built for protocol-relative ASI-proxy phase formation. That phrase means
a bounded, reproducible state where checked capability packets, preserved
residuals, explicit baselines, and authority limits show improved problem
solving relative to a resource-matched baseline. It is not a claim of real ASI.

CCR does not replace Percolation Inversion Compiler (PIC)
([kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)).
CCR coordinates runtime state and local evidence. PIC remains the optional
checker layer for packet-level and phase-proxy checks when available.

## What CCR Helps With

- AI agent coordination and task routing
- local capability packet storage
- residual ledger preservation
- mission-scoped workbench reports
- MCP descriptor and A2A handoff safety review
- provider manifest and provider registry validation
- operation replay and observation verification without dispatch
- CCR/PIC conformance checks
- static HTML review pages with no external assets
- public-release audits without publishing

## Non-Claims

CCR does not:

- detect real ASI
- create real ASI
- self-modify models
- update model weights
- grant execution authority
- bypass safety
- treat PIC or provider output as CCR settlement
- treat MCP/A2A descriptors or handoffs as delegated authority
- treat `execution_available`, `operation_ready`, or `provider_dispatch_ready`
  as executed work
- treat observation verification as physical outcome proof
- treat cache, SQLite, or static workbench output as proof
- release packages, push tags, or upload to PyPI from audit commands

Residuals are expected runtime state. `settled=false` is a normal diagnostic
result, not a command crash.

CCR certificate candidates are not real ASI proof.

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

Optional PIC route:

```bash
python -m pip install percolation-inversion-compiler
ccr provider health --provider pic --json
```

`<PIC_ROOT>` in docs means a local checkout of
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler),
for example `../percolation-inversion-compiler`. Public docs should use the
placeholder and not a user-specific local path.

## Fastest First Run

The safest first run creates a local ASI-proxy mission fixture and a markdown
workbench report. It performs no provider execution, network call, shell command,
physical actuation, release, tag, or package upload.

```bash
ccr asi quickstart --profile development --json
ccr mission next --mission mission:quickstart --compact --json
ccr workbench report --mission mission:quickstart --format markdown --out CCR_WORKBENCH.md
```

Read `CCR_WORKBENCH.md` next. If it shows blocking residuals, route them through
the residual market:

```bash
ccr residual market --mission mission:quickstart --json
```

To export a browser-readable local view:

```bash
ccr workbench export --mission mission:quickstart --format static-html --out site/ --json
```

The generated static site is presentation only. It is not proof, settlement,
authority, dispatch, or physical outcome evidence.

## P0, P1, and P2 Surface Map

P0 is the mission and local evidence core:

```bash
ccr asi quickstart --profile development --json
ccr mission status --mission mission:quickstart --json
ccr mission next --mission mission:quickstart --compact --json
ccr mission report --mission mission:quickstart --format json --out report.json --fail-on blocking_residual
ccr workbench report --mission mission:quickstart --format json --out report.json --fail-on missing_mission
ccr claim audit --input README.md --json
ccr bundle validate --bundle examples/asi_proxy_mission_bundle --profile development --json
```

P1 is the local gate and ingest layer:

```bash
ccr mcp inspect-descriptor --file examples/asi_proxy_acceleration_bundle/mcp_descriptor.good.json --json
ccr mcp preflight --descriptor examples/asi_proxy_acceleration_bundle/mcp_descriptor.good.json --invocation examples/asi_proxy_acceleration_bundle/mcp_invocation.good.json --json
ccr a2a inspect-card --file examples/asi_proxy_acceleration_bundle/a2a_agent_card.good.json --json
ccr a2a preflight-handoff --handoff examples/asi_proxy_acceleration_bundle/a2a_handoff.good.json --card examples/asi_proxy_acceleration_bundle/a2a_agent_card.good.json --json
ccr ingest trace --input README.md --mission mission:quickstart --write-candidates --json
ccr ingest repo --path . --mission mission:quickstart --json
ccr provider manifest --file examples/asi_proxy_acceleration_bundle/provider_manifest.good.json --json
ccr provider conformance --file examples/asi_proxy_acceleration_bundle/provider_manifest.good.json --json
```

P2 is the first-time-agent usability layer:

```bash
ccr residual market --mission mission:quickstart --json
ccr residual bounty --residual <residual_id> --mission mission:quickstart --emit task --json
ccr residual diff --before before.json --after after.json --json
ccr workbench export --mission mission:quickstart --format static-html --out site/ --json
ccr operation replay-manifest --dispatch-report examples/asi_proxy_acceleration_bundle/dispatch_report.example.json --observation examples/asi_proxy_acceleration_bundle/observation.example.json --out replay.json --json
ccr operation verify-observation --manifest replay.json --verifier examples/asi_proxy_acceleration_bundle/observation_verifier.good.json --json
ccr conformance bundle --bundle examples/asi_proxy_mission_bundle --json
ccr conformance parity --ccr-report ccr.json --pic-report pic.json --json
ccr provider registry-validate --file examples/asi_proxy_acceleration_bundle/provider_registry.good.json --json
ccr provider registry-list --file examples/asi_proxy_acceleration_bundle/provider_registry.good.json --json
```

These commands are local-first. They do not execute providers, import provider
code, call networks, dispatch MCP/A2A tools, waive residuals, or settle CCR.

## What Mutates Local State

Most inspection commands only read files and print JSON. Commands below can
write local CCR artifacts when their required flags are present:

| Command | Local write | External effect |
|---|---|---|
| `ccr asi quickstart` | mission, target, baseline, candidate packet, reports | none |
| `ccr mission init` | mission files | none |
| `ccr mission ingest` | mission-scoped candidate packet or residual | none |
| `ccr ingest trace --write-candidates` | candidate packets and residuals | none |
| `ccr ingest repo --write-candidates` | candidate packets and residuals | none |
| `ccr residual bounty --emit task` | one local repair task | none |
| `ccr workbench report --out ...` | one report file | none |
| `ccr workbench export --out ...` | static HTML and JSON files | none |
| `ccr operation replay-manifest --out ...` | one replay manifest | none |
| `ccr task lease` | local lease metadata | none |
| `ccr packet submit` | local packet file | none |
| `ccr provider import` | local reports, residuals, task hints | none |
| `ccr provider execute --execute` | provider report plus possible provider side effect | explicit operator authority required |

SQLite (`ccr.sqlite`) is a repairable index. JSON artifacts remain the source of
truth.

## Expected Outputs

CCR commands return deterministic JSON where possible. Important fields are:

- `ok`: command-level success or failure
- `accepted`: local gate acceptance, not settlement
- `settled`: final CCR settlement status, often `false`
- `external_execution`: whether this command performed external execution
- `network_call_performed`: whether this command made a network call
- `executed`: whether the source evidence says execution happened
- `physical_outcome_proven`: physical outcome proof status, normally `false`
- `residual_ready` or `residuals`: preserved blockers or follow-up work
- `non_claims`: boundaries the output does not assert

Failure is protocol data. Malformed input, unknown authority, stale evidence,
schema mismatch, hash mismatch, missing mission, unsupported claim, and path
traversal should become explicit JSON failures or residuals.

## Documentation Map

- [docs/README.md](docs/README.md): documentation index for agents and humans
- [docs/getting-started.md](docs/getting-started.md): first-use sequence
- [docs/command-map.md](docs/command-map.md): P0/P1/P2 command map and local writes
- [docs/asi-proxy-mission.md](docs/asi-proxy-mission.md): mission runtime facade
- [docs/p2-runtime-surfaces.md](docs/p2-runtime-surfaces.md): residual market, static workbench, replay, conformance, registry
- [docs/mcp-a2a-safety.md](docs/mcp-a2a-safety.md): MCP/A2A safety boundary
- [docs/operation-gate.md](docs/operation-gate.md): operation gate and replay boundary
- [docs/real-world-impact.md](docs/real-world-impact.md): operation evidence and non-claim boundary
- [docs/cross-repo-loop-conformance.md](docs/cross-repo-loop-conformance.md): CCR/PIC/PIC-TS parity
- [docs/github-action.md](docs/github-action.md): checked-out-source CI audit action
- [AUDIT.md](AUDIT.md): repository and release audit commands
- [SECURITY.md](SECURITY.md): threat model and provider execution boundary
- [INTEROP_PIC.md](INTEROP_PIC.md): CCR/PIC compatibility

Search terms: AI agent runtime, agent coordination, local-first runtime, JSON
schema, residual ledger, capability packet, ASI-proxy mission, phase formation,
MCP preflight, A2A handoff, provider registry, operation replay, static
workbench, PIC interop, release audit.

## Public Release Audit

Before publishing, audit the repository and built distributions without
releasing:

```bash
uv sync --all-extras
uv run ruff check .
uv run pytest
uv run ccr audit repo --json
uv run ccr audit pic --pic-root <PIC_ROOT> --json
uv build
uv run ccr audit release --dist dist --json
uvx twine check dist/*
```

These commands do not create a GitHub release, push a tag, upload to PyPI, or
dispatch providers.

## Provider API

Providers expose `capabilities`, `health`, `plan`, `execute`, and `normalize`.
Built-in providers are:

- `pic`: optional local PIC verifier/phase provider
- `http`: explicit HTTP report/webhook provider

Provider planning is dry-run:

```bash
ccr provider list --json
ccr provider health --provider pic --json
ccr provider plan --provider http --action webhook --file payload.json --json
```

HTTP execution requires an explicit config file, `allow_execute=true`, and an
explicit `--execute` flag. Imported provider `safe_commands` become task hints
only and are never run automatically.

## First-time agent guide

Purpose: use CCR to coordinate capability packets, tasks, residuals, provider
reports, and protocol-relative ASI-proxy phase diagnostics without executing
external commands by default.

First commands:

```bash
ccr agent explain --json
ccr asi quickstart --profile development --json
ccr mission next --mission mission:quickstart --compact --json
ccr workbench report --mission mission:quickstart --format markdown --out CCR_WORKBENCH.md
ccr residual market --mission mission:quickstart --json
```

Safe boundary: audit, report, schema validation, mission next, claim audit,
MCP/A2A inspect and preflight, provider manifest review, provider conformance,
external ingest without `--write-candidates`, residual market, static workbench
export, operation replay, conformance, and provider registry validation are
safe starting surfaces. They do not grant authority or execute providers.

Expected outputs: read `ok`, `accepted`, `settled`, `external_execution`,
`network_call_performed`, `residual_ready`, `residuals`, `blockers`,
`non_claims`, and local output paths before choosing the next command.

Failure/residual handling: preserve validation failures, provider gaps, missing
evidence, authority gaps, baseline mismatches, stale sources, and settlement
blockers as residuals. Use the residual market to rank work; it does not waive
residuals.

P2 safe commands:

```bash
ccr residual market --json
ccr residual market --mission mission:quickstart --json
ccr residual bounty --residual <residual_id> --mission mission:quickstart --emit task --json
ccr residual diff --before before.json --after after.json --json
ccr workbench export --mission mission:quickstart --format static-html --out site/ --json
ccr operation replay-manifest --dispatch-report dispatch.json --observation observation.json --out replay.json --json
ccr operation verify-observation --manifest replay.json --verifier verifier.json --json
ccr conformance bundle --bundle examples/asi_proxy_mission_bundle --json
ccr conformance parity --ccr-report ccr.json --pic-report pic.json --json
ccr provider registry-validate --file provider-registry.json --json
ccr provider registry-list --file provider-registry.json --json
```

Provider import: imported reports can update packet status to checked or
provisional and create task hints, but imported `safe_commands` are never run.

Phase formation cycle: agents create or repair packets, preserve residuals,
import verifier evidence, run `ccr phase form --profile development --json`,
inspect threshold and baseline blockers, then route the next residual through
tasks or residual market.

What not to claim: do not claim real ASI, model-weight updates, self-rewrite,
execution authority, physical truth, oracle truth, or CCR settlement from PIC
or provider output alone.

## Phase Formation

CCR can build local phase diagnostics:

```bash
ccr phase graph --json
ccr phase observe --json
ccr phase threshold --file examples/phase_formation/threshold.json --json
ccr phase compare --baseline baseline.json --candidate observation.json --json
ccr phase form --profile development --json
ccr phase certify --json
```

The effective graph counts checked or settled packets without blocking
residual, authority, or negative-liquidity blockers as positive contribution.
Raw, candidate-only, rejected, quarantined, duplicate, and speculative volume is
diagnostic only. Execution availability is recorded as a path witness and never
as executed work.

## Minimal Agent Loop

```bash
ccr agent explain --json
ccr task next --role generator --json
ccr task lease <task_id> --ttl 30m --agent agent.example --json
ccr packet submit --file examples/minimal/packet.json --json
ccr verify --provider pic --packet packet.minimal --profile development --json
ccr integrate --report reports/pic/<report>.json --json
ccr phase form --profile development --json
```

CCR does not include an LLM executor. Agents use the CLI to lease work, submit
packets, route verification, preserve residuals, and form phase diagnostics.

## Schema Validation

Local `schemas/` files are authoritative. Packaged schemas are used only if
local schemas are absent.

```bash
ccr schema validate --kind packet --file packet.json
ccr schema validate --kind task --file task.json
ccr schema validate --kind phase-observation --file observation.json
ccr schema validate --kind baseline --file baseline.json
```

Stable v1 public interfaces are CLI commands and JSON schemas. The Python API is
semi-stable.

## Safety Boundary

CCR distinguishes:

```text
execution_available != executed
safe_command != authority
candidate_path != settled capability
accepted_by_pic != settled_by_ccr
operation_replay != dispatch
observation_verification != physical_outcome_proof
static_workbench != proof
provider_registry != authority
cache_index_hit != proof
```

External content remains candidate-only until verifier reports and CCR promotion
policy accept it. Blocking residuals prevent settlement.
