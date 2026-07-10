# Operation Gate

CCR separates plan, preflight, dispatch, and observation.

`operation_ready` means a PIC/TRC report has enough finite trace structure to
plan a scoped handoff. `provider_dispatch_ready` means the provider-side
preflight and policy checks pass. `physical_dispatch_ready` means the physical
certificate fields are accepted and fresh. None of these states means the
operation was dispatched, executed, settled, or physically proven.

Dispatch requires `ccr.trc_operation_plan.v1`, a matching
`ccr.trc_operation_preflight.v1`, explicit `--execute`, `allow_execute=true`,
an operator approval reference, a dispatchable side-effect policy, a closed
provider circuit, and an accepted provider plan. Physical providers are denied
unless a separate physical gate is ready.

Search terms: TRC operation gate, preflight, provider_dispatch_ready,
physical_dispatch_ready, operator approval, provider circuit breaker,
observation verifier.

## v0.9/v1.4 Agent Loop Addendum

Operation gates keep operation readiness, provider dispatch readiness, physical dispatch readiness, execution, and physical outcome proof separate. `operation_ready` is not executed; `provider_dispatch_ready` is not dispatched; `physical_dispatch_ready` is not physical outcome proof.

Structured MCP/A2A reports are primary when supplied; legacy boolean fields are preserved only for backward compatibility.

## Replay Boundary

`ccr operation replay-manifest` and `ccr operation verify-observation` are
local evidence-review commands. Operation replay is not dispatch. Observation verification is not physical outcome proof. A source dispatch report may carry
`executed=true` evidence, but the replay command itself keeps
`external_execution=false`, `network_call_performed=false`,
`provider_dispatch_ready=false`, `physical_outcome_proven=false`, and
`settled=false`. Missing verifier acceptance, rollback confirmation, hazard
follow-up, or unresolved incident evidence becomes residual-ready work.

## Parameter-Bound Dispatch

Side-effect dispatch requires an approval artifact created from the exact plan
and provider config:

```bash
ccr operation approve --plan plan.json --provider http --config config.json \
  --approver human.operator --expires-at 2030-01-01T00:00:00Z \
  --nonce operation.1 --json
```

Add the returned `approval_id` as `operator_approval_ref` and echo the nonce as
`approval_nonce` in the dispatch config. CCR binds the plan digest, provider,
arguments, resource limits, scope, expiry, nonce, and use count. Dispatch
rechecks authority with current system time and consumes one use atomically.

The generic `provider execute` command cannot call a network provider. HTTP
dispatch requires HTTPS, `allowed_hosts`, redirect denial, public DNS
resolution, and time/byte limits.

`physical_outcome_proven` remains false for compatibility. A separate signed,
scoped, in-window verifier report is required for
`physical_outcome_verified=true`.
