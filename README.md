# Collective Capability Runtime

Collective Capability Runtime (CCR) is an agent-native open-source runtime
for converting distributed AI-agent work into a reusable, verifiable,
residual-preserving capability commons.

CCR does not replace Percolation Inversion Compiler (PIC)([kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)). It orchestrates
multi-agent proposal, task leasing, blackboard memory, packet distillation,
role-separated verification, residual preservation, and benchmark comparison,
while delegating packet-level and phase-proxy checks to PIC-compatible
verifier providers when available.

The operational target is not an unrestricted or metaphysical ASI claim, but
a protocol-relative ASI-proxy collective phase: a reproducible state in which
locally admissible, verified, reusable, and execution-available capability
packets form a collective system that improves downstream problem-solving
relative to a resource-matched baseline while preserving hazards, residuals,
authority bounds, and non-execution-by-default constraints.

v1.5.0 completes the Mission Runtime P2 surface. Agents can inspect MCP/A2A
gates with descriptor/card hashes and authority envelopes, ingest local traces
or repositories into mission-scoped candidate packets, rank residual work,
export a static HTML workbench, build operation replay manifests, compare
CCR/PIC evidence reports, and validate static provider registries. These
surfaces are local-first: no provider dispatch, network call, shell command,
physical actuation, or settlement is implied.

v1.4.0 adds the local advisory ASI-proxy loop layer on top of the v1.3.0
PIC/PIC-TS v0.8.0 interop helpers. Agents can run `ccr loop init`, `ccr loop
next`, token distill/import/dedup/next commands, foundry smoothing/frontier/VOI
diagnostics, graph quotient checks, cache/index rebuilds, and performance
reports without provider execution or network calls. The v1.4 loop is designed
to reduce time-to-first-use and duplicate residual work while preserving the
boundary between candidate token, accepted report, admitted capital, dispatch,
execution, and observed physical outcome.

v1.3.0 adds PIC/PIC-TS v0.8.0 interop helpers for target-valid ASI-proxy/CARA
acceleration, runtime capital witnesses, MCP/A2A structured reports, SQOT/BIT
diagnostics, provider circuit breakers, availability reports, and stricter TRC
operation preflight. CCR can consume a PIC trace-check or operation-gate report, build a
`ccr.trc_operation_plan.v1` dry-run plan, run
`ccr.trc_operation_preflight.v1`, and dispatch only when an operator supplies
provider configuration plus explicit `--execute`. Expired, fixture-only,
time-unknown, untrusted, or out-of-scope authority envelopes fail closed. The
plan remains residual-preserving evidence, not settlement or real-world
execution proof.

## Non-Claims

CCR does not:

- detect real ASI
- create real ASI
- self-modify models
- update model weights
- grant execution authority
- bypass safety
- treat PIC `accepted=true` as CCR `settled`
- treat execution-available paths as executed paths
- treat `operation_ready`, `provider_dispatch_ready`, or
  `physical_dispatch_ready` as outcome proof
- execute provider safe commands automatically

Residuals are expected runtime state. `settled=false` is not a command crash.
CCR certificate candidates are not real ASI proof.

## Install

```bash
python -m pip install collective-capability-runtime
uv sync --all-extras
uv run ccr agent explain --json
```

## ASI-Proxy Mission Quickstart

The fastest local path is the Mission Runtime Layer. It creates a local
ASI-proxy mission, target fixture, baseline upper envelope, advisory loop state,
candidate packet workspace, and workbench report without provider execution,
network calls, shell authority, settlement, or physical outcome claims.

```bash
python -m pip install collective-capability-runtime
ccr asi quickstart --profile development --json
ccr mission next --mission mission:quickstart --compact --json
ccr workbench report --mission mission:quickstart --format markdown --out CCR_WORKBENCH.md
```

The quickstart intentionally reports `settled=false` and
`external_execution=false`. Treat the workbench as an operational facade over
CCR JSON artifacts, not as real ASI proof, execution authority, provider
settlement, PIC settlement, or physical outcome proof.

Mission reports are mission-scoped: packets and residuals from another mission
do not contribute to acceptance or blocker counts. CI can make advisory reports
fail closed when desired:

```bash
ccr mission report --mission mission:quickstart --format json --out report.json --fail-on blocking_residual
ccr workbench report --mission mission:quickstart --format json --out report.json --fail-on missing_mission
```

Local gate facades are available for first-pass MCP/A2A/provider review. They
read local JSON only, perform no dispatch, make no network calls, and return
residual-ready blockers for authority, egress, replay, or settlement gaps:

```bash
ccr mcp inspect-descriptor --file examples/asi_proxy_acceleration_bundle/mcp_descriptor.good.json --json
ccr mcp preflight --descriptor examples/asi_proxy_acceleration_bundle/mcp_descriptor.good.json --invocation examples/asi_proxy_acceleration_bundle/mcp_invocation.good.json --json
ccr a2a inspect-card --file examples/asi_proxy_acceleration_bundle/a2a_agent_card.good.json --json
ccr a2a preflight-handoff --handoff examples/asi_proxy_acceleration_bundle/a2a_handoff.good.json --card examples/asi_proxy_acceleration_bundle/a2a_agent_card.good.json --json
ccr provider conformance --file examples/asi_proxy_acceleration_bundle/provider_manifest.good.json --json
ccr ingest trace --input README.md --json
ccr ingest trace --input README.md --mission mission:quickstart --write-candidates --json
ccr residual market --mission mission:quickstart --json
ccr workbench export --mission mission:quickstart --format static-html --out site/ --json
ccr operation replay-manifest --dispatch-report dispatch.json --observation observation.json --out replay.json --json
ccr operation verify-observation --manifest replay.json --verifier verifier.json --json
ccr conformance bundle --bundle examples/asi_proxy_mission_bundle --json
ccr provider registry-validate --file provider-registry.json --json
```

PIC is optional but recommended for packet-level and phase-proxy verification:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler).
PIC output never settles CCR by itself.

```bash
python -m pip install percolation-inversion-compiler
```

For development checks:

```bash
uv run ruff check .
uv run pytest
uv run ccr audit repo --json
uv run ccr audit pic --pic-root <PIC_ROOT> --json
uv run ccr provider health --provider pic --json
uv run ccr operation preflight --trace pic-trc-gate.json --provider http --config provider.json --json
uv run ccr operation plan --trace pic-trc-gate.json --json
uv run ccr operation dispatch --plan trc-operation-plan.json --provider http --config provider.json --execute --json
uv run ccr operation observe --dispatch-report dispatch.json --observation observation.json --json
```

`<PIC_ROOT>` means a local checkout of
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler),
for example `../percolation-inversion-compiler`. Public documentation should
use the placeholder rather than a user-specific local path.

## PyPI Distribution

CCR is prepared for PyPI distribution as `collective-capability-runtime`:

```bash
python -m pip install collective-capability-runtime
```

Publishing is configured for GitHub Trusted Publishing from
`kadubon/collective-capability-runtime` using `.github/workflows/workflow.yml`.
The publish workflow builds and checks distributions, then publishes with
`pypa/gh-action-pypi-publish@release/v1` and `id-token: write`. It does not use
PyPI username/password/API-token secrets.

## Public Release Audit

Before publishing, run the repository audit, optional PIC compatibility audit,
build the distributions, inspect the built archives for local-path, generated
artifact, and secret-like leakage, then run Twine validation:

```bash
uv run ccr audit repo --json
uv run ccr audit pic --pic-root <PIC_ROOT> --json
uv build
uv run ccr audit release --dist dist --json
uvx twine check dist/*
```

The release audit scans source files plus wheel/sdist contents. It treats local
home paths, generated CCR runtime state, cache/build artifacts, private-key
blocks, and assignment-like credentials as blocking findings.

## Quickstart

```bash
uv run ccr init
uv run ccr schema validate --kind packet --file examples/minimal/packet.json
uv run ccr schema validate --kind task --file examples/minimal/task.json
uv run ccr task submit --file examples/minimal/task.json
uv run ccr packet submit --file examples/minimal/packet.json --json
uv run ccr task next --role generator --json
uv run ccr phase report --json
```

CCR stores auditable JSON artifacts and maintains `ccr.sqlite` as an index for
objects, events, leases, provider runs, and phase observations. JSON remains the
source artifact.

## First-time agent guide

Purpose: use CCR to coordinate capability packets, tasks, residuals, provider
reports, and protocol-relative ASI-proxy phase diagnostics without executing
external commands by default.

First commands:

```bash
ccr asi quickstart --profile development --json
ccr mission next --mission mission:quickstart --compact --json
ccr agent explain --json
ccr audit repo --json
ccr provider health --provider pic --json
ccr phase report --json
```

Safe boundary: planning, audit, health, report, graph, observe, threshold, and
provider plan commands are safe inspection commands. Commands that submit,
lease, import, integrate, execute, or form phase write local CCR artifacts;
external provider execution still requires explicit authority.

Expected outputs: commands return deterministic JSON with `ok`, object ids,
paths, status fields, and residual-ready payloads when something blocks.

Failure/residual handling: validation failures, provider gaps, baseline
mismatches, candidate-only reasons, and settlement blockers must be preserved as
residuals or `residual_ready` objects, not discarded.

P2 safe commands:

```bash
ccr residual market --json
ccr residual market --mission mission:quickstart --json
ccr residual bounty --residual <residual_id> --mission mission:quickstart --emit task --json
ccr workbench export --mission mission:quickstart --format static-html --out site/ --json
ccr operation replay-manifest --dispatch-report dispatch.json --observation observation.json --out replay.json --json
ccr operation verify-observation --manifest replay.json --verifier verifier.json --json
ccr conformance parity --ccr-report ccr.json --pic-report pic.json --json
ccr provider registry-validate --file provider-registry.json --json
```

These commands are local report or local task-routing surfaces. They do not
release packages, push tags, upload to PyPI, dispatch providers, or prove
physical outcomes.

Provider import: imported reports can update packet status to checked or
provisional and create task hints, but imported `safe_commands` are never run.

Phase formation cycle: agents repeatedly submit/verify/import packets, run
`ccr phase form --profile development --json`, resolve generated tasks and
residuals, and compare against a resource-matched baseline.

What not to claim: do not claim real ASI, model-weight updates, self-rewrite,
execution authority, physical truth, oracle truth, or CCR settlement from PIC
or provider output alone.

## Phase Formation

CCR v1 adds local protocol-relative ASI-proxy phase formation commands:

```bash
uv run ccr --root examples/phase_formation phase graph --json
uv run ccr --root examples/phase_formation phase observe --json
uv run ccr --root examples/phase_formation phase threshold --file examples/phase_formation/threshold.json --json
uv run ccr --root examples/phase_formation phase form --profile development --json
uv run ccr --root examples/phase_formation phase certify --json
```

The effective graph counts only checked or settled packets without blocking
residual, authority, or negative-liquidity blockers as positive contribution.
Raw, candidate-only, rejected, quarantined, duplicate, and speculative volume is
diagnostic only. Execution availability is recorded as a path witness and never
as executed work.

`phase form` runs graph -> observation -> threshold -> certificate-candidate
locally and creates deterministic repair tasks for failed threshold components.
The certificate is a `CollectivePhaseCertificateCandidate`, not proof of real
ASI or physical outcomes.

## Baseline Comparison

Resource-matched comparison is explicit:

```bash
uv run ccr phase compare --baseline baseline.json --candidate observation.json --json
```

A resource-envelope mismatch is preserved as a blocking residual-ready object.
It is diagnostic state, not a crash.

## Provider API

Providers expose `capabilities`, `health`, `plan`, `execute`, and `normalize`.
Built-in providers are:

- `pic`: optional local PIC verifier/phase provider
- `http`: explicit HTTP report/webhook provider

Provider planning is dry-run:

```bash
uv run ccr provider list --json
uv run ccr provider health --provider pic --json
uv run ccr provider plan --provider http --action webhook --file payload.json --json
```

HTTP execution requires both an explicit config file and explicit `--execute`.
The config must contain `allow_execute=true`; methods are allowlisted, timeouts
and byte limits are enforced, sensitive headers are redacted from outbound
configuration, and failure returns residual-ready JSON.

```bash
uv run ccr provider execute --provider http --action webhook --config http-config.json --file payload.json --execute --json
```

Provider reports can be imported without executing safe commands:

```bash
uv run ccr --root examples/phase_formation provider import --provider http --report examples/phase_formation/mock_http_report.json --json
uv run ccr integrate --report examples/pic_interop/pic_import_example.json --json
```

`candidate_only_reasons` become residuals, `settled_blockers` become blocking
residuals, and `safe_commands` become non-executed task hints.

## Minimal Agent Loop

```bash
ccr agent explain --json
ccr task next --role generator --json
ccr task lease task.minimal.generator --ttl 30m --agent agent.example --json
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
provider_output != proof_of_real_ASI
```

External content remains candidate-only until verifier reports and CCR promotion
policy accept it. Blocking residuals prevent settlement.
