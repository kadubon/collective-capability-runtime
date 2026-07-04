# ASI-Proxy Mission Bundle Fixture

This fixture is a local, non-executing CCR mission bundle for validating the
Mission Runtime Layer. It contains a mission facade, ASI-proxy target, baseline
upper envelope, candidate packet, and workbench report.

It is evidence for bundle shape only. It is not real ASI proof, execution
authority, provider settlement, PIC settlement, or physical outcome proof.

```bash
ccr bundle validate --bundle examples/asi_proxy_mission_bundle --profile development --json
```
