# Agent Authz Beginner-to-Enterprise Execution Plan

Date: 2026-03-13  
Owner: platform

## Goal

Make `lemma.id` provide immediate out-of-box risk mitigation for beginner agent users, then scale to enterprise controls without changing the trust model.

## Product Promise

- Beginner (day 0): passkey-rooted, proof-first, local-first guardrails with one command.
- Advanced (day 30+): stronger policy customization, audit exports, and org-scale controls.

## Immediate Benefit Definition (Beginner)

A beginner user gets value on first run if all are true:

1. One command creates/loads proof, connects runtime, and validates authz path.
2. Default profile blocks risky behavior without manual policy editing.
3. Runtime kill switch can stop privileged actions immediately.
4. User can see clear pass/fail outcome and next remediation step.

## Phase Plan

### Phase 1 - Starter Safe Defaults (now)

Status: `in_progress`

Deliverables:

- `starter_safe` security profile as onboarding default.
- Local-first enforcement enabled by default.
- Noncritical online fallback disabled by default.
- External activity logging minimized by default.
- One-command E2E script generates evidence artifacts.

Acceptance:

- `scripts/setup_openclaw_authz_seconds.ps1` defaults to `starter_safe`.
- `scripts/start_openclaw_firewall.ps1` defaults to `starter_safe`.
- `scripts/run_openclaw_local_first_e2e.ps1` dry-run and live modes produce artifacts.
- Local-first firewall tests pass.

### Phase 2 - Beginner UX Reliability

Status: `todo`

Deliverables:

- Single command for “setup + firewall start + review + kill-switch check”.
- Guided remediation for top 5 failures:
  - `wallet_unlock_required`
  - `invalid_lemma_credential`
  - `insufficient_scope`
  - `runtime_inactive`
  - stale-proof/freshness errors
- “Safety status” output (`safe`, `degraded`, `unsafe`) in CLI and firewall health.

Acceptance:

- Clean machine success <= 10 minutes with no manual JSON edits.
- 90%+ success in scripted onboarding retries with remediation.

### Phase 3 - Enforcement Completion

Status: `todo`

Deliverables:

- Proof-required default on sensitive routes.
- Full claim verification coverage (signature, audience, site/resource binding, expiry/freshness, revocation, deny-by-default).
- Prompt-injection containment checks (`trust_state`, `taint_epoch`, step-up paths).

Acceptance:

- Conformance suite green:
  - `allow_valid`
  - `deny_missing_scope`
  - `deny_wrong_site`
  - `revoke_to_deny`
- Evidence attached to launch bundle.

### Phase 4 - Enterprise Controls

Status: `todo`

Deliverables:

- Policy profile management and approvals.
- Org-wide audit export and SIEM-friendly bundles.
- Team limits/quotas and higher-tier SLAs.
- Compatibility path sunset controls.

Acceptance:

- Enterprise drill runbook pass.
- Audit export validated by external consumer.

## Execution Tracker

Status values: `Not Started`, `In Progress`, `Done`.

| ID | Status | Priority | Task | Evidence |
|---|---|---|---|---|
| B0-1 | Done | P0 | Add local-first firewall E2E harness | `scripts/run_openclaw_local_first_e2e.ps1` |
| B0-2 | Done | P0 | Add local-first proof and freshness sync in firewall | `scripts/lemma_firewall.py`, `tests/test_openclaw_firewall_local_first.py` |
| B0-3 | Done | P0 | Add starter-safe security profile defaults in setup/start scripts | `scripts/setup_openclaw_authz_seconds.ps1`, `scripts/start_openclaw_firewall.ps1` |
| B1-1 | Done | P1 | Add one-command onboarding + firewall start wrapper | `scripts/run_openclaw_starter_safe.ps1` |
| B1-2 | Done | P1 | Add beginner “safety status” command/output | `scripts/run_openclaw_starter_safe.ps1` (`safe/degraded/unsafe` + evidence artifacts) |
| B2-1 | Not Started | P0 | Complete proof-required and binding checks on sensitive routes | pending |
| B2-2 | Not Started | P0 | Close revocation/freshness/deny-by-default gaps | pending |
| E1-1 | Not Started | P2 | Org policy packs + approvals | pending |
| E1-2 | Not Started | P2 | SIEM export and enterprise evidence bundle | pending |

## Weekly Metrics

- Onboarding success rate (first attempt and after remediation)
- Time to first “safe” status
- Proof-first coverage on protected routes
- Revoke-to-deny and kill-to-deny latency p95
- Beginner support ticket volume per 100 onboardings

## Exit Criteria (Beginner GA)

- One-command starter setup works from clean machine.
- Starter-safe profile is default and documented.
- Local-first guardrails active by default.
- Kill-switch and revoke paths verified with evidence.
- Beginner-facing remediation is clear and actionable.
