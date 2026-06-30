# Changelog

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
