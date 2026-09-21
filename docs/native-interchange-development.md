# Native interchange development status

This branch is an **unfinished Phase 2 implementation**, not CCR 1.9.0 and not
a qualified release candidate. Package version remains 1.8.0. Do not merge or
publish this branch as completion of the Phase 2 specification.

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
The explicit native CLI, three registered owned wire schemas, pinned installed
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

The latest local continuation run passed 51 tests, including offline socket guards,
malformed input, exact conversion, native tampering, selected faults and all four
runtime scenarios plus an integrated same-run loop. The ordinary base environment intentionally skips native
tests without this explicit setup; those skips are not native conformance.

Fixture generation uses installed pinned producer APIs. CPCF inputs are generated
with its maintained CLI, and its checker is consumed only through the maintained
`growth_control` facade. `scripts/generate_native_fixtures.py` documents the setup
command. No companion repository is modified.

## Qualification remains incomplete

The latest continuation selection measured 986/1030 native-module
statements (95.73%) and 421/462 branches (91.13%), including every native module.
The aggregate new-module 95%/90% gate passed. The earlier `b1b5cfe` gate passed
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

## Required work before release

1. Complete contract registration qualification: explicit clocks, semantic action/effect
   mappings and typed physical-cost allocation. Audit all fields against the
   specification rather than assuming retained JSON is enforced semantics.
2. Finish ALT lifecycle, parent/input/evaluator substitution and cost-identity
   checks. Complete source timing/occupancy and dependency translation checks.
3. Finish VEK predecessor/separation/contingency mappings,
   expiry/dispatch rechecks, and reconciliation of all signed check statuses.
   Unsupported contingent work is currently rejected.
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
