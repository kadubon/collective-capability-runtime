# CCR Documentation Index

This directory is the navigation layer for Collective Capability Runtime (CCR).
Use it when an agent or human needs to understand what to run first, which
commands are non-executing, and where each P0/P1/P2 surface is documented.

CCR is a local, JSON-first runtime for AI agent coordination. It stores
capability packets, tasks, residuals, mission reports, provider evidence, and
phase diagnostics. It supports protocol-relative ASI-proxy phase formation
without claiming real ASI, execution authority, or physical outcome proof.

Optional PIC checker route:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

## Start Here

1. [Getting Started](getting-started.md)
2. [Command Map](command-map.md)
3. [ASI-Proxy Mission Runtime](asi-proxy-mission.md)
4. [P2 Runtime Surfaces](p2-runtime-surfaces.md)

## Common Questions

| Question | Read |
|---|---|
| What is CCR? | [README](../README.md), [Getting Started](getting-started.md) |
| What should I run first? | [Getting Started](getting-started.md) |
| Which commands are safe and non-executing? | [Command Map](command-map.md), [P2 Runtime Surfaces](p2-runtime-surfaces.md) |
| What mutates local CCR state? | [Command Map](command-map.md) |
| How do I inspect MCP/A2A/provider surfaces? | [MCP/A2A Safety](mcp-a2a-safety.md), [Command Map](command-map.md) |
| How do I rank residual work? | [P2 Runtime Surfaces](p2-runtime-surfaces.md) |
| How do I export a local static workbench? | [P2 Runtime Surfaces](p2-runtime-surfaces.md) |
| How do I replay observations without dispatch? | [Operation Gate](operation-gate.md) |
| How do I compare CCR and PIC evidence? | [Cross-Repo Loop Conformance](cross-repo-loop-conformance.md) |
| How do I audit before publication without releasing? | [GitHub Action](github-action.md), [AUDIT](../AUDIT.md) |

## First-time agent guide

Purpose: use this index to pick the correct CCR document and command path
before mutating local runtime state.

First commands:

```bash
ccr agent explain --json
ccr asi quickstart --profile development --json
ccr mission next --mission mission:quickstart --compact --json
ccr workbench report --mission mission:quickstart --format markdown --out CCR_WORKBENCH.md
```

Safe boundary: CCR documentation distinguishes inspection commands, local
artifact writes, provider execution, release publication, and physical outcome
claims. Default P0/P1/P2 first-use commands are local-first and non-executing.

Expected outputs: commands should return JSON or documented files with `ok`,
`settled`, `external_execution`, blockers, residuals, and non-claims.

Failure/residual handling: unknown authority, malformed input, missing evidence,
schema mismatch, hash mismatch, stale evidence, and missing mission state must
remain visible as residuals or `residual_ready` objects.

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

Provider import: imported provider reports are evidence and task hints only.
Imported `safe_commands` are never executed automatically.

Phase formation cycle: agents use local packets, verifier evidence, residual
repair, baseline comparison, and `ccr phase form --profile development --json`
to improve a protocol-relative ASI-proxy mission without hiding blockers.

What not to claim: CCR does not detect or create real ASI, grant execution
authority, prove physical outcomes, or turn PIC/provider output into settlement.

## Safety Statements

- CCR does not detect or create real ASI.
- CCR does not grant execution authority.
- PIC/provider output is evidence only, not settlement.
- MCP/A2A descriptors or handoffs are evidence only, not delegated authority.
- Operation replay is not dispatch.
- Observation verification is not physical outcome proof.
- Static workbench is presentation, not proof.
- Residual market ranks work; it does not waive residuals.
- Provider registry is static metadata, not authority.
- Cache/index hits are not proof.
- Release is not performed by audit commands.
