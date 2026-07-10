# Collective Workcells

CCR workcells organize several agents without treating headcount or majority
vote as verified capability. The protocol stages are:

```text
independent_proposal -> reveal -> critique -> revision -> verification -> integration
```

During `independent_proposal`, each submission is stored with
`visibility=hidden_until_reveal`. A submission records model, tool, and source
provenance. Supports with the same provenance group count once, so repeated
outputs from one model or source do not look like independent agreement.

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

These commands use the source-checkout fixture. The two proposals deliberately
share a correlation group, so they demonstrate why duplicate support counts
once. They do not demonstrate an improvement claim.

Integration is claim-based. Each claim keeps support submissions, distinct
correlation groups, evidence, dependencies, contradictions, and minority
reports. An unresolved contradiction creates a blocking residual. Agent count,
role names, or majority support never marks a packet checked or settled.
Skipping directly to integration remains available for v1 compatibility, but it
creates a blocking incomplete-stage residual and `protocol_complete=false`.

Task leases include a monotonic fencing token. A worker must echo the current
token when sending a heartbeat, completion, or failure. Completion also needs
an idempotency key. Old workers cannot overwrite a reclaimed lease.

```bash
ccr task lease <task_id> --ttl 30m --agent worker.one --json
ccr task heartbeat <task_id> --agent worker.one --fencing-token <token> --json
ccr task complete <task_id> --agent worker.one --fencing-token <token> \
  --idempotency-key result.1 --summary "candidate ready" --output candidate.json --json
```

Residual resolution requires both a repair artifact and verifier JSON whose
`artifact_sha256` matches that artifact. The verifier must differ from the
assigned repair agent. Reopening preserves prior resolution evidence.

Expected integration fields include `protocol_complete`, `claims`,
`effective_support_count`, `minority_reports`, and blocking residuals. An
integration report remains `settled=false`.

Search terms: multi-agent collaboration, collective intelligence, independent
proposal, correlated votes, minority report, task lease, fencing token,
idempotency, residual resolution.
