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
