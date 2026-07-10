# Collective Runtime Mechanics

This source-checkout fixture demonstrates two bounded CCR mechanics:

1. correlated workcell proposals count as one independent support group;
2. a preregistered collective result is compared with a resource-matched
   baseline using a fixed-horizon interval.

It is not a general capability benchmark and does not prove ASI or model
improvement.

## Workcell

```bash
uv run ccr --root .tmp/collective-runtime workcell create --template packet-distillation --name review-a --json
uv run ccr --root .tmp/collective-runtime workcell submit --workcell review-a --file examples/collective_runtime/proposal-a.json --json
uv run ccr --root .tmp/collective-runtime workcell submit --workcell review-a --file examples/collective_runtime/proposal-b.json --json
uv run ccr --root .tmp/collective-runtime workcell advance --workcell review-a --to reveal --json
uv run ccr --root .tmp/collective-runtime workcell advance --workcell review-a --to critique --json
uv run ccr --root .tmp/collective-runtime workcell advance --workcell review-a --to revision --json
uv run ccr --root .tmp/collective-runtime workcell advance --workcell review-a --to verification --json
uv run ccr --root .tmp/collective-runtime workcell integrate --workcell review-a --strategy residual-preserving --json
```

Both submissions use the same model, tool, and source. The final claim has two
raw supports but one `effective_support_count`. Integration remains
`settled=false` and does not promote a packet by itself.

## Experiment

```bash
uv run ccr --root .tmp/collective-runtime experiment register --suite study-a --manifest examples/collective_runtime/experiment-manifest.json --json
uv run ccr --root .tmp/collective-runtime experiment ingest --suite study-a --label baseline --file examples/collective_runtime/baseline.json --json
uv run ccr --root .tmp/collective-runtime experiment ingest --suite study-a --label collective --file examples/collective_runtime/collective.json --json
uv run ccr experiment compare --baseline examples/collective_runtime/baseline.json --candidate examples/collective_runtime/collective.json --json
```

The baseline and collective files use the same declared budget and time. The
fixture has a preregistered horizon of 100 observations. Replace the task,
evaluator, versions, resources, and outcomes before using the protocol for a
real study.
