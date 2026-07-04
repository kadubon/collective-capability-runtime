# CCR GitHub Action

Use `.github/actions/ccr-audit` inside this repository to run CCR static audits in CI.

The action installs `collective-capability-runtime`, runs `ccr audit repo --json`, and can optionally run `ccr audit release --dist dist --json` after build artifacts exist. It does not publish packages, create tags, push commits, call external providers, or execute MCP/A2A handoffs.

Example:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: ./.github/actions/ccr-audit
```
