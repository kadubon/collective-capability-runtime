# Bounded growth interchange

Interchange uses local JSON schemas pinned by commit and SHA-256 in
`examples/verified_growth/interchange/sources.json`. No companion runtime is a
dependency. Imported text, command hints, expressions and code are inert.

| Source | Supported input/output | Mapping and boundary |
|---|---|---|
| CAIT `8ef4bc1` | CCR envelope for window balances | Exports service observations, costs, evidence and unresolved attribution. It is explicitly not a CAIT capital or arrival certificate. |
| VEK `718a481` | Native verifier-packet schema | Preserves scope, origin, procedure, residuals, exposure and unknown dependence. It does not establish service rate or truth. |
| ALT `b5170db` | Native token schema `0.4.0` | Preserves immutable token/version, dependencies, guard, provenance and costs. Receiver qualification still requires CCR transfer and service evidence. |

These are schema-level adapters for the stated subset, not full semantic
conformance to the companion tools. Missing fields remain null or unresolved;
positive surplus/finality flags cannot add CCR growth. Unknown commit/schema
versions are rejected. Original JSON and its digest accompany every import.
The native fixtures are synthetic examples, not admitted production evidence.

```text
ccr --root runtime optimizer interchange --run <id> --tool vek --file envelope.json
ccr --root runtime optimizer interchange --run <id> --tool alt --file envelope.json --apply
ccr --root runtime optimizer interchange --run <id> --tool cait
```

An import envelope contains exactly `tool`, `source_commit`, `schema_sha256`,
and `payload`. Inspection is read-only. `--apply` journals the evidence and
adds unresolved review work, without promoting packets or changing service
credit. CAIT export is always read-only. PIC's existing compatibility matrix
and evidence-only conformance path are preserved. CPCF is not modified or
required.
