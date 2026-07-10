# CCR Documentation

Use this index to choose a workflow. CCR is a local-first coordination runtime;
it does not supply an LLM or treat agent agreement as verified truth.

## Start Locally

1. Install CCR and run [Getting Started](getting-started.md).
2. Read the generated workbench and its blocking residuals.
3. Choose the next workflow from the table below.

The installed-package quickstart needs no repository examples. Commands under
`examples/` are explicitly source-checkout exercises.

## Choose A Task

| What you need to do | Guide | Main command |
|---|---|---|
| Create and inspect a local mission | [Getting Started](getting-started.md) | `ccr asi quickstart` |
| Find the next command and its write boundary | [Command Map](command-map.md) | `ccr agent explain` |
| Gather independent proposals and critiques | [Collective Workcells](collective-workcells.md) | `ccr workcell create` |
| Recover, heartbeat, or complete worker tasks | [Collective Workcells](collective-workcells.md) | `ccr task lease` |
| Run PostgreSQL workers and the API | [Distributed Runtime](distributed-runtime.md) | `ccr server run` |
| Measure collective improvement fairly | [Measurement Protocol](measurement-protocol.md) | `ccr experiment register` |
| Review and approve an external operation | [Operation Gate](operation-gate.md) | `ccr operation preflight` |
| Review real-world evidence boundaries | [Real-World Impact](real-world-impact.md) | `ccr operation observe` |
| Validate MCP or A2A metadata | [MCP and A2A Safety](mcp-a2a-safety.md) | `ccr mcp preflight` |
| Check PIC/PIC-TS parity | [Cross-Repo Conformance](cross-repo-loop-conformance.md) | `ccr conformance parity` |
| Prepare a public release | [Security Audit Checklist](security-audit-checklist.md) | `ccr audit repo` |

## Read Reports Correctly

- `ok=true` means the finite command completed; it does not prove the claim.
- `accepted=true` is checker acceptance, not CCR settlement.
- `settled=false` is expected while blockers remain.
- Unknown coordinates remain unknown and cannot contribute positive progress.
- Residuals are work records, not exceptions to hide or delete.
- `physical_outcome_proven` is always false; signed scoped evidence may set
  `physical_outcome_verified`.

## Safety Boundaries

- Operation replay is not dispatch.
- Provider or PIC evidence is not settlement.
- MCP and A2A metadata is not delegated authority.
- A static workbench or registry is not proof.
- Imported safe commands are never executed automatically.
- Release audit commands do not push, tag, publish, or upload packages.

See [Security Policy](../SECURITY.md), [Operation Gate](operation-gate.md), and
the [Security Audit Checklist](security-audit-checklist.md) for the complete
control set.

## Reference Guides

- [ASI-Proxy Mission](asi-proxy-mission.md)
- [ASI-Proxy Loop](asi-proxy-loop.md)
- [ASI-Proxy Measurement](asi-proxy-acceleration.md)
- [Agent Loop Protocol](agent-loop-protocol.md)
- [Performance](performance.md)
- [P2 Runtime Surfaces](p2-runtime-surfaces.md), retained as a compatibility map
- [PIC Roundtrip](ccr-pic-roundtrip.md)
- [PIC Interoperability](../INTEROP_PIC.md)
- [GitHub Action](github-action.md)

Search terms: CCR documentation, AI agent runtime quickstart, collective
workcell, residual workflow, PostgreSQL agent worker, resource-matched
collective intelligence, OIDC DPoP, operation approval, and PIC compatibility.
