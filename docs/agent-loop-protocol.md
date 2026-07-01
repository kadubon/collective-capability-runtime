# Agent Loop Protocol

Agents should ask for the next finite safe action, run only local checker commands, preserve residuals, and avoid treating accepted reports as settled state. CCR `loop next` is advisory and non-mutating. PIC and PIC-TS reports expose blockers, residual counts, non-claims, and compact next-safe-action summaries.

No loop command grants shell, network, provider, physical, repository, or model-update authority. Provider planning, preflight, dispatch, and observation remain separate. Unknown budgets are residuals, not zero.
