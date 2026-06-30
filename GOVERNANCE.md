# Governance

Related optional PIC project:
[kadubon/percolation-inversion-compiler](https://github.com/kadubon/percolation-inversion-compiler)

```bash
python -m pip install percolation-inversion-compiler
```

PIC integration is optional and cannot bypass CCR release, schema, residual, or
settlement policy.

## Release Policy

CCR follows semantic versioning from v1.0. Stable v1 interfaces are CLI commands
and JSON schemas. The Python API is semi-stable and may evolve with migration
notes.

PyPI releases use the project name `collective-capability-runtime` and GitHub
Trusted Publishing from `kadubon/collective-capability-runtime`. Publication is
allowed only from the release workflow `.github/workflows/workflow.yml`.

## Compatibility Policy

Local schemas are authoritative. Packaged schemas are fallbacks for installed
usage. A command must not silently accept an incompatible unknown schema version.

## Schema Versioning

Schema versions use the form:

```text
ccr.<object>.v<major>[.<minor>]
```

Breaking schema changes require:

- changelog entry
- updated examples
- updated tests
- documented migration route

New phase, baseline, provider, or audit schemas must preserve non-claim fields
where applicable: `protocol_relative_only=true`, `proves_real_asi=false`, and
`settled=false`.

## Side-Effect Changes

Any change that adds external side effects, network behavior, command execution,
or broader filesystem mutation requires maintainer review and an explicit
documentation update.

Provider additions must default to dry-run planning, expose health and
capabilities, require explicit execution authority, and preserve failure
residuals.

Publish workflow changes must keep `id-token: write`, avoid PyPI token secrets,
and run build, lint, tests, audit, and distribution metadata checks before
publishing.
