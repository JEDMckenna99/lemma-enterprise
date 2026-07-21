# GA Gate Status Tracker

This is the live GA gate sheet for Lemma.id launch approval.

Rules:
- GA requires all P0 gates in `PASS`.
- Any P0 gate in `FAIL`, `UNKNOWN`, or `IN_PROGRESS` is a launch blocker.
- Every gate entry must include owner and evidence artifact path.

Last updated: 2026-07-14

## Scope note (2026-07-14)

This tracker covers **lemma.id GA launch** (wallet, isHuman, platform auth). It
does **not** certify Agent Ops enterprise packaging, see
[`docs/AGENT_OPS_READINESS.md`](../AGENT_OPS_READINESS.md) for that scope.

**Deploy gate of record:** [`.github/workflows/auth-launch-gate.yml`](../../.github/workflows/auth-launch-gate.yml)
(CSP pytest → auth scope matrix → deploy health wait → strict
`post_deploy_launch_gate.ps1` with `LEMMA_PLATFORM_API_KEY`). A green run on
`main` supersedes ad-hoc manual gate runs unless a hotfix bypass is explicitly
documented.

Reconciled conflicts:

| Topic | GA gate stance | Notes |
| ----- | -------------- | ----- |
| P0-3 CI release gate | PASS via `auth-launch-gate.yml` | Replaces informal `launch-gate-smoke.yml`-only checks |
| isHuman IDV rail | Didit default | Stripe Identity is legacy migration only |
| Network revocation | Retired | Site-block is the enforcement path; endpoints return HTTP 410 |
| Agent Ops readiness | Out of GA P0 scope | Tracked separately in `AGENT_OPS_READINESS.md` |

## P0 Gates

| Gate | Status | Owner | Evidence | Blocking Gap |
|---|---|---|---|---|
| P0-1 Security Controls Sign-off | IN_PROGRESS | Security Lead | `docs/security/SECURITY_CHECKLIST.md` (refreshed 2026-06-08: 24 PASS / 22 IN_PROGRESS / 14 UNKNOWN) | Security Lead sign-off + close remaining IN_PROGRESS/UNKNOWN per checklist §Sign-Off Blockers |
| P0-2 End-to-End Test Execution Evidence | IN_PROGRESS | QA Lead | `docs/status/SOLO_GA_TEST_EXECUTION_SHEET.md`, `docs/testing/FULL_TEST_SUITE.md` | Manual critical flows still missing evidence |
| P0-3 CI Release Gate for Auth/Security Paths | PASS | Platform/DevOps | `.github/workflows/auth-launch-gate.yml` (scope matrix + `LEMMA_PLATFORM_API_KEY` post-deploy gate) | Authoritative deploy gate on every `main` push |
| P0-4 Revocation Data Path Completeness | IN_PROGRESS | Backend Lead | `ops/evidence/launch/2026-03-18-212437-revoke-to-deny-evidence.md` (historical PASS), `ops/evidence/launch/2026-06-08-security-hardening-deploy-summary.md` | v2186 deployed; new list/bloom smoke blocked `ppid_not_linked`; historical deny-path PASS on 2026-03-18 |
| P0-5 Passkey Algorithm Handling Correctness | IN_PROGRESS | Auth Lead | `ops/evidence/launch/2026-06-08-passkey-browser-matrix.md` | Fill Chrome/Firefox/Safari matrix with screenshots |
| P0-6 Independent Security Assessment | BLOCKED | Security Lead | `ops/evidence/launch/2026-06-08-external-pentest-scope.md` | Vendor report + remediation tracker not attached |
| P0-7 Operational Readiness | PASS | SRE Lead | `ops/evidence/launch/2026-07-21-185850-section9-restore-drill.md`, `scripts/section9_prod_smoke.py`, `docs/operations/ALERT_CATALOG.md`, `docs/operations/SECTION9_OPERATIONAL_RELIABILITY.md` | Section 9 PASS on v2487; Sentry token drill remains operator-run per ALERT_CATALOG |

## P1 Gates (Risk-Acceptable for GA only with documented exception)

| Gate | Status | Owner | Evidence | Notes |
|---|---|---|---|---|
| P1-1 Browser/Device Compatibility Matrix | IN_PROGRESS | QA Lead | Matrix report (pending) | Must exist before broad public claims |
| P1-2 Claims and Documentation Alignment | IN_PROGRESS | Product + Security | docs diff + approver sign-off | Ensure deployed vs planned claims are separated |
| P1-3 Privacy/Compliance Artifact Pack | IN_PROGRESS | Legal + Product | Approved policy docs | Needed for enterprise procurement |

## Required Evidence Pack for GO

- `docs/status/GA_LAUNCH_READINESS_CHECKLIST.md` (all P0 marked PASS)
- `docs/status/SOLO_GA_TEST_EXECUTION_SHEET.md` (final signed run)
- Latest post-deploy gate output in `ops/evidence/launch/*post-deploy-summary.md`
- Latest incident drill evidence in `ops/evidence/launch/*incident-drill-auth-control-plane.md`
- Browser/passkey compatibility matrix report
- Independent security assessment report + remediation tracker

## Approval Record

- Decision: `GO` / `NO-GO`
- Date: __________
- Approved by: __________
- Notes: __________
