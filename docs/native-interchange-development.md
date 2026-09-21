# Native interchange development history

The 1.9.0 source includes mandatory source clocks,
historical result validity and CPCF task/capability/verifier scope are implemented
and covered by the 85-test pinned native selection. The supported finite subset,
rejection boundaries and outstanding publication gates are recorded in
[Native interchange validation](native-interchange-validation.md).

The sections below preserve earlier development evidence and the work list at
that time. Their counts, version statements and open implementation items are
historical; the validation record governs current status. They are not a release
or public-install verification record.

## Implemented and exercised

The implementation uses `ControlStore` and the existing optimizer aggregate,
planner, plan checker, reservations, leases and signed growth outcomes. Legacy
interchange remains separate. New registration currently permits synthetic
training runs only. Native source inspection and checking do not initialize
stores or grant service, receiver eligibility, observed capacity or authority.

The new Python modules provide bounded byte parsing and exact conversion,
fixed optional native checkers, projection and independently implemented
translation checks, explicit registration/staging/admission, and source-bound
CAIT export/check/reconciliation. Native tools execute before database locks.
The explicit native CLI, four registered owned wire schemas, pinned installed
source/schema hashes and an installed example interface are now implemented.
There is no new HTTP endpoint. See [the current guide](native-interchange.md).

Actual released native packages used in a separate Python 3.14 environment:

| Producer | Native version | Exercised runtime behavior |
| --- | --- | --- |
| ALT | 0.5.0 | Checked source/plan/task sidecar gates six registered actions; formation and transfer signed results qualify the receiver; four distinct service results retain one asset |
| VEK | 1.3.0 | A newly explicit finite serial schedule enters diagnostic work; a signed negative result evaluates the check with zero capability service credit and permits the next work item |
| CAIT | 0.2.0 | Signed CCR formation, use, cost and withdrawal sources enter the native analyzer/checker; reconciliation preserves eight cost units, four task/research units and one historical asset, and enables registered repair after withdrawal; duplicate reconciliation changes no totals |
| CPCF | 1.0.1 | Fresh public-facade checking admits the observable root; signed CCR status-to-symbol mappings support subsequent native replanning; old or mismatched histories fail |

These are finite synthetic software tests. They are not operational observations,
empirical acceleration measurements, identified causal effects, execution
permission or settlement. CPCF continuation guarantees are not transferred.
Native CAIT authentication remains unestablished even when CCR separately checks
its own original signatures.

Generated fixture source documents are retained as original JSON strings in
`examples/native_interchange`. `artifacts.json` records public producer artifact
URLs and SHA-256 values independently checked after download. `installed-pins.json`
binds released Python/schema/metadata files, checked freshly before native calls.
`source-tags.json` records inspected immutable tag commits. The separate
`scripts/requirements-native.lock` pins transitive dependencies with hashes.

## Reproducing the current development tests

Use a disposable environment **outside the checkout**. The release hygiene audit
scans source-tree content, including ignored nested environments. Install CCR's
checkout there with development test dependencies, plus the exact producer
artifacts recorded in `examples/native_interchange/artifacts.json`. ALT is a
GitHub Release distribution; it is not assumed to be on PyPI.

Set `CCR_NATIVE_CONFORMANCE=1`, then run:

```text
python -m pytest tests/test_native_interchange.py tests/test_native_transactions.py tests/test_native_cli.py tests/test_native_projection_faults.py tests/test_native_accounting_faults.py
python -m ccr optimizer native example --json
```

The latest local continuation run passed 70 tests, including offline socket guards,
malformed input, exact conversion, native tampering, selected faults and all four
runtime scenarios plus an integrated same-run loop. The ordinary base environment intentionally skips native
tests without this explicit setup; those skips are not native conformance.

Fixture generation uses installed pinned producer APIs. CPCF inputs are generated
with its maintained CLI, and its checker is consumed only through the maintained
`growth_control` facade. `scripts/generate_native_fixtures.py` documents the setup
command. No companion repository is modified.

## Qualification remains incomplete

The latest continuation selection measured 1019/1038 native-module
statements (98.32%) and 445/462 branches (96.27%), including every native module.
Each native module independently meets 95% statements and 90% branches; the gate
now enforces those per-module thresholds as well as the aggregate. The earlier `b1b5cfe` gate passed
at 95.61%/90.85% locally and in CI. Further changes require a fresh
measurement; there is no exclusion or waiver for a native module.

The unchanged repository safety-critical CI gate also failed at **74.35%** on
development commit `4432e9a`, in
[CI run 35600109406](https://github.com/kadubon/collective-capability-runtime/actions/runs/35600109406).
That test selection does not yet include the new native suite/dependency setup.
The gate remains at 90%. Python/platform/PIC and the existing PostgreSQL smoke
jobs passed in that run; the PostgreSQL job does not exercise native admission.
That historical failure was resolved on `b1b5cfe` by measuring the isolated native
suite before enforcing the same 90% safety threshold. The separate native
statement/branch gate is also enforced. All jobs passed in
[CI run 35604173119](https://github.com/kadubon/collective-capability-runtime/actions/runs/35604173119).
Later source changes require fresh CI evidence and do not erase earlier failures.

The continuation base rerun passed **290 tests with 27 skips**. An earlier release-audit
failure was caused by the disposable native environment being inside the
checkout; moving that environment outside the checkout corrected the issue
without changing the audit. Formatting, lint, strict source typing and native
tests passed after the final source-bound-obligation correction. Compilation,
repository audit and the existing schema registry audit also passed during
development. The whole qualification must be rerun on the eventual final source.

PostgreSQL 16 was subsequently installed in WSL and a disposable loopback-only
cluster was created. Actual SQLite and PostgreSQL four-worker native admission
and task-creation contention passed: one admission and one task, including a
fresh ControlStore instance reading the authoritative state. Selected rollback
tests also passed. Broader PostgreSQL fault qualification remains incomplete.

A locally built development wheel was installed in a separate hash-locked
environment outside the checkout. Both the new native example and legacy
growth example passed there; `uv pip check` reported compatible dependencies.
This was a local development build retaining version 1.8.0, not public PyPI
publication or verification of a released 1.9.0 artifact.

Additional CLI round-trip testing found that embedded legacy fractional packet
fields were rejected by the strict native quantity parser. Accounting exports
now preserve canonical CCR source rows as strings, compare them to authenticated
original history, and use a separately registered closed export schema. The
real CLI export/feedback/reconcile regression test passes without relaxing the
native rational/integer parser or changing legacy signature rules.

## Additional signed-prerequisite and validity qualification

The latest native selection passed **70 tests in 127.13 seconds**, with actual
SQLite and PostgreSQL execution and no skips. Native coverage was 1,052/1,070
statements (98.32%) and 464/482 branches (96.27%); every native module separately
passed the 95% statement / 90% branch gates. No threshold or exclusion changed.

Finite VEK predecessor completion and positive/negative activation now change
subsequent CCR eligibility using authenticated outcomes from the same registered
source contract. Fifteen status/condition combinations exercise positive,
negative, timeout, inconclusive and invalid outcomes. Native forecast branches
do not discharge these prerequisites. Duplicate source-action registrations,
unmapped prerequisites and contradictory conditions fail closed.

Host validity now includes execution and cleanup before staging/admission and
before reservation/lease. A selected clock advance after reservation rejects the
lease without dropping the reservation on both database backends. Event and
receipt times are checked when admitting results; expired attempts retain their
costs but create no asset or service credit. Historical replay checks the
original receipt time and rejects promotion by rehashing derived journal flags.
These checks do not substitute for the remaining producer-clock/UTC mapping.

## Required work before release

1. Complete contract registration qualification: explicit clocks, semantic action/effect
   mappings and typed physical-cost allocation. Audit all fields against the
   specification rather than assuming retained JSON is enforced semantics.
2. Finish ALT lifecycle, parent/input/evaluator substitution and cost-identity
   checks. Complete source timing/occupancy and dependency translation checks.
3. Qualify VEK source clocks and independent verifier separation. Finite,
   uniquely mapped predecessor completion and positive/negative activation now
   use qualified signed CCR results. Unmapped/contradictory conditions and
   verifier separation without a host mapping are rejected. Host expiry is
   rechecked through reservation, lease, result receipt and historical replay.
4. Finish CAIT incomplete/negative-history handling and independent per-event
   reconciliation tests. Current export supports a bounded root-asset subset;
   unsupported formation/lifecycle/use records retain obligations. Complete the
   cutoff and evidence-period audit. Feedback storage is now bounded.
5. Qualify CPCF observation mapping against additional ambiguous/unsupported
   outcomes and effect/clock scopes. Signed-status replanning now works.
6. Broaden the implemented integrated loop and tiny accounting oracle with
   systematic selected faults, holdout/resource-alias controls, and additional
   PostgreSQL crash boundaries. The existing example is runtime behavior.
7. Complete API/discovery/installed-reference integration, documentation and
   machine-readable discovery. Extend CI and the existing release workflow with
   pinned native qualification and the requested coverage gates, preserving all
   existing checks and build-once publication behavior.
8. Run all final qualification, review, merge, existing Wiki update, release and
   protected Trusted Publishing steps. Verify exact released wheel/sdist hashes
   and fresh no-cache public-PyPI installed offline paths before claiming release.

No tag, release or PyPI publication has been initiated. The existing Wiki was
updated at commit `e92e77e` with a development page and explicit release gaps;
it does not announce 1.9.0. No earlier CPCF qualification waiver is used.
