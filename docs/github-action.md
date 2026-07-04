# CCR GitHub Action

Use `.github/actions/ccr-audit` inside this repository to run CCR static audits in CI.

The action audits the checked-out source. When `uv` is available it runs
`uv sync --all-extras` and then calls `uv run ccr ...`; otherwise it installs
the checkout with `python -m pip install -e .` and calls `ccr ...`. It runs
`ccr audit repo --json`, a README claim audit, an ASI quickstart smoke, and a
workbench report smoke. It can optionally run
`ccr audit release --dist dist --json` after build artifacts exist. It does not create releases, push tags, upload to PyPI, or dispatch providers. It also does not push commits, import provider plugin code, or execute MCP/A2A handoffs.

Example:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: ./.github/actions/ccr-audit
```
