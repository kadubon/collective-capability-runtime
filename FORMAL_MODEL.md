# CCR Formal Model v1

Related PIC runtime: [kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler).

```bash
python -m pip install percolation-inversion-compiler
```

PIC is an optional verifier relation. It is not a CCR settlement oracle.

CCR is a finite transition system over JSON artifacts plus a SQLite index.

## First-time agent guide

Purpose: use the formal model to understand why CCR separates admissible
packet work, residual debt, execution availability, provider evidence, and
phase-candidate status.

First commands:

```bash
ccr agent explain --json
ccr phase graph --json
ccr phase observe --json
ccr phase form --profile development --json
```

Safe boundary: every formal relation is protocol-relative and finite; execution
availability is a witness relation, not an execution trace.

Expected outputs: graph, observation, threshold, comparison, and certificate
candidate artifacts expose finite metrics, blockers, reasons, and `settled=false`.

Failure/residual handling: failed predicates become residual debt, failed
components, abstention reasons, or repair tasks rather than hidden state.

Provider import: provider reports enter the model as external evidence
relations and residual sources, not as direct settlement functions.

Phase formation cycle: repeated packet verification, residual reduction,
effective-edge construction, and resource-matched comparison can improve a
protocol-relative candidate phase.

What not to claim: the model does not assert metaphysical ASI, oracle truth,
physical outcome truth, autonomous authority, self-rewrite, or model-weight
change.

## Packet

A packet is:

```text
P = (id, status, claims, artifacts, scope, provenance, verifiers,
     verifier_reports, residuals, risk, reuse, lineage, execution_availability,
     pic_interop)
```

`status(P)` is an element of the packet lattice in `SPEC.md`.

Positive phase contribution is:

```text
Positive(P) =
  status(P) in {checked, settled}
  AND no_open_blocking_residual(P)
  AND authority_valid(P)
  AND liquidity_lower_bound(P) >= 0
```

Candidate-only packet volume is observed but excluded from `Positive`.

## Task

A task is:

```text
T = (id, status, role, priority, objective, inputs, expected_outputs,
     constraints, lease, verifier_plan, residual_policy, pic_interop)
```

The scheduler returns the open task with maximal `(priority, -created_at, id)`
for the requested role. Leasing is a separate transition.

## Residual Ledger

A residual is:

```text
R = (id, status, severity, kind, description, blocking, object_ref, source)
```

Residual preservation invariant:

```text
failed_validation OR failed_promotion OR candidate_only_reason
OR settled_blocker OR authority_gap OR provider_failure OR baseline_mismatch
=> residual OR residual_ready_object
```

## Effective Graph

The effective graph is:

```text
G_eff = (V, E, eligibility, contribution)
```

where `V` contains local packets and `E` contains dependency or semantic edges.
An edge contributes positively only when all incident packet nodes are positive
and edge evidence is checked or settled. Raw/candidate/rejected/quarantined mass
does not increase positive graph metrics.

## Execution Availability

Execution availability is a witness relation:

```text
ExAv(P, gate_set, side_effect_policy, rollback)
```

It is not an execution trace:

```text
ExAv(P, ...) does not imply Executed(P)
```

CCR phase observations set `executed_path_count = 0` unless an explicit future
schema introduces a separate execution evidence type. v1 does not introduce that
type.

## Observation

A phase observation is:

```text
O = metrics(G_eff, residual_ledger, queue_state)
```

with components:

```text
accepted_packet_count
effective_edge_count
execution_available_path_density
autocatalytic_closure_score
verification_throughput
residual_debt
false_liquidity_load
salience_obstruction_load
```

## Threshold Predicate

An ASI-proxy threshold is a protocol-relative predicate:

```text
Theta(O) -> {accepted, abstain, rejected}
```

`Theta(O)=accepted` means the finite CCR protocol threshold is satisfied. It
does not assert real ASI, oracle truth, physical outcome truth, or model-weight
change.

## Baseline Predicate

Baseline comparison is:

```text
B = (resource_envelope, comparison_class, metrics, validity_domain)
Compare(B, O) -> (resource_matched, deltas, residual_ready)
```

If `resource_envelope(B) != resource_envelope(O)`, comparison emits a blocking
residual-ready object. The mismatch is preserved rather than discarded.

## Certificate Candidate

A collective phase certificate candidate is:

```text
C = (G_eff, O, Theta(O), residual_obligations, baseline_obligations)
```

`accepted(C)` requires threshold acceptance and no blocking residual obligations.
`settled(C)` is always false in v1. Promotion to a settled phase claim would
require a future verifier-controlled settlement gate beyond CCR's candidate.

## Provider Relation

A provider relation is:

```text
Provider(plan | execute | normalize)
```

Planning is non-executing. Execution requires explicit operator authority. A
provider report is evidence input, not settlement authority.

## Promotion Predicate

Candidate to checked:

```text
schema_valid(P)
AND at_least_one_required_verifier_accepts(P)
AND residuals_preserved(P)
AND no_authority_bypass(P)
```

Checked to settled:

```text
checked(P)
AND no_blocking_residuals(P)
AND settlement_target_satisfied(P)
AND lineage_closed(P)
AND scope_declared(P)
AND risk_in_envelope(P)
AND integration_policy_passed(P)
AND phase_baseline_residual_gates_pass_if_phase_claim(P)
```

For v1, residual waivers are not implemented. Settlement fails closed.

## Non-Claims

CCR does not detect real ASI, create real ASI, update model weights, self-modify
models, grant execution authority, bypass safety, or convert provider output
into settled capability by itself.
