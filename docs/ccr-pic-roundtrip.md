# CCR/PIC Roundtrip

PIC and CCR remain separate:

- PIC checks, compiles, and emits diagnostic task/residual JSONL.
- CCR stores, leases, schedules, integrates, and preserves residuals.

Roundtrip commands:

```bash
pic phase plan --compact --emit ccr-tasks > tasks.jsonl
pic phase gap --compact --emit ccr-residuals > residuals.jsonl
ccr task import --file tasks.jsonl --provider pic --json
ccr residual import --file residuals.jsonl --provider pic --json
ccr phase report --json
```

The `ccr demo pic-roundtrip --json` command runs a disposable local demo. It
does not require PIC to be installed unless `--execute-pic` is passed.

TRC operation handoff uses the same separation:

```bash
pic trc trace-check --trace trace_nf.json > trc_trace_report.json
ccr operation plan --trace trc_trace_report.json --json
ccr operation execute --plan operation_plan.json --provider http --config provider.json --execute --json
```

The final command is the only stage that can call a provider, and it requires an
operation-ready PIC report, an explicit execute flag, and provider config. Safe
command hints and operation plans are not authority by themselves.
