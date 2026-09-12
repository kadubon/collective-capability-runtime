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

Post-publication verification was completed on 2026-09-13 (Asia/Tokyo).
This section and the [machine-readable receipt](verified-growth-release-1.8.0.json)
are follow-up documentation, not part of the original tagged build.

| Operation | Inspected status / evidence |
|---|---|
| Implementation / push | Complete: [PR #5](https://github.com/kadubon/collective-capability-runtime/pull/5), branch `codex/ccr-verified-growth-1.8.0` |
| CI | Passed: [PR CI](https://github.com/kadubon/collective-capability-runtime/actions/runs/34696411458), [merged-main CI](https://github.com/kadubon/collective-capability-runtime/actions/runs/34724947584); Python 3.10–3.14, three operating systems, PIC and PostgreSQL checks |
| Security review | Passed: GitGuardian returned `No secrets detected` after owner-authorized individual classification of incident `37045954` as a disposable test credential; no global detector or check was disabled |
| Merge | `1591e88e3b05f9b5fb06b2d0c749aad8bc0909be`, using normal merge without administrator override; tree `c472b3f18d2b98957ce9344798c5b0c375995ebc` exactly matches the tested PR tree |
| Documentation / Wiki | Canonical guides and agent instructions merged; [existing Wiki](https://github.com/kadubon/collective-capability-runtime/wiki/Verified-Growth) updated through its separate repository |
| Tag / GitHub Release | [v1.8.0](https://github.com/kadubon/collective-capability-runtime/releases/tag/v1.8.0), remote tag resolves to the merge commit above |
| Build / artifact attachment | Passed in [Publish run 34724978585, attempt 1](https://github.com/kadubon/collective-capability-runtime/actions/runs/34724978585); the single built wheel/sdist and SHA256SUMS are attached to the Release |
| Trusted Publishing / PyPI | Passed using the existing workflow and `pypi` environment; [public PyPI 1.8.0](https://pypi.org/project/collective-capability-runtime/1.8.0/) |
| Public-index verification | Passed: fresh Windows/Python 3.13.5 environment outside checkout; base, optimizer and distributed stages installed with cache disabled from the public index, with pip installation reports |
| Provenance | Both distribution attestations passed `pypi-attestations verify pypi --repository https://github.com/kadubon/collective-capability-runtime`; certificate bindings match repository, workflow, tag, source commit, publication run/attempt and `pypi` environment |

The PR and release-build full suites each passed 270 tests with one
non-applicable PostgreSQL-DSN test skipped; the separate PostgreSQL worker job
passed. The release safety-critical statement gate passed at 91.01%. These
results supplement, rather than replace, the separately scoped local statement
and branch figures above. Stalled obsolete CI runs were cancelled and are not
counted as successful qualification.

The clean environment had sanitized index/PYTHONPATH settings and
`PIP_CONFIG_FILE` set to the platform null device. Its initial installation was:

```sh
python -m pip install --index-url https://pypi.org/simple --no-cache-dir --no-input --report base-install.json collective-capability-runtime==1.8.0
```

The optimizer and distributed extras were then installed in separate stages
using the same public-index/cache-disabled flags. Every stage passed version,
module-origin and `pip check` validation. Base `agent explain`, isolated
storage/mission smoke, distributed imports, and the complete packaged legacy
and growth offline examples passed. The examples reported no provider network
calls. Installed PostgreSQL execution was not claimed; disposable PostgreSQL
correctness is supported by CI and release-build integration evidence.

| Distribution | SHA-256 |
|---|---|
| `collective_capability_runtime-1.8.0-py3-none-any.whl` | `97b2f3dc1f675c78246c362d211b71452b721b001e25dd2711263f34874f8b25` |
| `collective_capability_runtime-1.8.0.tar.gz` | `9b752077917b608295d159f5a24fc5f729aaebf5b4beffdd55781648da4d8ae2` |

Downloaded bytes agree with public PyPI metadata, the pip wheel installation
report, GitHub Release assets and the build's SHA256SUMS. Both Sigstore
attestations authenticate these hashes. One initial concurrent verifier call
hit a local TUF-cache race; the sequential sdist verification succeeded. This
was a verification-tool retry, not a rebuild or publication retry. The tagged
source and published distributions remain unchanged.

No external empirical collective-intelligence acceleration experiment was performed for this release. The implementation supports evidence-bound coordination, bounded planning, qualified reuse, and reproducible software-level testing. It does not establish causal endogenous capability reproduction, AGI/ASI, indefinite growth, or correctness outside the declared evidence and model boundaries.
