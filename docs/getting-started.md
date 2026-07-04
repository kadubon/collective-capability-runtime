# Getting Started with CCR

This guide gives a first-time agent the shortest safe path through Collective
Capability Runtime (CCR). It uses only local files and non-executing defaults.

CCR coordinates AI-agent work as JSON artifacts: tasks, capability packets,
residuals, mission reports, provider evidence, and phase diagnostics. The goal
is protocol-relative ASI-proxy phase formation, meaning a bounded and testable
improvement over a resource-matched baseline. CCR does not claim real ASI,
model self-rewrite, execution authority, or physical outcome proof.

Related optional PIC project:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

## First-time agent guide

Purpose: create one local mission, inspect the next safe action, read the
workbench, and route residuals without dispatching providers or changing the
outside world.

First commands:

```bash
python -m pip install collective-capability-runtime
ccr agent explain --json
ccr asi quickstart --profile development --json
ccr mission next --mission mission:quickstart --compact --json
ccr workbench report --mission mission:quickstart --format markdown --out CCR_WORKBENCH.md
ccr residual market --mission mission:quickstart --json
```

Safe boundary: the commands above are local-first. They do not perform provider
dispatch, network calls, MCP/A2A tool dispatch, shell execution, physical
actuation, release publication, tag creation, PyPI upload, or model updates.

Expected outputs:

- `ccr agent explain --json` returns the role contract, non-claims, docs, and
  safe first commands.
- `ccr asi quickstart --json` creates local mission fixtures and reports
  `external_execution=false`.
- `ccr mission next --compact --json` returns the next safe local action.
- `ccr workbench report` writes a mission-scoped report.
- `ccr residual market --json` ranks blockers and repair work.

Failure/residual handling: if a command returns `ok=false`, inspect
`residual_ready`, `residuals`, `blockers`, and `non_claims`. Do not suppress the
blocker. Preserve it, repair the referenced input, or create a local task with
`ccr residual bounty --emit task`.

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
```

Provider import: use provider imports only as evidence normalization. Imported
safe commands become local review tasks, not executed actions.

Phase formation cycle: create or repair packets, preserve residuals, import
verifier evidence, run `ccr phase form --profile development --json`, compare
against a baseline, and route the next blocker through tasks or residual market.

What not to claim: a passing quickstart or workbench report is not real ASI
proof, not execution authority, not provider settlement, not PIC settlement, and
not physical outcome proof.

## Next Documents

- [Command Map](command-map.md) for command categories and local writes.
- [ASI-Proxy Mission Runtime](asi-proxy-mission.md) for mission details.
- [P2 Runtime Surfaces](p2-runtime-surfaces.md) for residual market, static
  workbench, operation replay, conformance, and provider registry commands.
- [Operation Gate](operation-gate.md) for dispatch and observation boundaries.
