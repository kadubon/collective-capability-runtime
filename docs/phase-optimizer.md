# Phase Optimizer

CCR can select interventions, reserve resources, route bounded work, and update
allocation from independently verified outcomes. Phase detection and settlement
rules remain unchanged. This is a finite optimization protocol, not evidence of
real ASI or a generally improved model.

Install `collective-capability-runtime[optimizer]` for Ed25519 result validation,
or `[optimizer,distributed]` for PostgreSQL and the authenticated API.

## Register a run

Copy `examples/phase_optimizer/config.json` and replace the task manifest,
source digests, verifier public key, budgets, and deadline with your actual
evaluation design. The example is a mechanics fixture, not a benchmark. Supply
a mission identifier; registration does not create or modify the mission.

```text
ccr --root ccr-runtime optimizer init --mission mission:study --config config.json --json
ccr --root ccr-runtime optimizer plan --run <run_id> --json
ccr --root ccr-runtime optimizer step --run <run_id> --apply --expected-revision 0 --json
ccr --root ccr-runtime optimizer claim --run <run_id> --trial <trial_id> --worker producer --json
```

`init` snapshots any existing mission packets and residuals into the shared run.
Already-admitted artifact digests cannot earn new reward. Subsequent residual
updates enter through signed observations; worker-local mirror files are not
a competing authority for distributed optimizer admission. The ordinary phase
detector continues using its existing local ledger.

`init` fixes the full configuration, policy version, task IDs, input content
digests, acceptance criteria, verifier keys, and holdout set. A changed
configuration requires a new run and policy version. `plan`, `status`, `report`,
and `step` without `--apply` neither initialize storage nor write artifacts.
Plan output includes feasible candidates, deterministic selection reasons,
resource accounts, and blockers. The actual `step --apply` recomputes under the
database lock; `--expected-revision` optionally rejects stale plans.

The five intervention kinds are `verification`, `residual_repair`,
`independent_proposal`, `distillation`, and `measurement`. They produce standard
CCR task payloads with the source reference/digest and concrete completion
criteria. Existing workers can claim local optimizer tasks; network-bound
trials use the explicit optimizer dispatch path. Workcells, residual repair,
and distillation are performed by the task's worker using existing CCR
protocols, not by executing imported command strings.

## Policy and resource accounting

Default epsilon is 0.2. Exploration samples feasible intervention/target pairs;
exploitation selects the highest observed verified-outcome/effort ratio.
Unobserved efficiencies remain null and have zero exploitation priority.
Equal priorities use stable ordering. The seed and committed revision make
selection reproducible. Incomplete trials never contribute to policy learning.

Every resource dimension has a separately enforced upper bound. Reserve a
conservative total including generation, communication, verification, and
control work. The `effort_resource` dimension defines the efficiency denominator;
other dimensions remain independent caps. In an HTTP trial, a `calls` dimension
must reserve at least one call. Remote providers must enforce their declared
resource limits; an observed overrun is recorded, receives no reward, and blocks
further allocation. CCR cannot force an external service to honor a spending
bound after dispatch.

`evaluation.resource_envelope` is the per-arm comparison budget. Two such
envelopes must leave positive training capacity under `resource_limits`.
Training capacity is `resource_limits - 2 * evaluation.resource_envelope`.
At least 20% of training capacity is reserved for measurement interventions.
Training consumption is **also charged against the candidate evaluation
envelope**: learning is not free. These accounts overlap; do not sum the
training and candidate accounts as independent spend. Each physical trial is
reserved only once. Select limits that leave sufficient candidate evaluation
capacity after training.

For example, total cost 100 and evaluation envelope 40 allow training up to 20;
with training cost 10, the candidate has 30 left and the baseline has 40.
Unused reserve remains unused. Missing costs are rejected, not replaced by
zero. Pending and unknown-outcome trials retain their reservation.

## HTTP approval and dispatch

An intervention may include one existing `ccr.trc_operation_plan.v1` template.
`step` binds it to the selected trial, source digest, acceptance criteria, and
resource upper bounds. Review the returned `trial.operation_plan` and save that
exact object as `plan.json`. Use an actual provider config with HTTPS,
allowlisted hosts, bounded time/bytes, and the existing side-effect policy.

```text
ccr --root ccr-runtime operation approve --plan plan.json --provider http --config http.json --approver human.operator --expires-at <expiry> --nonce <unique_nonce> --json
ccr --root ccr-runtime optimizer run --run <run_id> --trial <trial_id> --worker producer --fencing-token <token> --config approved-http.json --execute --json
```

`approved-http.json` is the same config plus the returned `operator_approval_ref`
and its `approval_nonce`. The optimizer never issues approvals. Changed plans,
arguments, providers, or resource limits require new approvals. `run` performs
one finite dispatch attempt; repeated cycles are driven by the caller. It does
not create a hidden background executor.

Preflight and approval rejection before sending can be corrected and retried
with current authority. Once sending may have occurred, timeout or interruption
leaves `outcome_unknown` or durable `dispatching` state. Unknown execution or
network-call flags remain null rather than asserting no external activity. These states prevent
new allocation and automatic replay. Reconcile with an independently signed
observation; never infer success from a provider receipt or retry blindly.

## Result contract and recovery

The independent evaluator signs a `ccr.optimizer_result.v1` object, excluding
only `signature_base64`, with Ed25519 over `ccr.ids.canonical_bytes(payload)`.
The configured verifier key must belong to an identity distinct from the
producer, packet issuer, and leased worker. Key custody and evaluator accuracy
remain the operator's trust boundary. An evaluator must check the registered
source content digest and acceptance criteria before signing acceptance.

Required fields are documented by `schemas/optimizer-result.schema.json`:
run/trial/target IDs, configuration/input digests, worker identity and fencing
token, observed time, actual total resource use, accepted boolean, residuals,
verifier identity, and signature. Accepted results additionally need a checked
packet with an artifact `content_sha256` matching `artifact_sha256`.

Use the server's `status.server_time` clock reference for observation timestamps.
Database time governs leases and trial windows, including multi-host deployments.
Signature, scope, stale fence, malformed input, and missing-cost failures reject
the transition. A valid signed rejection records a zero-reward trial. A valid
candidate packet or a packet with unknown coordinates or blocking residuals also
receives zero. Imported packets remain evidence snapshots; optimizer ingestion
does not promote packet status or waive settlement gates.

```text
ccr --root ccr-runtime optimizer ingest --run <run_id> --file signed-result.json --json
ccr --root ccr-runtime optimizer plan --run <run_id> --json
ccr --root ccr-runtime optimizer heartbeat --run <run_id> --trial <trial_id> --worker producer --fencing-token <token> --json
ccr --root ccr-runtime optimizer stop --run <run_id> --json
```

A repair observation may name `resolved_residual_ids`. Resolution requires a
registered `residual_repair` intervention, a residual bound to that target/input,
and an eligible independently verified repair artifact. The shared ledger keeps
the original residual and records its resolved status, result digest, verifier,
and repair digest. Merely omitting an old blocker cannot resolve it.

Each registered target contributes at most one binary outcome per arm.
Duplicate artifacts are credited once across training and candidate evaluation;
baseline accounting is independent. Identical result retries are idempotent;
conflicting result digests are rejected. Old fencing tokens cannot update a
re-leased task. Independent signed observations can resolve an expired or
crashed dispatch while retaining its historical residuals and receipt.
`stop` prevents new claims/allocations/dispatches and preserves pending work;
valid late observations can still be ingested.

## Independent comparison

```text
ccr --root ccr-runtime optimizer freeze --run <run_id> --json
ccr --root ccr-runtime optimizer step --run <run_id> --apply --json
ccr --root ccr-runtime optimizer report --run <run_id> --json
ccr --root ccr-runtime optimizer export --run <run_id> --json
```

Freeze only after training observations are complete. The saved policy digest
then remains fixed. Evaluation uses only the predeclared holdout tasks; its
outcomes never update the policy. Baseline uses the predeclared fixed
intervention representing the current allocation workflow. Both arms receive
the same resource envelope, with training/control costs charged to the
candidate. Match tool versions and external evaluator conditions operationally.

The existing fixed-horizon comparison computes paired outcome differences in
registered task order. `improvement_claim_admissible` requires complete holdout
data, no run blockers, and a positive conservative lower confidence bound.
Incomplete, negative, and inconclusive results remain visible. A passing
mechanics test establishes runtime behavior, not a real performance improvement.

## Distributed storage and API

Set `CCR_DATABASE_URL` consistently for optimizer, operation approval, and worker
commands. The API instead uses its explicitly selected store, including a
custom `--database-url-env`. Never mix a PostgreSQL optimizer with approvals
created in another backend.

New additive tables are `ccr_control`, `ccr_control_outbox`, and
`ccr_control_migrations` (version 1). The first registration initializes them;
no existing task or packet tables are rewritten. PostgreSQL serializes schema
initialization and locks each run/approval aggregate transactionally. SQLite
uses `BEGIN IMMEDIATE`. Plan selection, reservation, standard task payload,
policy revision, and immutable outbox snapshot commit together. Network calls
occur outside database transactions.

DB records are authoritative control state. `export` materializes committed
JSON snapshots through CCR's content-addressed export format under
`exports/optimizer/`. Export can be repeated after a crash. Outbox history is
never discarded; backup the database, not just JSON exports. Existing SQLite
approval artifacts retain their compatibility consumption path. PostgreSQL
approvals are loaded and consumed exclusively from the shared registry.

The existing OIDC + DPoP middleware protects:

- `POST /v1/optimizer`: human registration.
- `GET /v1/optimizer/{run_id}`: authenticated report.
- `POST /v1/optimizer/{run_id}/step|freeze|stop`: human control.
- `POST /v1/optimizer/{run_id}/claim|heartbeat|dispatch|ingest`: worker execution
  or transport of independently signed evidence. Worker identity comes from
  authentication, not the request body's claim.
- `POST /v1/operation-approvals`: existing human approval, now shared through the
  server's selected backend.

No endpoint bypasses parameter-bound approval or authorizes imported commands.
The finite CLI and API transitions can be coordinated by an external scheduler;
CCR still does not supply an LLM or an automatic approval authority.

## Validation

Run `pytest tests/test_optimizer.py`. Set `CCR_TEST_POSTGRES_URL` to an isolated
PostgreSQL 16+ test database to include real concurrent reservation, approval,
lease, and reward tests. The tests create their own uniquely identified runs.
Mock HTTP tests never call a real provider. Run the repository's lint, type,
schema-registry, regression, and local audit gates before rollout.


## Verified growth opt-in (v1.8)

Use the separate `ccr.growth_profile.v1` registration with
`policy=verified_growth_v1` to enable receiver-specific service accounting and
finite dependency-bundle allocation. Existing v1 optimizer schemas and signing
bytes remain unchanged. See [Verified Growth](verified-growth.md) for the
complete register, check, reserve, lease, signed outcome, reuse, replay and
frozen-comparison path. Service observations, planning forecasts and causal or
statistical improvement are distinct. Growth does not grant admission, approval
or settlement authority. Unresolved attribution and invalidated evidence remain
visible; synthetic records cannot establish production performance.
