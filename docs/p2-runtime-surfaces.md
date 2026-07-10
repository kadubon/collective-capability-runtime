# P2 Runtime Surfaces

Introduced in CCR v1.5.0, these compatibility commands help agents move from residual review to local repair
work without expanding authority.

Start with [Getting Started](getting-started.md) for the first run and
[Command Map](command-map.md) for the P0/P1/P2 command overview.

P2 safe commands:

```bash
ccr residual market --json
ccr residual market --mission <mission_id> --json
ccr residual bounty --residual <residual_id> --mission <mission_id> --emit task --json
ccr residual diff --before before.json --after after.json --json
ccr workbench export --mission <mission_id> --format static-html --out site/ --json
ccr operation replay-manifest --dispatch-report dispatch.json --observation observation.json --out replay.json --json
ccr operation verify-observation --manifest replay.json --verifier verifier.json --json
ccr conformance bundle --bundle bundle/ --json
ccr conformance parity --ccr-report ccr.json --pic-report pic.json --json
ccr provider registry-validate --file provider-registry.json --json
ccr provider registry-list --file provider-registry.json --json
```

Safety boundary:

- residual market ranks mission-scoped or runtime-wide local residuals; only
  `--emit task` writes a local task
- residual market ranks work; it does not waive residuals or settle CCR
- static workbench export writes HTML/JSON with no external assets
- static workbench is presentation, not proof
- replay and verification read evidence only and never dispatch providers
- operation replay is not dispatch
- observation verification is not physical outcome proof
- conformance treats PIC reports as evidence only, not CCR settlement
- provider registry validation reads metadata and manifests only; it does not
  import plugin modules or execute provider code
- provider registry is static metadata, not authority
- operation replay preserves source `executed=true` evidence when present, but
  the replay itself keeps `external_execution=false`,
  `provider_dispatch_ready=false`, and `physical_outcome_proven=false`
- audit and P2 runtime commands perform no release, tag, PyPI upload, or provider dispatch

Use this sequence when a mission already exists:

```bash
ccr mission next --mission mission:quickstart --compact --json
ccr residual market --mission mission:quickstart --json
ccr residual bounty --residual <residual_id> --mission mission:quickstart --emit task --json
ccr workbench export --mission mission:quickstart --format static-html --out site/ --json
```

Expected outputs include `ok`, `settled=false`, `external_execution=false`,
`network_call_performed=false`, residual ids, blockers, output paths, and
non-claims.
