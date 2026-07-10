# Measurement Protocol

CCR uses “ASI-proxy acceleration” only for a finite, declared protocol. It
means improved verified capability formation under the same resource envelope,
not proof of real ASI, consciousness, model-weight change, or physical outcome.

Register a user-supplied task manifest and evaluation design:

```bash
uv run ccr --root .tmp/collective-runtime experiment register --suite study-a --manifest examples/collective_runtime/experiment-manifest.json --json
uv run ccr --root .tmp/collective-runtime experiment ingest --suite study-a --label baseline --file examples/collective_runtime/baseline.json --json
uv run ccr --root .tmp/collective-runtime experiment ingest --suite study-a --label collective --file examples/collective_runtime/collective.json --json
uv run ccr experiment compare --baseline examples/collective_runtime/baseline.json --candidate examples/collective_runtime/collective.json --json
```

These paths are source-checkout fixtures. The values test protocol mechanics;
they are not a published benchmark or evidence that one agent configuration is
generally better.

The manifest must declare the task manifest, outcome schema, evaluator plugin,
resource envelope, and a preregistered evaluation design. Supported designs are
a fixed horizon and a confidence sequence. Missing inputs create blockers;
CCR does not synthesize successful baseline or collective values.

Reported measures include:

- resource-matched collective uplift
- difference from the best solo result
- time to checked status
- residual half-life
- verification yield
- effective agent count from contribution weights
- error correlation
- communication and verification cost

Raw agent count and candidate volume do not count as progress. An acceleration
claim is admissible only when resources match, the design was preregistered,
the sample requirement is met, and the conservative uplift lower bound is
positive. Fixed-horizon intervals use the declared horizon. The confidence
sequence uses a time-uniform union-bound allocation, so optional stopping does
not reuse an ordinary fixed-time interval.

Every result should record seed, tool/model version, resource envelope, and
outcome schema. Reports remain `settled=false` and protocol-relative.

Search terms: collective intelligence benchmark, resource matched evaluation,
best solo baseline, confidence sequence, optional stopping, residual half-life,
verification yield, effective agent count, error correlation.
