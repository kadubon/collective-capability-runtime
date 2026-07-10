# Getting Started With CCR

This is the shortest safe path from an empty directory to an inspectable agent
coordination mission. It works with the published package and performs no
provider execution or network request.

## Install And Inspect

```bash
python -m pip install collective-capability-runtime
ccr agent explain --json
```

Confirm that `default_mode` is `dry_run` and read `safe_next_commands`. The
manifest reports local write boundaries and explicit non-claims for agents that
have not seen the repository.

## Create A Local Mission

Use a dedicated runtime directory so generated artifacts do not mix with source
files:

```bash
ccr --root ccr-runtime asi quickstart --profile development --json
ccr --root ccr-runtime mission status --mission mission:quickstart --json
ccr --root ccr-runtime mission next --mission mission:quickstart --compact --json
ccr --root ccr-runtime workbench report --mission mission:quickstart --format markdown --out CCR_WORKBENCH.md
```

Expected output:

- `ok=true` when the local command completes;
- `external_execution=false` and `network_call_performed=false`;
- `settled=false` while evidence or verification remains incomplete;
- a `CCR_WORKBENCH.md` file containing packets, tasks, and residuals.

## Route Remaining Work

```bash
ccr --root ccr-runtime residual market --mission mission:quickstart --json
ccr --root ccr-runtime task next --role verifier --json
```

The market ranks residual work but never waives it. A repair is resolved only
after an artifact-bound independent verifier report is supplied. A leased task
must echo its current fencing token when heartbeating or completing.

## Try Collective Coordination

For a repository checkout, the mechanics fixture supplies complete input JSON:

```bash
uv run ccr --root .tmp/collective-runtime workcell create --template packet-distillation --name review-a --json
uv run ccr --root .tmp/collective-runtime workcell submit --workcell review-a --file examples/collective_runtime/proposal-a.json --json
uv run ccr --root .tmp/collective-runtime workcell submit --workcell review-a --file examples/collective_runtime/proposal-b.json --json
```

Continue with
[examples/collective_runtime/README.md](../examples/collective_runtime/README.md)
and [Collective Workcells](collective-workcells.md). The fixture demonstrates
correlation discounting; it is not a capability benchmark.

## Choose The Next Guide

- [Collective Workcells](collective-workcells.md): proposal isolation, critique,
  task leasing, and residual resolution.
- [Distributed Runtime](distributed-runtime.md): PostgreSQL, OIDC + DPoP, and
  worker processes.
- [Measurement Protocol](measurement-protocol.md): preregistered,
  resource-matched comparisons.
- [Operation Gate](operation-gate.md): external-effect approval and dispatch.
- [Command Map](command-map.md): all major commands and local write behavior.

What not to claim: a successful quickstart proves only that the finite local
workflow ran. It does not prove real ASI, model improvement, legal authority,
physical outcome, or settlement.
