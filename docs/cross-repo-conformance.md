# Cross-Repo Conformance

The v0.8 conformance loop is:

1. PIC Python emits target, baseline, capital, MCP/A2A, SQOT, BIT, and TRC
   reports.
2. CCR imports candidate tasks, residuals, and capital witnesses without
   settlement.
3. CCR emits foundry dashboards, active cuts, allocation hints, availability
   reports, and phase acceleration reports.
4. PIC Python checks the returned reports.
5. PIC-TS emits equivalent public JSON shapes for shared fixtures without a
   Python runtime dependency.

Compare required keys, status booleans, blockers, non-claims, residual kinds,
and rounded numeric coordinates. Do not compare transient file paths or runtime
artifact IDs.

Search terms: cross-repo conformance, PIC, PIC-TS, CCR, roundtrip, phase
acceleration report, runtime capital witness, JSONL residuals.
