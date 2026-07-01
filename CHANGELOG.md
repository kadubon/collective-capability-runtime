# Changelog

## 1.1.0 - 2026-07-01

- Added PIC-oriented workcell, distillation, residual, scheduler, foundry, and
  experiment helper commands for multi-agent ASI-proxy phase acceleration.
- Added TRC operation planning from PIC trace-check reports, including
  explicit dry-run provider dispatch and residual-preserving execution blockers.
- Added `ccr.trc_operation_plan.v1` schema validation and an ASI-proxy benchmark
  bundle that first-time agents can use for local roundtrip checks.
- Extended PIC compatibility audit expectations to the PIC v0.6.0 interop and
  TRC operation-readiness surfaces without treating PIC output as CCR settlement
  or execution authority.

## 1.0.0 - 2026-06-30

- Added SQLite indexing while preserving JSON artifacts as source records.
- Added v1 phase formation engine: effective graph, observation, threshold,
  baseline comparison, formation cycle, and certificate candidate generation.
- Added provider API with PIC and HTTP providers.
- Added repository audit command and v1 phase/provider/audit schemas.
- Added phase formation examples and v1 documentation.
- Added PIC route documentation for
  [kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)
  and `python -m pip install percolation-inversion-compiler`.

## 0.1.0 - 2026-06-30

- Added initial CCR Python package and `ccr` CLI.
- Added local runtime initialization, task queue, task leasing, packet submission,
  packet promotion, residual ledger, blackboard events, phase reports, and PIC
  dry-run/execute adapter.
- Added normative packet and task schema usage plus additional runtime schemas.
- Added examples, tests, Apache-2.0 licensing, and GitHub Actions CI.
