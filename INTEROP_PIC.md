# CCR-PIC Interoperability Specification v1

PIC repository and optional install path:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

This document defines how Collective Capability Runtime (CCR) interoperates with
Percolation Inversion Compiler (PIC) without replacing or duplicating PIC.

## Boundary

CCR MUST NOT reimplement PIC's ECPT/BIT/TRC/SQOT/ALT certificate logic.

CCR owns:

- task leasing and role separation
- blackboard events
- packet distillation and local packet status
- residual ledger preservation
- SQLite indexing of JSON artifacts
- provider plan/execute/import orchestration
- effective packet graph construction from local CCR packets
- baseline comparison and phase certificate candidate assembly

PIC owns or provides:

- packet-level route and verifier checks
- ECPT phase diagnostics
- BIT, TRC, SQOT, and ALT certificate logic
- phase acceleration plans
- PIC-native collective phase certificate candidates

PIC is optional. Missing PIC is a provider-missing residual condition, not an
internal crash.

## First-time agent guide

Purpose: use this document to connect CCR orchestration to optional PIC checks
without treating PIC as a CCR settlement oracle.

First commands:

```bash
ccr provider health --provider pic --json
ccr audit pic --pic-root <PIC_ROOT> --json
ccr provider plan --provider pic --action verify_packet --packet <packet_id> --json
```

Safe boundary: PIC plans and imported reports are evidence routes; PIC
`safe_commands` remain task hints and PIC `settled=true` remains provider
evidence until CCR gates pass.

Expected outputs: normalized imports preserve accepted/workflow usable flags,
settled flags, candidate-only reasons, blockers, phase gaps, bottlenecks, and
safe command hints.

Failure/residual handling: missing PIC package or CLI is a provider-missing
residual-ready state, not an internal CCR failure.

P2 safe commands:

```bash
ccr residual market --json
ccr residual market --mission <mission_id> --json
ccr residual bounty --residual <residual_id> --mission <mission_id> --emit task --json
ccr workbench export --mission <mission_id> --format static-html --out site/ --json
ccr operation replay-manifest --dispatch-report dispatch.json --observation observation.json --out replay.json --json
ccr operation verify-observation --manifest replay.json --verifier verifier.json --json
ccr conformance parity --ccr-report ccr.json --pic-report pic.json --json
ccr provider registry-validate --file provider-registry.json --json
```

PIC/PIC-TS reports are evidence-only in these routes. They do not settle CCR,
grant authority, dispatch providers, or prove physical outcomes.

Provider import: use `ccr provider import --provider pic --report <file> --json`
or legacy `ccr integrate --report <file> --json`; neither path executes
safe commands.

Phase formation cycle: PIC can help produce packet checks and phase plans; CCR
still builds its own graph, observation, threshold status, baseline comparison,
and certificate candidate.

What not to claim: PIC accepted, workflow usable, or settled output alone is
not CCR settlement and not proof of real ASI.

TRC operation reports: CCR accepts PIC `pic.trc_trace_report.v1` and
`pic.trc_operation_gate_report.v1` as non-executing inputs. It re-checks
authority freshness during plan construction so stale hand-written reports fail
closed. `operation_ready` is not execution, `provider_dispatch_ready` is not
dispatch, and `physical_dispatch_ready` is not physical outcome proof.

v1.3/v0.8 interop: CCR also consumes target-valid CARA inputs, runtime capital
witnesses, MCP/A2A report fixtures, SQOT protocol diagnostics, BIT MEC frontier
reports, and operation preflight reports. These imports remain candidate
evidence. `capital_admitted` is lower-bound evidence, not settlement; proxy-only
evidence cannot increase safe capital.

Mission Runtime Layer: `ccr asi quickstart` and `ccr mission ...` organize a
local target, baseline, authority envelope, packet workspace, residual ledger,
loop policy, provider policy, and workbench report. Mission may reference or
import PIC-compatible evidence, but PIC remains optional and is not a settlement
oracle. Mission reports preserve `settled=false` and `external_execution=false`
unless a separate explicit CCR command and existing CCR semantics say otherwise.

## Shared Non-Claims

CCR and PIC interop MUST preserve these constraints:

1. No real ASI detection claim.
2. No real ASI creation claim.
3. No model self-rewrite or model-weight update claim.
4. No hidden capability injection claim.
5. PIC safe commands are task hints, not authority.
6. External content is candidate-only until verifier and promotion policies accept it.
7. Raw or duplicate packet volume does not improve phase status.
8. Candidate-only closure, execution-path, or basin-path records do not improve phase status.
9. Residuals are expected and must be preserved.
10. `settled=false` is valid diagnostic state.

## Provider API Mapping

CCR exposes PIC through the v1 provider API:

```text
provider capabilities
provider health
provider plan --provider pic
provider execute --provider pic --execute
provider import --provider pic
```

`provider plan` returns non-executing argv and import guidance. `provider
execute` runs only when the operator passes explicit `--execute`; it uses
`shell=False`, bounded timeout, captured output, and a stored report. `provider
import` normalizes the report and materializes residuals or task hints.

The legacy convenience commands remain:

```bash
ccr provider health --provider pic --json
ccr audit pic --pic-root <PIC_ROOT> --json
ccr verify --provider pic --packet <packet_id> --profile development --json
ccr verify --provider pic --packet <packet_id> --profile development --execute --json
ccr integrate --report reports/pic/<report>.json --json
```

## PIC v0.5.0/v0.6.0 compatibility matrix

The strict contract is also supported through PIC 1.0.x. CCR negotiates the
major/minor version, validates JSON booleans without truthy coercion, records a
canonical report digest, compares residual kind sets, and keeps every
`safe_commands` item as a non-executed task hint.

| PIC surface | CCR v1.1 mapping | Compatibility rule |
|---|---|---|
| `pic agent check --compact` | `verify --provider pic` plan/execute and `provider import --provider pic` | Optional provider; missing CLI becomes provider-missing residual-ready JSON. |
| `pic trc operation-gate` | `ccr operation preflight` and `ccr operation plan` | Requires approved/active, fresh, scoped authority. Fixture dry-runs are diagnostic-only and non-executable. |
| `pic packet inspect` | dry-run command hint | Inspection is never executed automatically. |
| `pic phase plan --compact` | phase-plan report import and bottleneck diagnostics | `phase_gap_vector`, `bottlenecks`, and `safe_commands` stay diagnostic/task-hint inputs. |
| `pic runtime collective-certify` | external certificate-candidate evidence | PIC output never settles CCR by itself. |
| `pic trc trace-normalize` / `trace-check` / `trace-to-packet` | TRC operation plan input and packet candidate import | Trace checks expose blockers and readiness gates; they do not grant execution authority. |
| `accepted` / `workflow_usable` | verifier evidence attached to the existing packet status | Import never promotes; normal CCR promotion evaluates evidence. |
| `settled` | `settled_candidate` provider evidence | CCR settlement still requires CCR promotion, phase, baseline, and residual gates. |
| `candidate_only_reasons` | nonblocking residuals | Candidate-only mass never adds positive phase contribution. |
| `settled_blockers`, `missing_obligations`, `cannot_promote_because` | blocking residuals | Block CCR settlement until resolved. |
| `execution_blockers`, `real_world_operation_gate` | TRC operation residuals and dispatch preconditions | CCR still requires provider configuration and explicit execution opt-in. |
| `safe_commands` / `sdk_calls` | task hints or preserved metadata | Safe commands are not executed by import. |

## Status Mapping

| PIC output | CCR mapping | Rule |
|---|---|---|
| `accepted=false` | evidence plus residuals; packet status unchanged | Normal promotion or quarantine policy decides later. |
| `accepted=true, settled=false` | evidence plus candidate-only reasons; packet status unchanged | Normal accepted evidence path. |
| `accepted=true, settled=true` | evidence plus settlement blocker review; packet status unchanged | PIC settlement alone never grants CCR final settlement. |
| `candidate_only_reasons` | residuals | Preserve without promotion. |
| `settled_blockers` | blocking residuals | Prevent CCR settlement. |
| `safe_commands` | tasks/open hints | Never execute automatically. |
| phase bottlenecks | tasks/open repair/verifier/baseline/residual tasks | Deterministic scheduling input. |
| phase dashboard metrics | phase observation input | Diagnostic unless linked to positive packet capital. |

## CCR to PIC Input Mapping

CCR may pass packet summaries, packet JSON, task objectives, phase reports, and
baseline/threshold records to PIC-compatible tooling. Production or adversarial
profiles require explicit identity context references; CCR does not infer global
identity or Sybil resistance from a declared agent id.

Recommended dry-run planning commands:

```bash
ccr provider plan --provider pic --action verify_packet --packet <packet_id> --profile development --json
ccr phase plan --provider pic --profile development --json
```

Recommended PIC-side commands may include:

```bash
pic agent check --compact --text "<packet summary>" --profile development
pic phase plan --compact --profile development
pic phase lab certify --store <store> --threshold <threshold.json>
```

CCR treats these as recommendations until an operator explicitly executes them
or imports a verifier report.

## PIC to CCR Output Mapping

CCR normalized provider reports preserve:

- provider name
- accepted and settled flags
- packet id
- candidate-only reasons
- settled blockers
- safe commands
- original report path
- normalized report path
- residual ids
- task hint ids

Minimal normalized shape:

```json
{
  "schema_version": "ccr.provider_import.v1",
  "import_id": "pic-import:<digest>",
  "provider": "pic",
  "accepted": true,
  "settled": false,
  "ccr_status": "checked",
  "packet_id": "packet.example",
  "candidate_only_reasons": [],
  "settled_blockers": [],
  "safe_commands": []
}
```

## Phase Formation Boundary

CCR v1 can build:

- `effective-graph`
- `phase-observation`
- `asi-proxy-threshold` status
- `baseline` comparison
- `phase-certificate-candidate`

These are CCR orchestration artifacts. They may call or import PIC-compatible
provider output, but they do not replace PIC certificates and do not imply real
ASI.

## Execution-Available vs Executed

CCR MUST preserve:

```text
execution_available != executed
safe_command != authority
candidate_path != settled capability
accepted_by_pic != settled_by_ccr
```

Execution availability requires declared mode, gates, side-effect policy,
rollback or quarantine rule, and residual preservation. It does not mean CCR or
PIC executed a command.

## Minimal Interop Cycle

```bash
ccr task next --role generator --json
ccr task lease <task_id> --ttl 30m --agent <agent_id> --json
ccr packet submit --file packet.json --json
ccr verify --provider pic --packet <packet_id> --profile development --json
ccr integrate --report reports/pic/<report>.json --json
ccr phase form --profile development --json
ccr report --format markdown
```

All residuals, blockers, candidate-only reasons, and safe-command hints remain
visible after import.

## v1.4 Loop Interop

Use `examples/asi_proxy_loop_bundle/` with PIC/PIC-TS v0.9. CCR imports token,
task, residual, and capital-witness reports as candidate runtime work, then
computes loop-next, foundry, graph quotient, performance, cache, and interval
diagnostics. PIC/PIC-TS remain checker layers. CCR remains the local runtime
and never treats PIC acceptance as settlement or execution authority.

## Runtime Conformance Interop

Use `ccr conformance bundle` and `ccr conformance parity` to compare CCR bundle
reports with PIC/PIC-TS evidence reports. Missing parity fields become
`residual_ready`; PIC `settled=true` remains evidence-only and is not CCR
settlement. Provider registry validation reads static manifests only and does
not import PIC, PIC-TS, or provider plugin modules.
