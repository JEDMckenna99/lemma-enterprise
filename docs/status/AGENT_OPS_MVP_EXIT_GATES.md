# Agent Ops MVP Exit Gates

Objective pass/fail sheet for MVP launch readiness of Agent Ops.

Use this as a binary launch control, not a roadmap.

---

## Decision Rule

- MVP launch is ready when all `P0` gates are `PASS`.
- Any `P0` gate marked `OPEN` blocks MVP launch.
- `P1` gates can remain open only with explicit risk acceptance.

---

## Current Snapshot

- Last updated: `2026-03-16`
- Environment: `https://lemma.id`
- Current deployment: Heroku `v1966` (`80676ae3`)
- P0 score: `10 / 10 PASS`
- Distance to MVP: **at MVP threshold** (`P0 complete`)

---

## P0 Gates (Blocking)

| ID | Gate | Status | Evidence | Gap to Close |
|---|---|---|---|---|
| P0-1 | Proof-first enforcement on protected routes | PASS | `docs/AGENT_OPS_READINESS.md`, `scripts/lemma_firewall.py` | None |
| P0-2 | Conformance: allow/deny/scope/site/revoke controls green | PASS | `docs/AGENT_OPS_READINESS.md`, `tests/test_authz_v2_controls.py` | None |
| P0-3 | Revoke-to-deny demonstrated in live flow | PASS | `ops/evidence/launch/2026-03-14-210301-revoke-to-deny-evidence.md` | None |
| P0-4 | Kill switch deny path verified live | PASS | `scripts/run_agent_ops_e2e.ps1`, `docs/AGENT_OPS_READINESS.md` | None |
| P0-5 | Incident drill (baseline/failure/recovery) passed | PASS | `ops/evidence/launch/2026-03-14-180322-incident-drill-auth-control-plane.md` | None |
| P0-6 | Post-deploy launch gate passes on production | PASS | `docs/launch-evidence/2026-03-15-102258-post-deploy-summary.md` | None |
| P0-7 | Decision feed + explain + export backend deployed | PASS | `api/services/wallet_service.py`, `docs/launch-evidence/2026-03-15-102800-post-deploy-openclaw-decision-export-verification.md` | None |
| P0-8 | Agent Ops UI clickthrough evidence (authenticated browser/hybrid) | PASS | `docs/launch-evidence/2026-03-15-111800-agent-ops-ui-hybrid-verification.md` | None |
| P0-9 | Runbook closure for key rotation / false deny / revocation incident | PASS | `docs/launch-evidence/2026-03-15-112500-p0-9-runbook-drills.md` | None |
| P0-10 | One-command onboarding reliability repeatability (clean machine) | PASS | `docs/launch-evidence/2026-03-15-113800-p0-10-clean-state-repeatability.md` | None |

---

## P1 Gates (Strongly Recommended)

| ID | Gate | Status | Evidence | Note |
|---|---|---|---|---|
| P1-1 | Delegation record completeness (bounds/expiry lineage) | PASS | `api/agent_ops_store.py`, `tests/test_agent_ops_store_lineage.py` | Lineage now included in decision list/explain/export payloads |
| P1-2 | Revocation registry completeness across all shapes | PASS | `api/authz_control_plane.py`, `ops/evidence/launch/2026-03-16-170427-revoke-to-deny-evidence.md` | Delta includes normalized revocation subject shape metadata |
| P1-3 | Customer API boundary pass (no internal identifier leakage) | PASS | `api/services/wallet_service.py`, `tests/test_agent_ops_enterprise_hardening.py` | OpenClaw runtime/decision APIs return PPID-first payloads without default wallet_id leakage |
| P1-4 | Prompt-injection trust/taint controls (`taint_epoch`, stale-epoch deny) | PASS | `api/services/wallet_service.py`, `tests/test_agent_ops_enterprise_hardening.py` | Runtime authorize enforces stale-epoch and step-up-required deny paths |

---

## MVP Launch Recommendation

All blocking `P0` gates are `PASS` and all `P1` hardening gates are now `PASS` on current deployment.

Agent Ops is at MVP `GO` and enterprise-hardening complete for the current tracked gate set.
