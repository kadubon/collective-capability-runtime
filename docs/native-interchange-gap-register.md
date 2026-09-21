# Phase 2 implementation register

Baseline inspected: CCR `3b4702454f732c7a0a9f30d87483384dc8a281eb`, source,
GitHub Release and public PyPI 1.8.0 (2026-09-21). Proposed version: 1.9.0;
no version has been changed or publication initiated.

Current implementation and measured evidence are tracked in
[Native interchange development](native-interchange-development.md). The rows
below describe milestone completion, not whether any code has been written:
all four native checkers and four finite runtime tests now execute, but no
milestone is yet qualified complete.

| Requirement | Existing source and behavior | Required change and verification | Status |
| --- | --- | --- | --- |
| P2-A registration | `optimizer/growth_model.py` fixes the finite catalogue; `growth_interchange.py` admits only legacy evidence | Separate closed registration and raw byte identities, bounded parsing, independent checking, revision/idempotency tests | Pending |
| ALT 0.5 | `growth_interchange.py` pins 0.4 tokens; `growth_runtime.py` already requires signed transfer evidence | Check native source reconstruction and sidecar; bind preregistered work; scoped qualification and withdrawal scenarios | Pending |
| VEK 1.3 | Growth declares verifier demand; capacity reports have no admission route | Check native schedule, preserve pool/budget separation, reject unsafe serialization; signed negative/unknown work reconciliation | Pending |
| CAIT 0.2 | Legacy export explicitly lacks native source accounting | Source-bound forward/backward conversion, native analyzer/checker, no duplicate reward, qualified loss changes later eligibility | Pending |
| CPCF 1.0.1 | No growth-control proposal route | Maintained facade only; checked observable first action, current revision and finite action mapping, preserve continuation obligations | Pending |
| Runtime | `engine.py`, `growth_runtime.py`, `storage/control.py` own task/result/reservation/outbox transactions | Extend existing aggregate; SQLite/PostgreSQL contention and fault recovery | Pending |
| Qualification | CI includes 90% critical statement gate, Python 3.10–3.14, platforms and PIC | Preserve gates, add native conformance and 95% statement/90% branch gates, selected faults and installed offline checks | Pending |
| Publication | `.github/workflows/workflow.yml` builds once and passes artifacts to PyPI/release assets | Normal PR/merge, existing Wiki, release, exact artifact hashes and public no-cache install | Pending |

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
