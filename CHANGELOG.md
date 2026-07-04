# Changelog

## Unreleased

- Improves first-time-agent readiness with a clearer README, a docs index,
  getting-started guide, P0/P1/P2 command map, richer `ccr agent explain`
  navigation output, and repository audit/test coverage for those routes.

## 1.5.0 - 2026-07-04

- Hardens the Mission Runtime Layer with mission-scoped packet/residual
  isolation, schema-valid failure reports, `--fail-on blocking_residual` and
  `--fail-on missing_mission` report exit policies, bounded UTF-8/JSON input
  handling, schema-bound bundle validation, reference-closure checks, markdown
  escaping, and stronger deterministic overclaim detection.
- Adds local-only P1 gate facades: `ccr mcp inspect-descriptor/preflight`,
  `ccr a2a inspect-card/preflight-handoff`, `ccr ingest trace/repo`, provider
  manifest/conformance reports, provider manifest schemas, and a non-publishing
  `.github/actions/ccr-audit` helper.
- Adds P2 runtime surfaces: residual work market/bounty/diff, static workbench
  export, operation replay/observation verification, cross-repo CCR/PIC
  conformance reports, and a static provider plugin registry.
- Adds a local Mission Runtime Layer with `ccr asi quickstart`, `ccr mission
  init/status/ingest/next/report`, and `ccr workbench report` for immediate
  ASI-proxy mission setup without provider execution, network calls, settlement,
  or physical outcome claims.
- Adds deterministic `ccr claim extract/audit/passport` commands that skip
  fenced code blocks, classify unsupported claims, and convert real-ASI,
  execution-authority, physical-outcome, model-update, and provider/PIC
  settlement overclaims into residual-ready objects.
- Adds `ccr bundle validate` plus mission/workbench/claim/bundle schemas and a
  local `examples/asi_proxy_mission_bundle/` fixture. Validation fails closed on
  missing target/baseline/non-claim surfaces, implicit execution, implicit
  settlement, capital admission without witness refs, and cache/index proof
  confusion.

## 1.4.0 - 2026-07-02

- Adds the advisory `ccr loop` layer, token distillation/import/dedup/next
  commands, duplicate-aware foundry metrics, graph quotient diagnostics,
  performance/cache/index reports, and SQLite WAL/index migrations.
- Adds `examples/asi_proxy_loop_bundle/`, v1.4 public report schemas, and
  first-time-agent docs for ASI-proxy loops, token extraction, operation
  observation, phase intervals, SQOT resource tensors, BIT frontiers, and
  cross-repo loop conformance.
- Preserves non-execution boundaries: loop next is non-mutating, safe commands
  are hints, token import is not settlement or capital admission, cache/index
  rebuilds are repairable local indexes, and physical observations require
  scoped verifier acceptance.

## 1.3.0 - 2026-07-01

- Added v0.8 PIC/PIC-TS interop surfaces for target-valid ASI-proxy/CARA phase
  acceleration, runtime capital witness import/listing, MCP/A2A report
  fixtures, SQOT probe/protocol diagnostics, and BIT MEC frontier examples.
- Tightened TRC dispatch so explicit execution requires a dispatch-ready
  preflight report or an internally regenerated equivalent preflight. Failing
  preflight, provider-circuit, side-effect-policy, or plan-schema checks return
  residuals and do not call `provider.execute`.
- Added provider circuit-breaker, availability, shadow, incident, observation
  repair, probe, and foundry active-cut commands. These are advisory and
  non-executing unless a separate operator-approved dispatch path is taken.
- Added phase-response foundry allocation and simulation inputs. Allocation is
  advisory, preserves diagnostic reserve, and only writes tasks when
  `--write-tasks` is explicitly supplied.
- Tightened CARA checks so unapproved authority, non-accepted target laws,
  missing admitted capital witnesses, proxy-only capital, and raw-net floor
  failures set the phase acceleration report to `ok=false`.
- Extended foundry dashboard residual propagation so direct, referenced,
  dependency, lineage, imported capital, observation, authority, and physical
  blockers prevent raw packet count from being treated as progress.

## 1.2.0 - 2026-07-01

- Added `ccr.trc_operation_preflight.v1` and
  `ccr.trc_operation_observation.v1` schemas plus `ccr operation preflight`,
  `dispatch`, and `observe` commands.
- Re-checks TRC authority freshness during operation plan construction so
  expired, time-unknown, fixture-only, or inactive authority fails closed even
  when a stale PIC trace report claims readiness.
- Accepts PIC `pic.trc_operation_gate_report.v1` as a non-executing operation
  planning input while preserving residuals, `executed=false`, and
  `settled=false`.
- Documents that `operation_ready`, `provider_dispatch_ready`, and
  `physical_dispatch_ready` are not execution or physical outcome proof.

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
