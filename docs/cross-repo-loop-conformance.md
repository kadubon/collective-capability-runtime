# Cross-Repo Loop Conformance

The shared v0.9/v1.4 loop roundtrip checks that PIC emits token, residual, task, and capital-witness reports; CCR imports them and computes loop-next, foundry, performance, and interval reports; PIC-TS mirrors the public JSON shape without Python at runtime.

Parity fields are schema_version, ok, accepted, settled, executed, capital_admitted, certified_acceleration_candidate, certified_acceleration_interval_candidate, blockers, residual kinds, non_claims, hashes, and refs. Numeric interval tolerance must be explicitly declared.

## v1.5 P2 Parity Boundary

`ccr conformance bundle` and `ccr conformance parity` read local files only.
They do not call GitHub, execute providers, dispatch tools, or settle CCR.
Missing parity fields become residual-ready evidence. PIC and PIC-TS remain
checker layers; parity is evidence, not settlement.
