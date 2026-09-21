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
The public CLI, HTTP authorization surface, closed schema registry entries and
installed example interface are **not yet implemented**.

Actual released native packages used in a separate Python 3.14 environment:

| Producer | Native version | Exercised runtime behavior |
| --- | --- | --- |
| ALT | 0.5.0 | Checked source/plan/task sidecar gates six registered actions; formation and transfer signed results qualify the receiver; four distinct service results retain one asset |
| VEK | 1.3.0 | A newly explicit finite serial schedule enters diagnostic work; a signed negative result evaluates the check with zero capability service credit and permits the next work item |
| CAIT | 0.2.0 | Signed CCR formation, use, cost and withdrawal sources enter the native analyzer/checker; reconciliation preserves eight cost units, four task/research units and one historical asset, and enables registered repair after withdrawal; duplicate reconciliation changes no totals |
| CPCF | 1.0.1 | Fresh public-facade checking admits the observable initial recommendation; CCR changes selection from `greedy` to `form`, then uses its existing lease and signed-result path |

These are finite synthetic software tests. They are not operational observations,
empirical acceleration measurements, identified causal effects, execution
permission or settlement. CPCF continuation guarantees are not transferred.
Native CAIT authentication remains unestablished even when CCR separately checks
its own original signatures.

Generated fixture source documents are retained as original JSON strings in
`examples/native_interchange`. `artifacts.json` records public producer artifact
URLs and SHA-256 values independently checked after download. This does not yet
constitute the required full schema/dependency/source-commit pin manifest.

## Reproducing the current development tests

Use a disposable environment **outside the checkout**. The release hygiene audit
scans source-tree content, including ignored nested environments. Install CCR's
checkout there with development test dependencies, plus the exact producer
artifacts recorded in `examples/native_interchange/artifacts.json`. ALT is a
GitHub Release distribution; it is not assumed to be on PyPI.

Set `CCR_NATIVE_CONFORMANCE=1`, then run:

```text
python -m pytest tests/test_native_interchange.py
```

The latest native run passed 31 tests, including offline socket guards, malformed
input, exact conversion, native tampering, SQLite concurrent staging and the
four runtime scenarios. The ordinary base environment intentionally skips native
tests without this explicit setup; those skips are not native conformance.

Fixture generation uses installed pinned producer APIs. CPCF inputs are generated
with its maintained CLI, and its checker is consumed only through the maintained
`growth_control` facade. `scripts/generate_native_fixtures.py` documents the setup
command. No companion repository is modified.

## Qualification remains incomplete

The native test selection measured 541/634 statements (85.33%) and 241/334
branches (72.16%). It does **not** meet the requested 95% statement / 90% branch
thresholds. The combined coverage display was 81%; this is not a statement-coverage result.
Coverage is an open gate, not an exception or waiver.

The full base run initially reported 286 passed, 13 skipped and one release-audit
failure caused by the disposable native environment being inside the checkout.
That environment was moved outside the checkout; the failing package/build/audit
test then passed. The whole suite must be rerun on the eventual final source.
Formatting, lint, strict source typing, compilation, repository audit and the
existing schema registry audit passed before the most recent additions; rerun
all gates after completing the implementation.

No local PostgreSQL service was available: Docker's Linux-engine named pipe was
absent and PostgreSQL tools were not found in WSL. PostgreSQL qualification has
not run; this is not evidence that the PostgreSQL implementation passes. Existing
CI supplies PostgreSQL but has not yet been extended for the new native tests.

## Required work before release

1. Complete contract registration: owned closed schemas, raw schema/dependency
   pins, producer commit identities, explicit clocks, semantic action/effect
   mappings and typed physical-cost allocation. Audit all fields against the
   specification rather than assuming retained JSON is enforced semantics.
2. Finish ALT lifecycle, parent/input/evaluator substitution and cost-identity
   checks. Complete source timing/occupancy and dependency translation checks.
3. Finish VEK predecessor/separation/contingency mappings, work-state distinctions,
   expiry/dispatch rechecks, and reconciliation of all signed check statuses.
   Unsupported contingent work is currently rejected.
4. Finish CAIT incomplete/negative-history handling and independent per-event
   reconciliation tests. Current export supports a bounded root-asset subset;
   unsupported formation/lifecycle/use records retain obligations. Bound feedback
   storage and fully audit cutoff and evidence-period semantics.
5. Implement CPCF observation mapping and subsequent native replanning. The
   current projection rejects nonempty visible histories rather than selecting
   a branch without a signed observation mapping.
6. Add the required integrated two-cycle example, independent tiny mapping oracle,
   systematic selected fault tests, SQLite/PostgreSQL admission/reservation/task
   contention and crash recovery, holdout and resource-alias counterexamples.
7. Complete CLI/API/schema/installed-reference integration, documentation and
   machine-readable discovery. Extend CI and the existing release workflow with
   pinned native qualification and the requested coverage gates, preserving all
   existing checks and build-once publication behavior.
8. Run all final qualification, review, merge, existing Wiki update, release and
   protected Trusted Publishing steps. Verify exact released wheel/sdist hashes
   and fresh no-cache public-PyPI installed offline paths before claiming release.

No tag, release or PyPI publication has been initiated. The existing Wiki has
been inspected but not changed. No earlier CPCF qualification waiver is used.
