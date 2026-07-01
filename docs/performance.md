# Performance

The v0.9/v1.4 performance surface is local-only and deterministic. It reports CLI startup, JSON/JSONL counts, SQLite index counts, cache entries, graph size, duplicate hashes, and p50/p95/p99 placeholders where stable timing is unavailable.

Optimizations must not weaken fail-closed semantics. Cache hits are valid only under schema, dependency, profile, authority, and hazard hashes; a cache hit is not proof. Optional fast JSON or hash dependencies remain optional.
