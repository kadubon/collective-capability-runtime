# Native companion interchange (1.9.0)

This additive implementation provides the finite opt-in profile introduced in
CCR 1.9.0. See [validation evidence and publication checks](native-interchange-validation.md).
Legacy `optimizer interchange`, growth schemas and signed bytes retain their
existing meanings. OAWM completion is not assumed.

## Install the separate conformance environment

Use Python 3.14 and a disposable environment outside the repository. Install
`scripts/requirements-native.lock` with `uv pip sync --require-hashes`, then
install CCR with `--no-deps`. The ordinary CCR environment and Python 3.10 floor
do not gain these optional companion dependencies. The lock includes transitive
dependency hashes. The ALT wheel is obtained from its existing GitHub Release.

`examples/native_interchange/artifacts.json` records the exact published wheel
and available sdist hashes. `installed-pins.json` records Python source, JSON
schema/data and metadata hashes derived from those verified wheels. Every native
checker invocation verifies those installed files before importing its fixed
entry points. The source tags are recorded separately in `source-tags.json`.
These checks establish byte identity, not a claim that a build provenance
attestation has been independently verified.

## Commands and local authority

```text
ccr optimizer native sources --json
ccr optimizer native inspect --file source.json --json
ccr optimizer native project --file source.json --registration registration.json --json
ccr optimizer native register --run RUN --registration registration.json --expected-revision 0 --json
ccr optimizer native check --run RUN --file source.json --projection projection.json --json
ccr optimizer native stage --run RUN --file source.json --projection projection.json --expected-revision 1 --idempotency-key DELIVERY --json
ccr optimizer native admit --run RUN --proposal-id DIGEST --expected-revision 2 --json
ccr optimizer native export --run RUN --json
ccr optimizer native feedback --run RUN --export export.json --report report.json --json
ccr optimizer native reconcile --run RUN --export export.json --report report.json --expected-revision REVISION --json
ccr optimizer native replan --run RUN --file cpcf-source.json --json
ccr optimizer native replay --run RUN --json
ccr optimizer native status --run RUN --json
ccr optimizer native example --json
```

All commands emit JSON to stdout. Register, stage, admit and reconcile explicitly
write the selected ControlStore. Inspect, project, check, export, feedback,
replan, replay and status do not initialize or mutate it. The example uses an
isolated temporary SQLite root and ephemeral synthetic verifier keys. There is
no new unauthenticated HTTP route. Database selection uses the existing
`--database-url-env` convention on commands that access a run.

Admission admits an advisory source-to-action binding. The existing plan checker
still controls reservation and immediate task creation. Claim/dispatch recheck
the binding and existing receiver eligibility. Native checking runs outside
database transactions; revision, expiry and immutable-source predicates run
inside the transaction. A native acceptance never supplies approval or settlement.

## Supported representations

Four new closed wire schemas are registered and packaged:
`ccr.native_source.v1`, `ccr.native_registration.v1`,
`ccr.native_projection.v1`, and `ccr.native_accounting_export.v1`.
Sources contain original native documents as UTF-8
JSON strings. Raw source/document SHA-256 values remain separate from producer
canonical identities and CCR canonical registration digests. Parsing bounds
bytes, nodes, depth, containers, strings and integer/rational size. Input cannot
choose imports, schema URLs, executables or output paths.

The accounting export preserves original CCR journal records as canonical JSON
strings. The checker compares those strings to independently authenticated CCR
history; it does not reinterpret legacy fractional packet fields as native
quantities. The surrounding native accounting data still uses strict integer
tokens and exact rational strings. Existing CCR signing bytes remain unchanged.

The registration is immutable before training work. It binds run/config/study,
training arm, pool, existing actions and action digests, source contract/action,
validity and exact or conservative upper unit conversion. This development
subset permits synthetic evidence only. Fractional costs cannot be rounded down.
An optional `pools` map binds producer resource names to existing canonical CCR
capacity keys; absent aliases retain exact names. ALT occupancy and VEK pool
claims are summed after alias resolution, so renaming a pool cannot enlarge it.
Every actionable ALT, VEK or CPCF contract also requires a `clocks` entry keyed
by its contract digest: `utc_origin`, exact rational `tick_origin`, and positive
`seconds_per_tick`. ALT/VEK rates must match the native slot duration; CPCF uses
seconds. Earliest times round later and deadlines earlier at UTC microsecond
precision. Missing clocks, overflow and unsupported historical clock events fail
closed. CAIT derives its separate integer-second clock from signed CCR history.

- ALT 0.5.0: real plan and task-sidecar reconstruction, formation/transfer/reuse
  mapping, scoped receivers/inputs/evaluators, and signed prerequisite outcomes.
  Shared physical cost IDs without an explicit supported allocation are rejected.
- VEK 1.3.0: real history replay, plan/report checking, separate budget and pool
  constraints, serial timing including CCR cleanup, and signed negative checks
  with zero capability service. Prerequisite work must map uniquely to registered
  work in the same source contract. Completion prerequisites accept qualified
  positive or negative results; positive/negative activation requirements accept
  only their respective signed result. Pending, censored, invalid, timeout and
  inconclusive work do not unlock these dependents. Unmapped or contradictory
  prerequisites, unsupported verifier separation and unsafe parallel translations
  are rejected. Forecast service is never observed capacity.
  Status/replay distinguish positive, negative, timeout, invalid, inconclusive,
  pending and censored work from signed CCR outcomes and the observation window.
  Only qualified positive/negative results count as completed verification.
  Censoring is a read-only label and does not release reservations.
- CAIT 0.2.0: original signed CCR costs, supported root creation, use and withdrawal
  enter native source streams and native analysis/checking. Reconciliation checks
  every expected physical event as well as totals. Unsupported history remains
  partial. Reconciliation adds zero reward/stock; qualified losses can enable
  preregistered funded review. Feedback storage is bounded to 64 records.
- CPCF 1.0.1: only the maintained `growth_control` facade is used. A current
  observable first action is advisory. Optional preregistered status-to-symbol
  maps reconstruct visible history from qualified, signed training results.
  Unmapped results, mismatched history and old proposals cannot select a branch.
  Replanning does not automatically stage or admit the new proposal.
  Each binding requires a closed `scope` containing native action/capability
  digests, the native verifier, a trusted host verifier, and the frozen host task
  digest. `effects=model_only` prevents native model effects from becoming
  observed capacity. Unmapped obligations/preconditions and inherited evidence
  are rejected. Another trusted host verifier cannot substitute for this scope.

The planner checks native admission for the immediate task. It still funds and
checks the entire registered CCR bundle, including cleanup. Hypothetical future
bundle steps cannot become tasks before their own current admission check.
CPCF continuation guarantees are explicitly not transferred.

The registered host validity interval is checked again at staging, admission,
planning, reservation and lease. The action's conservative execution and cleanup
must finish before its exclusive endpoint. A signed result whose event time or
receipt is outside that interval remains a charged attempt without qualification
or service credit. Replay uses the original receipt time, so a later replay
does not retroactively expire historical credit. Rehashing derived journal flags
cannot promote such an invalid result. Source clock windows are separately
reconstructed from the immutable native documents. Staging/admission reject
future evidence and expired windows; reservation/lease must fit execution and
cleanup. An observation must meet the execution endpoint, while its receipt must
meet the cleanup endpoint. CPCF visible history advances the conservative native
elapsed bound and required evidence retains its native expiry.

## Executable finite evidence

The integrated example considers a CPCF probe, runs one explicitly changed and
native-checked VEK serial verification problem and a newly checked ALT serial
problem with explicit cleanup gaps, then ALT formation, transfer and
four services through CCR reservation, lease and signed-result code. The negative
verification result contributes no service. Eight distinct attempts consume
16 synthetic cost units; four service events retain one historical asset.
After a signed withdrawal, native CAIT reconciliation changes the next allocation
to funded review without adding cost, service or stock again.
The example uses a finite simulated UTC clock over real SQLite transactions,
advancing execution and cleanup separately. Imported documents cannot select
this example store; normal runtime commands retain the database clock. Native
tests likewise freeze or explicitly advance synthetic time while retaining real
SQLite/PostgreSQL locks, revisions, outbox writes and contention.

Separate tests exercise subsequent CPCF replanning, actual SQLite/PostgreSQL
four-worker contention, rollback after selected journal faults, stale revisions,
expiry and source/receiver/quantity substitutions. Selected fault injection is
not exhaustive mutation qualification.

Evidence labels have separate meanings: `documented` describes a contract;
`schema_checked` its wire form; `native_checked` the pinned companion's checked
properties; `ccr_runtime_tested` the finite host execution; and
`operationally_observed` actual admitted operating evidence. The synthetic
examples do not establish the last category or causal/statistical acceleration.

## Migration and remaining qualification

Existing users need no migration. New native registrations are opt-in and cannot
amend a frozen growth catalogue. Unpublished draft native records using the old
`profile` labels must be recreated using the registered schema versions; this
does not change any released legacy record or signature.

The supported profile rejects unmapped VEK verifier separation, inherited native
history, ALT dependency lifecycles, shared ALT costs without a unique owner,
CPCF interval reservations and host effects outside its explicit model-only
scope. These are fail-closed profile limits, not silently translated features.
Current qualification and publication gates are tracked in the
[release validation record](native-interchange-validation.md). Passing the finite
example does not establish operational performance or complete publication.
