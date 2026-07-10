# Security Audit Checklist

This checklist maps CCR release review to the NIST AI Risk Management
Framework functions and the OWASP AI Agent Security controls. It is an
engineering checklist, not a certification.

## Govern

- [ ] Human approval identity is separate from worker identity.
- [ ] Provider, verifier, scheduler, and integrator responsibilities are named.
- [ ] `NON_CLAIMS` remain visible in public reports and documentation.
- [ ] Schema registry digest and every registered schema digest match.
- [ ] Release workflow uses least privilege and trusted publishing.

## Map

- [ ] Mission, validity domain, authority scope, resource envelope, and hazard
      envelope are explicit.
- [ ] External files, reports, prompts, MCP descriptors, A2A cards, and provider
      responses are classified as untrusted inputs.
- [ ] Network, physical, irreversible, and legal side effects are identified.
- [ ] Agent/model/tool/source correlation groups are recorded.

## Measure

- [ ] Unknown coordinates do not become zero, positive reuse, or progress.
- [ ] Resource-matched baseline, best-solo uplift, time-to-checked, residual
      half-life, verification yield, effective agent count, error correlation,
      and communication/verification cost are reported where known.
- [ ] Fixed-horizon or confidence-sequence design was preregistered.
- [ ] Adversarial agents, correlated votes, minority reports, stale leases, and
      replay attempts are tested.

## Manage

- [ ] Blocking residuals remain open until artifact-bound independent review.
- [ ] Task completion uses owner identity, fencing token, and idempotency key.
- [ ] Operation approval binds plan, provider, config, scope, resources, expiry,
      nonce, and use count.
- [ ] Provider circuit, rollback, hazard, incident, and verifier gates fail closed.
- [ ] PostgreSQL delivery is documented as at-least-once, not exactly-once.

## OWASP Agent Controls

- [ ] Prompt and external-content injection does not grant tool authority.
- [ ] Tool calls use allowlists, strict schemas, least privilege, and bounded
      inputs/outputs.
- [ ] HTTPS endpoints use exact host allowlists, redirect denial, public-address
      DNS checks, and byte/time limits.
- [ ] OIDC issuer/audience/expiry and DPoP key, method, URI, token hash, time,
      and replay ID are verified.
- [ ] Secrets, prompts, cookies, credentials, and PII are excluded from default
      telemetry.
- [ ] Memory, packet, residual, provider, and verifier artifacts retain digest
      provenance and cannot silently overwrite normative schemas.
- [ ] Safe command hints are never automatically executed.
- [ ] Physical outcomes require a trusted Ed25519 key, observation digest,
      validity scope, and observation window.

Run these local checks before release review:

```bash
uv run ccr audit repo --json
uv run python scripts/check_schema_registry.py
uv run pytest
uvx bandit -q -r src
uvx pip-audit
uv build
uv run ccr audit release --dist dist --json
```

Search terms: NIST AI RMF Govern Map Measure Manage, OWASP AI Agent Security,
prompt injection, tool authorization, agent identity, DPoP replay, SSRF,
residual ledger, verifier separation, software supply chain.
