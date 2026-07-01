# ASI-Proxy Benchmark Bundle

This dry-run bundle demonstrates the CCR side of the PIC/CCR interop loop.

It contains:

- `tasks.jsonl`: PIC-style repair work for CCR import;
- `residuals.jsonl`: PIC-style residual ledger entries;
- `baseline.json` and `collective.json`: resource-matched experiment inputs;
- `packets/candidate/`: a candidate-only packet with a blocking residual;
- `packets/checked/`: a checked dry-run packet fixture;
- `phase_report.json`: a compact phase report fixture;
- `runtime_report_for_pic.json`: a CCR-to-PIC runtime export fixture;
- `trc_trace_report.json`: a PIC TRC trace-check report for an operation candidate;
- `trc_operation_plan.json`: a CCR dry-run operation plan from that trace report;
- `expected_foundry_dashboard.json`: expected diagnostic shape.

The bundle is candidate-only and keeps command execution authority out of the
task records. It demonstrates residual preservation, resource-matched
comparison, and TRC-governed operation handoff, not real ASI detection,
creation, or physical outcome proof.
