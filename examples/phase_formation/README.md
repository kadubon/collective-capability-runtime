# CCR Phase Formation Example

Related optional PIC verifier:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

This directory is a runnable CCR runtime root for protocol-relative ASI-proxy
phase formation diagnostics.

It contains two checked packets with an execution-available path witness and one
candidate packet that remains diagnostic-only. The candidate packet demonstrates
that raw or duplicate volume does not improve positive phase contribution.

## First-time agent guide

Purpose: use this directory as a complete local phase-formation runtime root
with packets, threshold, baseline, and mock provider reports.

First commands:

```bash
ccr --root examples/phase_formation phase graph --json
ccr --root examples/phase_formation phase observe --json
ccr --root examples/phase_formation phase form --profile development --json
```

Safe boundary: these examples run local CCR commands and write local runtime
artifacts; provider reports are imported as files and `safe_commands` are not
executed.

Expected outputs: the effective graph excludes the duplicate candidate packet
from positive contribution, the observation records zero executed paths, and
the certificate candidate keeps `settled=false`.

Failure/residual handling: if thresholds fail, `phase form` creates deterministic
repair tasks and preserves failed components instead of hiding them.

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

These commands are local diagnostics or local task routing only. They do not
dispatch providers, prove physical outcomes, or settle CCR.

Provider import: the HTTP and PIC-like reports exercise import semantics only;
they are not proof that a provider executed anything.

Phase formation cycle: agents can edit or add packets, import verifier reports,
run `phase form`, inspect generated tasks, and iterate until blockers are
resolved.

What not to claim: this example does not prove real ASI, physical truth,
executed work, or settlement from candidate-only volume.

Run:

```bash
uv run ccr --root examples/phase_formation phase graph --json
uv run ccr --root examples/phase_formation phase observe --json
uv run ccr --root examples/phase_formation phase threshold --file examples/phase_formation/threshold.json --json
uv run ccr --root examples/phase_formation phase form --profile development --json
uv run ccr --root examples/phase_formation phase certify --json
```

Provider examples are local artifacts only:

```bash
uv run ccr --root examples/phase_formation provider import --provider http --report examples/phase_formation/mock_http_report.json --json
uv run ccr --root examples/phase_formation provider import --provider pic --report examples/phase_formation/pic_like_report.json --json
```

These commands do not prove real ASI and do not execute provider safe commands.
