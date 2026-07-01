# ASI-Proxy Acceleration

v1.3.0 treats ASI-proxy/CARA acceleration as a target-valid comparison:
the target set, baseline upper envelope, and capital witness inputs must be
declared before outcome observation. A report can become a certified
acceleration candidate only when admitted lower-bound capital crosses the
declared target with positive margin before a resource-matched baseline upper
envelope.

Search terms: ASI-proxy acceleration, CARA, runtime capital witness, baseline
upper envelope, target-validity certificate, phase acceleration report, CCR
foundry, PIC interop, residual ledger.

CCR treats ASI-proxy acceleration as a runtime measurement problem: are finite
candidate packets, tasks, verifier plans, and residuals easier to coordinate
under a declared protocol?

The runtime never interprets a candidate as real ASI evidence. Positive progress
requires checked or settled packet status and the absence of linked open
blocking residuals. Candidate inflow alone is a bottleneck signal.

`ccr.phase_acceleration_report.v1` fails closed at the report level. Missing or
stale baselines, unapproved authority envelopes, non-accepted target laws,
absent admitted capital witnesses, proxy-only capital, and raw-net floor
failures set `ok=false` and produce explicit blockers. A valid report with no
blockers can still have `certified_acceleration_candidate=false` when the margin
is not positive.

## Runtime Signals

- candidate inflow;
- checked packet growth;
- open and blocking residual counts;
- baseline freshness;
- diagnostic reserve status;
- queue and lease diagnostics.

For TRC-governed real-world operation, CCR consumes a PIC
`pic.trc_trace_report.v1` report and builds a dry-run operation plan. The plan
can be dispatched to a provider only with an explicit `--execute` flag and
provider config. Execution-available remains distinct from executed, and CCR
does not treat provider output as physical outcome proof.

Unknown metrics stay unknown. They are not coerced to zero.

`capital_admitted=true` is lower-bound evidence, not settlement. Proxy-only
evidence cannot increase safe capital. Raw packet count, duplicate mass, and
unchecked candidate inflow do not count as positive foundry progress.

Phase-response foundry allocation is advisory:

```bash
ccr foundry allocate --strategy phase-response \
  --response-report examples/asi_proxy_acceleration_bundle/phase_response_control_step.accepted.json \
  --json
ccr foundry simulate-allocation \
  --cuts examples/asi_proxy_acceleration_bundle/foundry_cuts.example.json \
  --budget examples/asi_proxy_acceleration_bundle/foundry_budget.example.json \
  --json
```

These commands do not execute providers, promote settlement, or mutate runtime
tasks unless `--write-tasks` is explicitly supplied to `allocate`.
