# Challenge Harness

CCR's challenge harness is a dry-run runtime test for protocol-relative
coordination. It imports candidate work, schedules it, preserves residuals, and
exports reports that PIC can check.

CCR does not detect real ASI, create real ASI, update model weights, or grant
execution authority.

Do not summarize first. Run the minimal loop, produce one candidate packet, one
residual, and one verifier or phase report, then inspect what remains blocked.

## Runtime Checks

- PIC task JSONL imports into the normal task queue.
- PIC residual JSONL imports into the normal residual ledger.
- Candidate packets do not count as positive settled progress.
- Foundry dashboards report unknown baselines and diagnostic reserve as unknown.
- Scheduler reports can recommend rebalance steps without mutation.
- Experiments compare resource-matched dry-run results only.
- CARA acceleration reports require a declared target set, baseline upper
  envelope, and admitted runtime capital witnesses.
- MCP descriptors and A2A handoffs are checked evidence, not delegated
  authority.

## Minimal Run

```bash
ccr demo pic-roundtrip --json
ccr init
ccr task import --file examples/asi_proxy_benchmark_bundle/tasks.jsonl --provider pic --json
ccr foundry dashboard --json
ccr schedule diagnose --json
ccr operation plan --trace examples/asi_proxy_benchmark_bundle/trc_trace_report.json --json
ccr phase acceleration-report --target examples/asi_proxy_acceleration_bundle/target.json --baseline examples/asi_proxy_acceleration_bundle/baseline_upper_envelope.json --capital examples/asi_proxy_acceleration_bundle/capital_witnesses.jsonl --json
```

Do not execute safe command hints without explicit authority. Preserve
candidate-only reasons, settlement blockers, and residuals throughout the loop.
TRC operation plans are dry-run by default and require explicit provider config
plus `--execute` before any real-world side effect can be attempted.

`settled=false` is expected for this harness.

## v1.4 Loop Challenge

The runtime challenge is to help agents decide which residual, token, baseline,
observation, or duplicate-mass cut to repair next while keeping all authority
separate. `ccr loop next` must remain advisory and non-mutating. Cache/index
rebuilds must not become proof. Provider preflight, dispatch, execution, and
observation remain separate reports.
