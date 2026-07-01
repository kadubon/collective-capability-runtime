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

## Minimal Run

```bash
ccr demo pic-roundtrip --json
ccr init
ccr task import --file examples/asi_proxy_benchmark_bundle/tasks.jsonl --provider pic --json
ccr foundry dashboard --json
ccr schedule diagnose --json
ccr operation plan --trace examples/asi_proxy_benchmark_bundle/trc_trace_report.json --json
```

Do not execute safe command hints without explicit authority. Preserve
candidate-only reasons, settlement blockers, and residuals throughout the loop.
TRC operation plans are dry-run by default and require explicit provider config
plus `--execute` before any real-world side effect can be attempted.

`settled=false` is expected for this harness.
