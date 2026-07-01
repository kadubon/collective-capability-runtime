# MCP And A2A Safety

MCP tool descriptors and A2A handoffs are untrusted candidate evidence until
checked. CCR stores or imports their reports as residual-preserving data; it
does not infer delegated authority from a descriptor, endpoint, message, or
handoff.

MCP descriptor checks should record server identity, descriptor hash, descriptor
version, provenance or signature when required, canonical tool name,
side-effect class, auth scope, egress policy, timeout/byte budgets, schema
hashes, and descriptor changes after approval. MCP invocation preflight remains
non-executing.

A2A checks should record agent-card identity, endpoint provenance, task schema,
declared authority, handoff scope, replay nonce, idempotency key, and the
non-claim that provider evidence is not settlement.

Search terms: MCP descriptor report, MCP invocation preflight, A2A agent card,
A2A task handoff, delegated authority, tool safety.
