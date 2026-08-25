---
name: collective-capability-runtime
description: "Coordinate multi-agent tasks, capability packets, independent workcells, verifier reports, residual ledgers, and resource-matched collective evaluation with Collective Capability Runtime (CCR). Use for local AI-agent coordination, task leasing, residual routing, collective verification, PIC-provider integration, mission/workbench inspection, or approval-bound operation planning. Start dry-run and preserve unresolved work. Do not use to claim real ASI, agent agreement as truth, execution authority, physical success, generic team management, or an LLM runtime."
license: Apache-2.0
metadata:
  author: K. Takahashi
  repository: https://github.com/kadubon/collective-capability-runtime
  version: "1.0"
---

# Collective Capability Runtime

Coordinate candidate work without converting agent count, agreement, provider output, or a local report into settlement.

## Fast path

1. Identify the local runtime root, mission, role, and whether the request is inspection or a local state mutation.
2. Start with CCR's dry-run/introspection surface and inspect `accepted`, `settled`, blockers, residuals, and non-claims.
3. Create or inspect a local mission only in an explicitly chosen runtime directory.
4. Lease tasks before doing task work; retain fencing tokens and idempotency keys for state transitions.
5. Route verification through the named provider, retaining imported evidence and candidate-only reasons.
6. Keep local coordination, approval, dispatch, observation, and physical outcome as separate states.

## Select a mode

### Inspect and route

Use this default for an unfamiliar runtime or a request to find the next safe action:

```text
uv run ccr agent explain --json
uv run ccr audit repo --json
uv run ccr --root RUNTIME_ROOT mission next --mission MISSION_ID --compact --json
uv run ccr --root RUNTIME_ROOT residual market --mission MISSION_ID --json
```

Read [mode selection](references/mode-selection.md) before choosing a mutating command.

### Local coordination

For explicit local coordination, use an isolated root rather than the repository:

```text
uv run ccr --root ccr-runtime asi quickstart --profile development --json
uv run ccr --root ccr-runtime task next --role ROLE --json
```

Lease before assigned task work. Lease, heartbeat, and completion are local transactional writes, not evidence that described external work happened.

### Verification and integration

Submit a packet candidate, then route it to the requested verifier provider. PIC is optional and its output is evidence only: `accepted` or safe commands do not settle CCR state or grant authority. Use `ccr integrate` to retain verifier reports, residuals, and candidate-only reasons.

### Collective evaluation

Use workcells and preregistered experiment commands for independent proposals and resource-matched comparisons. Treat effective support, error correlation, baseline, measurement limits, and residuals as separate evidence. Do not infer improvement from candidate volume or agent count.

## When to use

Use when the primary object is collective AI-agent work: a local mission, task queue/lease, capability packet, workcell, residual workflow, verifier-provider routing, or resource-matched coordination evaluation. Use PIC for an individual general agent-output check; VEK for a primary verification-evidence object; CMGL for persistent/retrieved memory; Audit-Closed for adaptive scientific inference; ATRB for trust-fixture benchmarking.

## Do not use

- Generic project management, chat-agent orchestration, or a generic LLM runtime.
- To treat a vote, repeated output, local database record, or provider receipt as truth or settlement.
- To execute provider/network operations without an explicit request, selected configuration, bound approval, and `--execute` where supported.
- To claim real ASI, model self-rewrite, model-weight updates, legal authority, or physical success.

## Evidence and result semantics

`ok` means only the named finite command or transition completed. `accepted` is local checker admission; it is not `settled`. `settled=false` is expected when declared requirements or residuals remain. Read [result and operation boundary](references/result-and-operation-boundary.md) before reporting execution, authority, or outcome.

## Retrieve only what is needed

- Read `docs/getting-started.md` for a new local mission.
- Read `docs/command-map.md` for a command's write boundary.
- Read `docs/collective-workcells.md` only for staged independent collaboration.
- Read `docs/measurement-protocol.md` only for resource-matched evaluation.
- Read `docs/operation-gate.md` only for an explicitly authorized operation request.
- Read [result and operation boundary](references/result-and-operation-boundary.md) for interpretation of reports, approvals, or provider output.

## Validate

```text
uv run pytest
uv run ccr agent explain --json
uv run ccr audit repo --json
```

For a local mission, retain the generated JSON report and rerun its relevant inspection command. Do not run a provider or network path merely to validate the skill.

## Report

State: outcome; runtime/mission and exact command; evidence and checked fields; residuals and blockers; authority and execution scope; non-claims; and the next safe action. Distinguish local state mutation, provider plan, provider dispatch, observation, and verified physical outcome.

## Required non-claims

- CCR does not prove real ASI, agent consensus, model improvement, or a physical outcome.
- A packet/provider result is candidate evidence unless the declared CCR policy settles it.
- Approval is parameter-bound and is not dispatch; a provider receipt is not a verified physical result.
- Unknown measurements and residuals do not become favorable defaults or disappear.
