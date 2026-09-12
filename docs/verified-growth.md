# Verified growth: finite service and reuse accounting

The explicit `verified_growth_v1` policy uses `ccr.growth_profile.v1`, wrapping
an unchanged v1 optimizer configuration and a closed growth registration.
Existing v1 configurations, signed bytes, epsilon-greedy allocation and binary
holdout inference retain their original meanings. Install the `optimizer`
extra for signed results and `distributed` for PostgreSQL/API operation.

```text
ccr optimizer growth-example --json
ccr --root runtime optimizer init --mission mission:source --config profile.json
ccr --root runtime optimizer plan --run <id> --json
ccr --root runtime optimizer check-plan --run <id> --file plan.json
ccr --root runtime optimizer step --run <id> --apply --expected-revision <n>
ccr --root runtime optimizer claim --run <id> --trial <trial> --worker <worker>
ccr --root runtime optimizer ingest --run <id> --file growth-result.json
ccr --root runtime optimizer growth-ledger --run <id>
ccr --root runtime optimizer freeze --run <id>
ccr --root runtime optimizer replay --run <id>
```

The packaged offline example creates a temporary synthetic store and ephemeral
signing keys, forms a workflow through the workcell protocol, uses the existing
fenced worker path, independently checks finite arithmetic, qualifies a second
receiver, records two uses of one asset, freezes allocation, and evaluates both
arms. It contacts no providers. No reusable signing secret is distributed.
It also executes the unchanged legacy policy, an immediate-output restriction,
a supported verifier investment, and a cost-dominates-formation control.
The fixture public key in `examples/verified_growth/profile.json` is inert;
replace it with an independently held evaluator key for a real registration.

## Registration and finite scope

Register the study, empty checkpoint digest, tasks/inputs, receiver missions and
contexts, evaluator/protocol versions, service quality, separate task/research
targets and units, costs, finite observation/attribution windows, asset digests,
versions, parent coalitions, external inputs, transfer grants and expiry.
The initial supported checkpoint is empty evidence; inherited development is
not granted free credit. Reuse of preexisting material must pay for a new
registered formation/validation trial. A study identifier cannot be reused to
reset its accounting, even with changed configuration.

The implemented search domain is at most 64 actions, 128 registered bundles,
16 explicit joint scenarios, eight steps per bundle and 86,400 seconds per
horizon. The candidate limit bounds actual catalogue enumeration. A truncated
search may return a checked incumbent but cannot establish nonexistence or
global optimality. Empty compatible model sets mean inconsistency.

The reference policy uses a common sequential bundle in every scenario. An
unsuccessful step stops productive descendants; all worst-case cleanup is
funded. Only the immediate step becomes a task. Later steps require actual
qualified evidence and are replanned after ingestion. The objective is the
worst-scenario minimum normalized task/research attainment, followed by the
registered lexicographic order of typed costs, latency, then identifier.
Diagnostic/repair actions can be selected without a positive service forecast;
unknown effects never become successes. There is no claim of indefinite
feasibility or general policy optimality.

## Accounting and lineage

An immutable, chained journal inside the authoritative optimizer aggregate
records reservations, signed outcome envelopes, release of provably unstarted
work, lifecycle changes and imported evidence. ControlStore commits the
aggregate and its immutable outbox snapshot in one SQLite/PostgreSQL transaction.
`export` produces audit copies; PostgreSQL never admits worker-local mirrors.

One study/arm/task/input/receiver/protocol delivery earns service credit once.
The same content on a distinct registered service task can earn another service
event, while the asset count remains one. Baseline and candidate have separate
asset eligibility, outcomes and trial state. Training expense is included in
candidate evaluation expense; those accounts overlap and must not be summed.

Every cost dimension uses nonnegative integers in declared base units, with a
maximum of 2^53 at the legacy numeric boundary. Fractional input is rejected;
operators must convert to finer integer units, conservatively rounding costs
up before registration. Money, tokens, time and risk are never subtracted from
a service scalar. Each action's actual total includes production, communication,
validation, verification and control; cleanup has an additional explicit upper
bound. Asset count, lineage depth and repeated deliveries are not capital.

Parents are a coalition. There is no automatic credit to ancestors, semantic
equivalence claim, reproduction number or causal attribution. Reports disclose
overlapping task/research measurements. Pending reuse stays pending until the
registered window ends, after which unobserved reuse is censored. Neither state
means demonstrated success or failure. Failed and inconclusive observations
retain costs and reasons.

## Receiver qualification and lifecycle

Asset existence and permission to attempt transfer do not qualify a receiver.
A signed, packet-eligible `transfer_validation` action qualifies only its
registered receiver/context after source validity and explicit cross-mission
scope checks. A later independently signed service observation establishes use.
No shared-database read implicitly grants cross-mission permission.

`optimizer reuse --file lifecycle.json` admits a signed withdrawal, quarantine,
expiry or correction. It preserves history and invalidates dependent future
uses. New claims and dispatch recheck prerequisite eligibility. Revalidation
requires a distinct registered `revalidation` task and new independently
checked evidence; a lifecycle flag alone cannot restore eligibility. Immutable
expiry is not extended. Repair hints remain visible when no funded registered
repair is available.

Growth envelopes bind an unchanged, separately signed v1 result plus receiver,
context, source/version, parent coalition, evidence mode and evaluator fields
under another signature. A growth run rejects bare v1 result ingestion.
Existing packet eligibility, residual, approval, lease and fencing predicates
remain mandatory. Signatures authenticate statements; they do not prove
external truth or independence of evaluator errors.

## Verification and resource control

Verifier stages register domains, quality, freshness, offered work units per
second, exposure groups and dependence. Work arrives at each sequential step;
the declared duration must fund completion before its deadline. Unknown service
cannot support generation. This bounded sequential service assumption is not a
general queueing or burst-distribution theorem.
Reports separate each arrival, registered work, age, deadline, authenticated
completion, unfinished trials, funded continuation and repair obligations.
Measured completed work stays unknown when only a completion record exists.

Verifier investment can forecast later service support, but cannot change
observed service until an independently signed, packet-eligible measurement is
admitted. That support is tied to an unexpired prerequisite asset; invalidation
removes it. Signing keys or multiple workers never multiply reliability.

Registration transactionally allocates an explicitly assigned budget and
concurrent-capacity quota from a declared shared pool. The entire run quota
remains allocated, so separate runs cannot double-book it. Operators must map
physical resources to the same pool; different invented pool names cannot
prove physical disjointness. This conservative profile serializes each run and
does not introduce a new scheduler or database authority.

Before task creation, all bundle costs and cleanup are reserved and the
independent checker recomputes dependency activation, service, time, capacity,
objective and reservations. Applying recomputes under the database lock and
checks revision. Unknown dispatch retains all reservations and blocks new work;
it is never automatically resent. Signed reconciliation releases only future
steps that never acquired tasks or dispatches. Stop preserves pending debt.

## Evaluation and limitations

Training observations filter the registered finite joint model set. Freeze
commits that set before holdout. Holdout can update operational eligibility but
cannot fit the policy. The baseline reoptimizes its predeclared permitted bundle
catalogue, including preparation and reuse. Candidate training is charged to its
evaluation envelope. The offline example reports a null comparison when the
restricted baseline has the same useful reuse route.

Service outcomes, coverage, measured verifier support, joint service capacity,
causal gain and statistical improvement remain distinct. Growth v1 supplies no
causal estimator or iid inference over dependent reuse. Its improvement claim
is always inadmissible; a future empirical study needs its own identification,
clustering and uncertainty method. Existing v1 inference remains available only
for its original binary-outcome scope.

See [Interchange](verified-growth-interchange.md) for pinned companion schemas
and [Validation](verified-growth-validation.md) for actual release receipts.

No external empirical collective-intelligence acceleration experiment was
performed for this release. The implementation supports evidence-bound
coordination, bounded planning, qualified reuse, and reproducible software-level
testing. It does not establish causal endogenous capability reproduction,
AGI/ASI, indefinite growth, or correctness outside the declared evidence and
model boundaries.
