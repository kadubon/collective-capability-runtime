# PIC Interop Examples

Related optional PIC verifier:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

These examples model representative PIC v0.5.0-compatible reports for CCR import tests.
They are not execution logs. CCR imports `safe_commands` as task hints only,
keeps `settled=false` or `settled=true` as provider evidence, and still requires
CCR phase, baseline, residual, and promotion gates before any CCR settlement.

## First-time agent guide

Purpose: use these files to test PIC-compatible report normalization without
requiring PIC to be installed or executed.

First commands:

```bash
ccr provider health --provider pic --json
ccr provider import --provider pic --report examples/pic_interop/pic_v050_agent_check_report.json --json
ccr integrate --report examples/pic_interop/pic_import_example.json --json
```

Safe boundary: importing a report reads local JSON and may create local residuals
or task hints, but it never executes PIC commands.

Expected outputs: normalized reports preserve accepted, workflow usable,
settled, candidate-only reasons, blockers, missing obligations, bottlenecks,
phase gaps, and `safe_commands`.

Failure/residual handling: provider-missing and blocker examples should remain
visible as residual-ready state or open residuals.

P2 safe commands:

```bash
ccr residual market --json
ccr residual market --mission <mission_id> --json
ccr residual bounty --residual <residual_id> --mission <mission_id> --emit task --json
ccr workbench export --mission <mission_id> --format static-html --out site/ --json
ccr operation replay-manifest --dispatch-report dispatch.json --observation observation.json --out replay.json --json
ccr operation verify-observation --manifest replay.json --verifier verifier.json --json
ccr conformance parity --ccr-report ccr.json --pic-report pic.json --json
ccr provider registry-validate --file provider-registry.json --json
```

PIC interop evidence remains evidence-only in these commands. It does not grant
CCR settlement, dispatch authority, or physical outcome proof.

Provider import: both `provider import --provider pic` and legacy `integrate`
use the same CCR settlement boundary.

Phase formation cycle: imported PIC evidence can support packet checking, but
CCR still runs graph, observe, threshold, compare, and certify locally.

What not to claim: PIC representative reports do not grant CCR
settlement, real ASI proof, or execution authority.

Useful local checks:

```bash
ccr provider health --provider pic --json
ccr audit pic --pic-root <PIC_ROOT> --json
```
