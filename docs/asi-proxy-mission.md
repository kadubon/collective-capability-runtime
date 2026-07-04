# ASI-Proxy Mission Runtime

The Mission Runtime Layer is the first-use facade for Collective Capability
Runtime. It groups the local target, baseline upper envelope, authority
envelope, hazard envelope, resource envelope, packet workspace, residual ledger,
loop policy, provider policy, and report policy into one inspectable workflow.

```bash
ccr asi quickstart --profile development --json
ccr mission next --mission mission:quickstart --compact --json
ccr workbench report --mission mission:quickstart --format markdown --out CCR_WORKBENCH.md
```

Mission is not a replacement for phase semantics. Packet promotion, residual
preservation, baseline comparison, threshold status, and certificate-candidate
logic remain the underlying CCR protocol. PIC remains optional and PIC output is
evidence only, not CCR settlement.

Safe boundaries:

- `external_execution=false` means no provider, shell, network, repository, or
  physical action was dispatched.
- `settled=false` is normal diagnostic state.
- `operation_ready` is not execution.
- `physical_ready` is not physical outcome proof.
- cache and SQLite index hits are never proof.
- safe commands are review hints, not authority.

Useful local commands:

```bash
ccr mission init --name demo --profile development --template local-asi-proxy --json
ccr mission status --mission mission:demo --json
ccr mission ingest --mission mission:demo --from markdown --input README.md --json
ccr mission next --mission mission:demo --compact --json
ccr mission report --mission mission:demo --format markdown --out CCR_WORKBENCH.md
ccr mission report --mission mission:demo --format json --out report.json --fail-on blocking_residual
ccr claim audit --input README.md --json
ccr bundle validate --bundle examples/asi_proxy_mission_bundle --profile development --json
ccr mcp inspect-descriptor --file examples/asi_proxy_acceleration_bundle/mcp_descriptor.good.json --json
ccr a2a preflight-handoff --handoff examples/asi_proxy_acceleration_bundle/a2a_handoff.good.json --json
ccr provider conformance --file examples/asi_proxy_acceleration_bundle/provider_manifest.good.json --json
```

Input hardening:

- Mission ingest and claim audit read bounded UTF-8 text and return
  `residual_ready` for binary, oversized, malformed, or undecodable input.
- Workbench and mission reports are scoped to one mission's state, packet refs,
  residual refs, and `x_ccr_mission_id` extensions.
- Bundle validation is schema-bound and reference-closed for local CCR object
  refs. Path traversal and implicit execution/network/settlement claims fail
  closed.
