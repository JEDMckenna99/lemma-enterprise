# Agent Ops MVP Decision Record - 2026-03-15

## Decision

- Decision: `GO`
- Scope: Agent Ops MVP launch on `https://lemma.id`
- Basis: all blocking MVP `P0` gates are `PASS` in `docs/status/AGENT_OPS_MVP_EXIT_GATES.md`

## Gate Summary

- P0-1 Proof-first enforcement on protected routes: `PASS`
- P0-2 Conformance allow/deny/scope/site/revoke controls: `PASS`
- P0-3 Revoke-to-deny demonstrated live: `PASS`
- P0-4 Kill switch deny path verified live: `PASS`
- P0-5 Incident drill baseline/failure/recovery: `PASS`
- P0-6 Post-deploy launch gate on production: `PASS`
- P0-7 Decision feed + explain + export backend deployed: `PASS`
- P0-8 Authenticated decision/explain/export hybrid verification: `PASS`
- P0-9 Key rotation + false deny + revocation runbook drills: `PASS`
- P0-10 One-command clean-state onboarding repeatability: `PASS`

P0 score at decision time: `10 / 10 PASS`

## Primary Evidence

- `docs/status/AGENT_OPS_MVP_EXIT_GATES.md`
- `docs/launch-evidence/2026-03-15-102258-post-deploy-summary.md`
- `docs/launch-evidence/2026-03-15-102800-post-deploy-openclaw-decision-export-verification.md`
- `docs/launch-evidence/2026-03-15-111800-agent-ops-ui-hybrid-verification.md`
- `docs/launch-evidence/2026-03-15-112500-p0-9-runbook-drills.md`
- `docs/launch-evidence/2026-03-15-113800-p0-10-clean-state-repeatability.md`

## Risk Acceptance (Non-Blocking P1)

The following remain open but are explicitly treated as post-MVP hardening:

- Delegation record completeness (bounds/expiry lineage)
- Revocation registry completeness across all credential shapes
- Customer API boundary pass for internal identifier leakage
- Prompt-injection trust/taint hardening (`taint_epoch`, stale-epoch deny)

## Post-Launch Commitments

1. Keep `P0` checks green on each deploy (post-deploy gate + incident drill cadence).
2. Execute P1 hardening in priority order from the MVP exit gates sheet.
3. Preserve evidence-first release discipline (`docs/launch-evidence/*`).
