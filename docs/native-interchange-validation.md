# Native interchange 1.9.0 qualification and publication

This is the build-time qualification record for source version 1.9.0. Public
GitHub/PyPI were checked on 2026-09-21 before publication and contained 1.8.0.
Public installation can only be verified after the publication job completes;
the exact distribution checksums and post-publication receipt belong to the
[1.9.0 release record](https://github.com/kadubon/collective-capability-runtime/releases/tag/v1.9.0).

## Supported finite profile

All four paths use existing CCR registration, planning, independent plan checks,
transactional reservations, leases, signed outcomes and historical replay.
Native imports nominate already registered work. They grant no service, receiver
qualification, observed capacity, settlement or execution authority.

| Path | Implemented behavior | Explicit rejection boundary |
| --- | --- | --- |
| ALT 0.5.0 | Fresh native plan/sidecar check; candidate, receiver, mission, context, input, evaluator, quality and physical-cost binding; signed preparation/transfer prerequisites; later reuse and signed withdrawal | Unmapped dependency lifecycle/inherited history, unsupported refresh, duplicate cost ownership, mismatched task kind/scope, unfunded occupancy or expired source window |
| VEK 1.3.0 | Fresh contract/history/schedule/report checks; consumable cost versus reusable canonical pools; serial execution/cleanup windows; signed positive/negative/timeout/invalid/inconclusive/pending/censored states and subsequent prerequisite eligibility | Unsafe parallel serialization, historical events without a cutoff map, unmapped verifier separation, ambiguous or contradictory prerequisites; model forecasts never become observed service |
| CAIT 0.2.0 | Exact signed CCR source export; real analyzer and independent report check; per-event completeness plus totals; idempotent feedback; qualified withdrawal enables funded review without adding credit | Missing or substituted history, wrong arm/cutoff/terminal commitment, unsupported lineage/lifecycle, fractional or out-of-range source clock; partial output cannot provide positive support |
| CPCF 1.0.1 | Maintained public facade; fresh observable root check; frozen task/action/capability/verifier mapping; signed observation history and replanning; source elapsed time and evidence expiry | Hidden or unregistered observation branch, stale source/history, inherited evidence, unmapped host preconditions/effects/obligations or interval reservations; continuation guarantee remains false |

Each actionable native source has a preregistered affine UTC clock. Exact
rational conversion rounds earliest times later and deadlines earlier. Execution
and cleanup have separate endpoints. Admission, reservation, lease, signed result
receipt and historical replay enforce those bounds. Tests include a result whose
observation falls in cleanup time and a trusted verifier outside the registered
CPCF check scope; neither can be promoted by rewriting derived journal flags.

The integrated example explicitly regenerates and freshly checks an ALT serial
problem with cleanup gaps and a VEK serial problem. It uses simulated elapsed UTC
over real database transactions, not wall-clock performance measurements. Eight
signed synthetic attempts retain 16 actual synthetic cost units, four service
events and one historical asset; withdrawal plus CAIT reconciliation changes the
next eligible allocation to review. Declared native cost bounds and signed actual
costs remain separate views. No empirical acceleration or causal attribution is
asserted.

## Measured local evidence

- Pinned Python 3.14 native selection: 85 passed, no skips, 160.44 seconds, including
  real SQLite and PostgreSQL contention. All four published native checkers run.
- Native modules: 1,235/1,254 statements (98.48%) and 541/560 branches (96.61%). Every
  module passes 95% statement and 90% branch gates; no exclusions or lowered gates.
- Base regression: 299 passed, 57 optional-environment skips, one existing
  Starlette deprecation warning. Skips are not counted as native conformance.
- Formatting, lint, strict typing, compilation, repository audit and the
  184-entry schema registry pass. All 180 prior schema entries and the original
  four native fixture document byte strings are unchanged.
- Independent tests reconstruct mappings from original documents and use tiny
  interval/accounting oracles, selected false-acceptance faults, signed-envelope
  substitutions, journal rollback and revision contention. These are selected
  faults, not a claim of exhaustive mutation qualification.

The ordinary Python >=3.10 dependency surface is unchanged. The optional native
qualification environment uses hash-locked packages and verifies installed
producer source/schema/metadata bytes. Companion repositories and the website
are not modified. OAWM completion is neither assumed nor required.

## Publication record

Implementation and source-bound validation are available in
[PR #7](https://github.com/kadubon/collective-capability-runtime/pull/7).
The maintainer reviewed and approved the implementation at `cd847fa` on
2026-09-22 JST. Final exact-head checks still govern merge; the approval does not
waive a failing check. Normal repository and environment policy applies. No prior
CPCF exception is used.

The release sequence is merge, tag, GitHub Release, protected Trusted Publishing
and public-PyPI no-cache installation verification. The existing workflow builds once and
passes those same wheel/sdist bytes to publication and release assets. Release
completion requires matching their SHA-256 hashes to public PyPI and executing
legacy and new offline paths from a fresh installed environment outside checkout.
An existing Wiki is maintained separately; canonical repository documents govern.
