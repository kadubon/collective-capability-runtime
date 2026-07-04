# CCR v1.5 P2 Runtime Surfaces

These commands help first-time agents move from residual review to local repair
work without expanding authority.

```bash
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

- residual market ranks local residuals; only `--emit task` writes a local task
- static workbench export writes HTML/JSON with no external assets
- replay and verification read evidence only and never dispatch providers
- conformance treats PIC reports as evidence only, not CCR settlement
- provider registry validation reads metadata and manifests only; it does not
  import plugin modules or execute provider code
