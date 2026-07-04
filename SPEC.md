# CCR Specification v1

Related PIC runtime: [kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler).

```bash
python -m pip install percolation-inversion-compiler
```

PIC is optional. CCR does not replace PIC, and PIC output never settles CCR by
itself.

```bash
ccr audit pic --pic-root <PIC_ROOT> --json
ccr provider health --provider pic --json
```

## Operational Objects

CCR persists these source artifacts as JSON:

- packet: scoped, reusable capability packet with claims, artifacts, provenance, verifier plan, risk, reuse, lineage, execution-availability, and provider interop fields
- task: role-scoped unit of work with constraints, lease metadata, expected outputs, verifier plan, residual policy, and PIC interop hints
- residual: preserved uncertainty, blocker, candidate-only reason, authority gap, validation failure, provider failure, or baseline mismatch
- blackboard event: append-only mutation record
- verifier or provider report: optional external output normalized into CCR semantics
- effective graph: phase graph over checked/provisional/settled packets and semantic edges
- phase observation: deterministic metrics over the effective graph, residual ledger, and execution-available path witnesses
- threshold status: ASI-proxy threshold evaluation over one observation
- baseline comparison: resource-matched comparison against a declared baseline
- certificate candidate: protocol-relative collective phase candidate, never real ASI proof
- mission: an operational facade over a target, baseline upper envelope,
  authority envelope, hazard envelope, resource envelope, packet workspace,
  residual ledger, loop policy, provider policy, and report policy
- workbench report: human-readable and JSON mission summary for CI and
  first-time agents

SQLite (`ccr.sqlite`) is an index and transaction support layer. JSON artifacts
remain the auditable source of truth.

## First-time agent guide

Purpose: read this specification as the stable v1 contract for CLI behavior,
JSON artifacts, phase diagnostics, provider imports, residual preservation, and
non-claim boundaries.

First commands:

```bash
ccr agent explain --json
ccr audit repo --json
ccr schema validate --kind packet --file packet.json
ccr provider health --provider pic --json
```

Safe boundary: schema validation, audit, health, report, graph, observe,
threshold, compare, and provider plan do not grant external execution authority.

Expected outputs: every public command should return deterministic JSON,
schema-bound artifacts where applicable, explicit status values, and residual
or `residual_ready` records for blockers.

Failure/residual handling: validation, provider, baseline, authority, and
settlement failures are protocol data and must remain observable.

Provider import: normalized provider reports are evidence inputs; they may
create residuals and task hints, but imported commands are not executed.

Phase formation cycle: packets accumulate, verifier reports check or
provisionalize them, effective graphs and observations measure phase state, and
threshold/baseline gates decide whether a candidate is usable.

What not to claim: the specification does not define real ASI detection,
physical truth proof, model-weight updates, model self-rewrite, or automatic
settlement from PIC/provider output.

## Runtime State

`ccr init` creates:

```text
blackboard/events.jsonl
tasks/open tasks/leased tasks/done tasks/blocked
tasks/submitted tasks/verified tasks/integrated tasks/quarantined tasks/rejected tasks/expired
packets/raw packets/proposed packets/candidate packets/checked packets/settled
packets/provisional packets/speculative packets/rejected packets/quarantined packets/deprecated packets/expired
residuals/open residuals/resolved residuals/quarantined
reports/pic reports/verifier reports/phase reports/audit reports/providers
phase/graphs phase/observations phase/thresholds phase/certificates phase/comparisons
baselines
missions missions/state missions/targets missions/baselines reports/workbench reports/claims
ccr.config.json
ccr.sqlite
```

The SQLite schema includes `schema_migrations`, `objects`, `events`, `leases`,
`provider_runs`, and `phase_observations`.

## Status Lattice

Packet states:

```text
raw -> proposed -> candidate -> checked -> settled
                          \-> provisional
                          \-> speculative
                          \-> rejected
                          \-> quarantined
                          \-> deprecated
                          \-> expired
```

Task states:

```text
open -> leased -> submitted -> verified -> integrated
             \-> blocked
             \-> quarantined
             \-> rejected
             \-> expired
```

`settled=false` is valid diagnostic state. A provider, PIC report, or threshold
status cannot settle a packet or phase by itself.

## Phase Formation Semantics

CCR builds an effective packet graph from local packets:

- checked and settled packets may contribute positively
- provisional packets may enter diagnostics but do not settle coordinates
- raw, candidate, speculative, rejected, quarantined, deprecated, expired, and duplicate mass is diagnostic only
- semantic edges contribute only when endpoints and edge evidence are accepted
- execution-available path density counts path witnesses, not executions

Phase observations include accepted packet count, effective edge count,
execution-available path density, autocatalytic closure proxy, verification
throughput, residual debt, false liquidity load, salience obstruction, and
baseline delta when compared.

Threshold failure is not a crash. It is preserved as failed components and repair
tasks.

## Baseline Semantics

A baseline declares:

- resource envelope
- comparison class
- observable metrics
- validity domain

Resource-envelope mismatch yields a blocking residual-ready object. Improvement
relative to baseline is insufficient for accepted certificate status when
blocking residuals remain.

## Provider Semantics

Providers implement:

```text
capabilities()
health()
plan(action, payload, root)
execute(action, payload, root, config)
normalize(report)
```

Built-in providers:

- `pic`: optional PIC-compatible verifier and phase provider
- `http`: explicit HTTP provider

Planning must not perform network calls or command execution. HTTP execution
requires explicit config and explicit `--execute`. Provider safe commands are
converted to task hints only.

## Command Semantics

`ccr audit repo --json` checks README/docs/schema/CLI/tests/non-claims/provider
safety/SPDX/CI drift and returns residual-ready findings.

`ccr audit pic --json` checks the optional PIC source root, installed package,
CLI availability, expected commands, report-field mapping, non-claim boundary,
safe-command handling, and settlement boundary.

`ccr asi quickstart --profile development --json` initializes a local
non-executing mission fixture, target, baseline upper envelope, advisory loop
state, candidate packet, and workbench report. It reports `settled=false` and
`external_execution=false`.

`ccr mission init/status/ingest/next/report` exposes Mission as an operational
facade. Mission does not replace phase semantics and does not grant provider,
network, shell, repository, physical, or model-update authority.

`ccr claim extract/audit/passport` deterministically extracts prose claims,
skips fenced code blocks, and converts ASI-proxy overclaims into residual-ready
objects.

`ccr bundle validate --bundle <dir> --profile development --json` validates
mission bundles for target/baseline/non-claim presence and fail-closed
execution, settlement, capital-admission, and cache/index proof boundaries.

`ccr phase graph --json` writes an effective graph artifact.

`ccr phase observe --json` writes a phase observation artifact.

`ccr phase threshold --file threshold.json --json` evaluates the current or
provided observation against a threshold.

`ccr phase compare --baseline baseline.json --candidate observation.json --json`
compares a candidate observation to a resource-matched baseline.

`ccr phase form --profile development --json` runs graph, observation,
threshold, certificate-candidate generation, and deterministic repair task
creation.

`ccr phase certify --json` creates a
`CollectivePhaseCertificateCandidate`. It does not prove real ASI.

`ccr provider list/health/plan/execute/import` exposes explicit provider control.

Existing task, packet, residual, verify, integrate, phase report, and report
commands keep the v0 behavior and exit-code contract.

## Exit Codes

- `0`: success
- `1`: validation, policy, threshold, or provider action failure
- `2`: missing file, missing provider, or missing config
- `3`: unexpected internal error
