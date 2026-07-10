# Distributed Runtime

CCR has two storage profiles with the same task lifecycle:

| Profile | Authoritative state | Intended use |
|---|---|---|
| SQLite | local transaction database plus inspectable JSON | one machine, local agents |
| PostgreSQL 16+ | PostgreSQL tables; JSON is export | multiple API and worker processes |

Install the optional profile:

```bash
python -m pip install "collective-capability-runtime[distributed]"
```

PostgreSQL workers claim tasks with `FOR UPDATE SKIP LOCKED`, database time,
lease expiry, and monotonic fencing tokens. Delivery is at least once.
Idempotency keys make completion safe to retry; CCR does not claim exactly-once
execution. A transactional outbox records committed state changes without
requiring Kafka, NATS, or another broker.

Set the database URL in an environment variable rather than a command argument.
For Linux and macOS:

```bash
export CCR_DATABASE_URL='postgresql://...'
ccr server run --auth-config oidc.json --host 127.0.0.1 --port 8787
ccr worker run --role verifier --worker-id worker:verifier-1 --once
```

For PowerShell:

```powershell
$env:CCR_DATABASE_URL = 'postgresql://...'
ccr server run --auth-config oidc.json --host 127.0.0.1 --port 8787
ccr worker run --role verifier --worker-id worker:verifier-1 --once
```

`oidc.json` must contain the trusted issuer, audience, and JWKS. It must not
contain a worker token or private signing key.

All `/v1` write requests require an OIDC access token using the `DPoP`
authorization scheme and a matching RFC 9449 proof. CCR verifies issuer,
audience, expiry, access-token hash, method, target URI, key thumbprint, proof
age, and one-time `jti`. Replay identifiers are consumed in the authoritative
database. Worker subjects and human approval subjects use separate configured
prefixes.

The local storage tools never repair disagreements silently:

```bash
ccr storage doctor --json
ccr storage migrate --json
ccr storage migrate --apply --json
ccr storage reconcile --json
```

`migrate` defaults to a dry-run report. It preserves original JSON, IDs,
timestamps, hashes, and residual status. `reconcile` reports missing files,
digest mismatches, and path escapes without choosing which side is correct.

Events carry CloudEvents-compatible fields, a locally generated W3C
`traceparent`, and PROV-oriented provenance. Incoming trace context is not
trusted as an authority signal. OpenTelemetry is opt-in with
`CCR_OTEL_ENABLED=1`; prompt, secret, credential, cookie, and PII-like fields
are not emitted.

Search terms: distributed AI agent runtime, PostgreSQL task queue, SKIP LOCKED,
transactional outbox, fenced lease, FastAPI, OIDC, DPoP, CloudEvents, trace
context, provenance, OpenTelemetry.
