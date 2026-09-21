# Phase 2 implementation register

Baseline inspected: CCR `3b4702454f732c7a0a9f30d87483384dc8a281eb`, source,
GitHub Release and public PyPI 1.8.0 (2026-09-21). Proposed version: 1.9.0;
no version has been changed or publication initiated.

Current implementation and measured evidence are tracked in
[Native interchange development](native-interchange-development.md). The rows
below describe milestone completion, not whether any code has been written:
all four native checkers, a same-run integrated example, signed observation
replanning, SQLite/PostgreSQL contention and installed-wheel examples now execute.
The 70-test native selection passes 95% statement/90% branch gates for every
native module, with no excluded new module.
Contract-level release qualification remains incomplete, particularly source-clock
and action/effect translation. Passing CI is not a waiver for these gaps.

| Requirement | Existing source and behavior | Required change and verification | Status |
| --- | --- | --- | --- |
| P2-A registration | Closed native schemas, raw identities, installed source/schema hashes and immutable bindings now exist | Complete source-clock/action/effect scope qualification | Partial |
| ALT 0.5 | `growth_interchange.py` pins 0.4 tokens; `growth_runtime.py` already requires signed transfer evidence | Check native source reconstruction and sidecar; bind preregistered work; scoped qualification and withdrawal scenarios | Pending |
| VEK 1.3 | Growth declares verifier demand; capacity reports have no admission route | Check native schedule, preserve pool/budget separation, reject unsafe serialization; signed negative/unknown work reconciliation | Pending |
| CAIT 0.2 | Legacy export explicitly lacks native source accounting | Source-bound forward/backward conversion, native analyzer/checker, no duplicate reward, qualified loss changes later eligibility | Pending |
| CPCF 1.0.1 | No growth-control proposal route | Maintained facade only; checked observable first action, current revision and finite action mapping, preserve continuation obligations | Pending |
| Runtime | Existing aggregate plus native admission; real SQLite/PostgreSQL four-worker admission/apply contention passes | Broaden source expiry and crash-boundary cases | Partial |
| Qualification | Existing 90% gate plus isolated pinned native 95%/90% gates pass on `b1b5cfe`; Python 3.10–3.14/platform/PIC jobs pass | Qualify remaining semantics and rerun on eventual final release source | Partial |
| Publication | Draft PR #7 pushed; existing Wiki development guide published at `e92e77e`; build-once Trusted Publishing retained | Complete qualification, normal review/merge, tag/release, artifact hashes and public no-cache install | Pending |

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
