# Phase 2 implementation register

Baseline inspected: CCR `3b4702454f732c7a0a9f30d87483384dc8a281eb`, source,
GitHub Release and public PyPI 1.8.0 (2026-09-21). Proposed version: 1.9.0;
the current review candidate now declares 1.9.0. Publication has not started.

Current implementation and measured evidence are tracked in
[Native interchange development](native-interchange-development.md). The rows
below describe milestone completion, not whether any code has been written:
all four native checkers, a same-run integrated example, signed observation
replanning, SQLite/PostgreSQL contention and installed-wheel examples now execute.
The 85-test native selection passes 95% statement/90% branch gates for every
native module, with no excluded new module.
Mandatory source clocks and CPCF task/capability/verifier scope now enforce the
bounded supported contract. See [current validation](native-interchange-validation.md)
for measured evidence and exact unsupported cases. Publication gates remain open.

| Requirement | Existing source and behavior | Required change and verification | Status |
| --- | --- | --- | --- |
| P2-A registration | Closed schemas, raw identity, artifact pins and immutable bindings | Mandatory exact clocks and CPCF scoped task/effect/check binding, independent original-source reconstruction | Implemented; local tests pass |
| ALT 0.5 | Separate from the unchanged 0.4 legacy importer | Fresh native source/sidecar check, funded preparation/transfer, signed receiver qualification and later reuse | Implemented for documented finite subset |
| VEK 1.3 | Verification work through existing CCR actions | Native checks, canonical pool/budget separation, preserved serial windows and signed work-state prerequisites | Implemented for documented finite subset |
| CAIT 0.2 | Original signed CCR source export and feedback | Native analyzer/checker, independent per-event reconciliation, idempotency and qualified loss changing allocation | Implemented for documented root-asset subset |
| CPCF 1.0.1 | Maintained public facade only | Observable first action, signed history replan, frozen scope and native clock/evidence expiry | Implemented; continuation guarantee not transferred |
| Runtime | Existing aggregate/transaction/outbox path | SQLite/PostgreSQL admission/apply contention, selected rollback faults, expiry and lease rechecks | Local tests pass |
| Qualification | Old safety gate retained; every new native module in 95%/90% gate | Local tests pass; exact-candidate CI and installed-artifact checks still required | In progress |
| Publication | PR #7; existing Wiki; build-once Trusted Publishing retained | Review/merge, Wiki refresh, tag/release, exact artifacts and public no-cache install | Pending |

## Inspected authority boundaries

ALT's `reuse/interchange.py` preserves proposals with `host_admission=null`.
VEK's capacity interchange preserves `observed_service=null` and no guaranteed
rate. CAIT's source profile leaves authentication unestablished. CPCF's maintained
public API checks feasibility, not global optimality or execution permission.
CCR remains the authority for local admission and signed-result eligibility.

The existing CCR Wiki is present. GitHub returned no branch rulesets and reported
`main` unprotected at inspection. The existing `pypi` environment returned no
protection rules. These observations do not waive review or authorize changing
repository/environment controls; policy must be rechecked before publication.
