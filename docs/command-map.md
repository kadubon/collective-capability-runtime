# CCR Command Map

This map groups Collective Capability Runtime commands by P0, P1, and P2
surface. It also identifies which commands only inspect local state and which
commands write local CCR artifacts.

CCR is local-first by default. Audit commands do not release packages, push
tags, upload to PyPI, call providers, dispatch MCP/A2A tools, or prove physical
outcomes.

Related optional PIC project:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

## First-time agent guide

Purpose: choose the right CCR command for the next local step without confusing
inspection, local artifact writes, provider execution, and settlement.

First commands:

```bash
ccr agent explain --json
ccr asi quickstart --profile development --json
ccr mission next --mission mission:quickstart --compact --json
ccr residual market --mission mission:quickstart --json
```

Safe boundary: the P0/P1/P2 inspection commands below preserve
`external_execution=false`, `network_call_performed=false`, and `settled=false`
unless an older source artifact explicitly records execution evidence. Replay
inspection is still not dispatch.

Expected outputs: command reports expose `ok`, `accepted`, `settled`,
`external_execution`, `network_call_performed`, blockers, residuals,
`residual_ready`, hashes, refs, and non-claims where applicable.

Failure/residual handling: use `--fail-on` in CI when blocking residuals,
missing missions, unsupported claims, overclaims, or schema errors should fail
closed. Preserve the returned residual object as the repair target.

P2 safe commands:

```bash
ccr residual market --json
ccr residual market --mission mission:quickstart --json
ccr residual bounty --residual <residual_id> --mission mission:quickstart --emit task --json
ccr residual diff --before before.json --after after.json --json
ccr workbench export --mission mission:quickstart --format static-html --out site/ --json
ccr operation replay-manifest --dispatch-report dispatch.json --observation observation.json --out replay.json --json
ccr operation verify-observation --manifest replay.json --verifier verifier.json --json
ccr conformance bundle --bundle examples/asi_proxy_mission_bundle --json
ccr conformance parity --ccr-report ccr.json --pic-report pic.json --json
ccr provider registry-validate --file provider-registry.json --json
```

Provider import: provider reports are evidence. Imported `safe_commands` become
task hints only and do not grant authority.

Phase formation cycle: packet work, verifier evidence, residual repair,
baseline comparison, and phase formation repeat until blockers are removed or
clearly preserved.

What not to claim: do not claim real ASI, automatic authority, physical outcome
truth, model self-rewrite, or CCR settlement from provider/PIC evidence alone.

## P0 Mission Core

| Command | Purpose | Local write |
|---|---|---|
| `ccr asi quickstart --profile development --json` | create a local mission fixture | yes |
| `ccr mission status --mission <id> --json` | inspect mission state | no |
| `ccr mission next --mission <id> --compact --json` | choose next safe action | no |
| `ccr mission ingest --mission <id> --from markdown --input file.md --json` | ingest one local input | yes |
| `ccr mission report --mission <id> --format json --out report.json` | write a mission report | yes |
| `ccr workbench report --mission <id> --format markdown --out report.md` | write a workbench report | yes |
| `ccr claim audit --input README.md --json` | detect overclaims in prose | no |
| `ccr bundle validate --bundle bundle/ --json` | validate a local mission bundle | no |

## P1 Gate and Ingest Layer

| Command | Purpose | Local write |
|---|---|---|
| `ccr mcp inspect-descriptor --file descriptor.json --json` | inspect MCP descriptor safety | no |
| `ccr mcp preflight --descriptor descriptor.json --invocation invocation.json --json` | preflight MCP invocation | no |
| `ccr a2a inspect-card --file card.json --json` | inspect A2A agent card | no |
| `ccr a2a preflight-handoff --handoff handoff.json --card card.json --json` | preflight A2A handoff | no |
| `ccr ingest trace --input trace.md --json` | inspect trace as candidate evidence | no |
| `ccr ingest trace --input trace.md --mission <id> --write-candidates --json` | write mission candidates | yes |
| `ccr ingest repo --path . --json` | inspect repository text safely | no |
| `ccr provider manifest --file manifest.json --json` | inspect static provider contract | no |
| `ccr provider conformance --file manifest.json --json` | validate provider boundary | no |

## P2 Usability Layer

| Command | Purpose | Local write |
|---|---|---|
| `ccr residual market --mission <id> --json` | rank residual repair work | no |
| `ccr residual bounty --residual <id> --mission <id> --emit task --json` | create one repair task | yes |
| `ccr residual diff --before before.json --after after.json --json` | compare residual sets | no |
| `ccr workbench export --mission <id> --format static-html --out site/ --json` | write static local workbench | yes |
| `ccr operation replay-manifest --dispatch-report dispatch.json --observation observation.json --out replay.json --json` | build evidence replay manifest | yes |
| `ccr operation verify-observation --manifest replay.json --verifier verifier.json --json` | verify observation evidence | no |
| `ccr conformance bundle --bundle bundle/ --json` | check local bundle conformance | no |
| `ccr conformance parity --ccr-report ccr.json --pic-report pic.json --json` | compare CCR/PIC reports | no |
| `ccr provider registry-validate --file registry.json --json` | validate static registry metadata | no |
| `ccr provider registry-list --file registry.json --json` | list registry metadata | no |

## Transactional Task And Residual Work

```bash
ccr storage doctor --json
ccr storage migrate --json
ccr storage reconcile --json
ccr task heartbeat <task_id> --agent <agent_id> --fencing-token <token> --json
ccr task complete <task_id> --agent <agent_id> --fencing-token <token> --idempotency-key result.1 --summary "ready" --json
ccr task fail <task_id> --agent <agent_id> --fencing-token <token> --reason "blocked" --json
ccr task retry <task_id> --reason "repair available" --json
ccr residual assign --residual <residual_id> --agent <agent_id> --json
ccr residual resolve --residual <residual_id> --artifact repair.json --verifier verifier.json --json
ccr residual reopen --residual <residual_id> --reason "new evidence" --json
```

Heartbeat and completion require the current fencing token. Residual resolution
requires digest-bound repair evidence from an independent verifier.

## Distributed And Experiment Work

```bash
ccr server run --auth-config oidc.json
ccr worker run --role verifier --worker-id worker:verifier-1 --once
ccr experiment register --suite study-a --manifest manifest.json --json
ccr experiment ingest --suite study-a --label baseline --file baseline.json --json
ccr experiment compare --baseline baseline.json --candidate collective.json --json
```

The server and worker need the optional `distributed` extra. Write APIs require
OIDC + DPoP. Experiment acceleration claims require a preregistered fixed
horizon or confidence sequence.

## Commands Requiring Extra Authority

`ccr provider execute --execute` is outside the safe first-use path. It requires
an explicit operator request, an explicit config file, and provider-specific
policy checks. Audit, conformance, preflight, replay, and registry validation do
not grant that authority.
