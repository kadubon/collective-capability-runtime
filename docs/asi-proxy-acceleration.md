# ASI-Proxy Acceleration

CCR treats ASI-proxy acceleration as a runtime measurement problem: are finite
candidate packets, tasks, verifier plans, and residuals easier to coordinate
under a declared protocol?

The runtime never interprets a candidate as real ASI evidence. Positive progress
requires checked or settled packet status and the absence of linked open
blocking residuals. Candidate inflow alone is a bottleneck signal.

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
