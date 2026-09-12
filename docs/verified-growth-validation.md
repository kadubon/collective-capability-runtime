# Verified growth implementation and release validation

Source baseline: `4f6e22daeb653fa93e860933b12d57a846e30d9f` (main).
At preflight, the checkout was clean, no PRs were open, GitHub and public PyPI
reported 1.7.0, and 1.8.0 was unused. The existing Wiki is present. No branch
rulesets, main protection, or PyPI environment reviewers were configured at
inspection; release-time policy must be inspected again.

| Requirement | Existing mechanism | Additive implementation / validation |
|---|---|---|
| M1 evidence and lineage | Signed optimizer results, packet eligibility, capital witnesses | Separate service journal, receiver qualification, lifecycle replay and conservation tests |
| M2 productive allocation | v1 epsilon-greedy, fenced trials, resource accounts | Opt-in finite bundles, exact arithmetic, independent checking and oracle tests |
| M3 reuse and interchange | Token candidate imports, mission scopes, provider evidence | Explicit receiver/mission grants, bounded evidence envelopes and tampering tests |
| M4 runtime and release | ControlStore, authenticated API, CI, Trusted Publishing | SQLite/PostgreSQL integration, packaged offline scenarios, build/install receipts |

The v1 optimizer, canonical signature payload and evaluation meanings remain
the compatibility baseline. Existing capital/token imports do not supply
receiver-specific verified service accounting and are not treated as such.

## Qualification status

Pre-publication source qualification on Windows/Python 3.14 used frozen
dependencies. The clean baseline had 217 passed and five PostgreSQL skips.
The additive full regression has 265 passed and six environment-dependent
skips; the growth-specific PostgreSQL case is included in Linux CI with a
disposable PostgreSQL 16 service. No local PostgreSQL execution is claimed.

The existing 90% safety-critical **statement** gate is preserved and includes
all new optimizer modules. Its final local run passed at 90.56% (2,589/2,859).
A separate optimizer/control branch-collecting run passed 85 tests with five
PostgreSQL skips: statements 90.45% (1,544/1,707), branches 79.18% (635/802),
and combined coverage 86.85%. The selections differ, so the combined metric is
not the repository's broader statement gate.
No statement-only run is described as branch coverage.

Ruff formatting/lint, mypy (135 source files), compilation, the 180-entry schema
registry, repository audit, source/wheel/sdist publication audit, build and
Twine metadata checks passed. Existing security scans found no blocking source
or distribution findings. Dependency auditing found an advisory in the previous
cryptography 49 lock; the optimizer extra now requires cryptography 50 and the
lock resolves 50.0.1. A subsequent pip-audit found no known vulnerabilities in
resolved dependencies. The unpublished local CCR version was skipped by that
advisory lookup; this is not a proof of absence of vulnerabilities.

The supported PIC v1.0.0 source is pinned to
`83ca785e5ab79fe8c546c92474b4b03321fdc04c`. Source compatibility audit passed;
the optional PIC executable/package was not run. Companion schemas are pinned
separately in the [interchange guide](verified-growth-interchange.md).

## Reproducible software evidence

`uv sync --frozen --all-extras` precedes the commands in `.github/workflows/ci.yml`.
The same safety-gate test/module selection is used by the release workflow.
Branch coverage is collected with `pytest tests/test_growth.py tests/test_optimizer.py
--cov=ccr.optimizer --cov=ccr.storage.control --cov-branch`.

`ccr optimizer growth-example --json` executes the signed task/lease path and
returns four finite policy references plus verifier-investment and adverse-cost
scenarios. The delayed route records task=4 and research=4 from two distinct
uses of one asset at cost=8; the immediate restriction records 1 and 1 at cost=2.
The reoptimized permitted reuse route reaches the same 4/4 outcome, preserving
the null comparison. Legacy binary artifact reward is reported as a different
metric. These references use the same declared finite task/evaluator/budget
contract and are descriptive, not an empirical treatment-effect estimate.

Independent tests cover exact arithmetic and catalogue permutation with
Hypothesis, forged plans, receiver/source/signature tampering, multi-parent
conservation, expiry/revalidation, training/holdout isolation, outbox rollback,
concurrent quota/reservation/ingest and OIDC/DPoP-authenticated API transitions.
An approved mocked dispatch times out after simulated send: restart retains
reservation, a second send is refused, and signed reconciliation releases only
unstarted work. No production provider is contacted.

## Publication receipts

This source record precedes publication. Push, current-head CI, merge, Wiki
push, release creation, artifact attachment, Trusted Publishing and exact-version
public-index installation are separate operations. Their inspected run/commit
and hash receipts will be appended in a follow-up documentation commit, without
changing the tagged distributions or pretending that post-publication evidence
was part of their original build.

No external empirical collective-intelligence acceleration experiment was
performed. Deterministic software scenarios cannot establish causal endogenous
capability reproduction, AGI/ASI, indefinite growth, or correctness outside
the declared evidence and model boundaries.
