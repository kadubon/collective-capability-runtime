# Runtime Fixture

This directory is a placeholder for a disposable CCR runtime root.

Recommended sequence:

```bash
ccr --root examples/asi_proxy_benchmark_bundle/ccr_runtime init
ccr --root examples/asi_proxy_benchmark_bundle/ccr_runtime task import --file ../tasks.jsonl --provider pic --json
ccr --root examples/asi_proxy_benchmark_bundle/ccr_runtime residual import --file ../residuals.jsonl --provider pic --json
ccr --root examples/asi_proxy_benchmark_bundle/ccr_runtime foundry dashboard --json
```
