# GA Gate Status Tracker

This is the live GA gate sheet for Lemma.id launch approval.

Rules:
- GA requires all P0 gates in `PASS`.
- Any P0 gate in `FAIL`, `UNKNOWN`, or `IN_PROGRESS` is a launch blocker.
- Every gate entry must include owner and evidence artifact path.

Last updated: 2026-06-08

## P0 Gates

| Gate | Status | Owner | Evidence | Blocking Gap |
|---|---|---|---|---|
| P0-1 Security Controls Sign-off | IN_PROGRESS | Security Lead | `docs/security/SECURITY_CHECKLIST.md` | Formal security sign-off and closure plan for non-PASS controls |
| P0-2 End-to-End Test Execution Evidence | IN_PROGRESS | QA Lead | `docs/status/SOLO_GA_TEST_EXECUTION_SHEET.md`, `docs/testing/FULL_TEST_SUITE.md` | Manual critical flows still missing evidence |
| P0-3 CI Release Gate for Auth/Security Paths | PASS | Platform/DevOps | `.github/workflows/auth-launch-gate.yml`, `.github/workflows/launch-gate-smoke.yml` | Strict workflow added with required secret check and non-skippable scope matrix gate |
| P0-4 Revocation Data Path Completeness | IN_PROGRESS | Backend Lead | `ops/evidence/launch/2026-06-08-revoke-to-deny-evidence.md`, `scripts/revoke_to_deny_smoke.py` | Prod smoke blocked `ppid_not_linked`; re-run with linked wallet for PASS |
| P0-5 Passkey Algorithm Handling Correctness | IN_PROGRESS | Auth Lead | `ops/evidence/launch/2026-06-08-passkey-browser-matrix.md` | Fill Chrome/Firefox/Safari matrix with screenshots |
| P0-6 Independent Security Assessment | BLOCKED | Security Lead | `ops/evidence/launch/2026-06-08-external-pentest-scope.md` | Vendor report + remediation tracker not attached |
| P0-7 Operational Readiness | IN_PROGRESS | SRE Lead | `ops/evidence/launch/2026-06-08-incident-drill-csp-alert.md`, `ops/evidence/launch/2026-03-04-114534-incident-drill-auth-control-plane.md` | Attach Sentry event id from CSP drill; auth control-plane drill already present |

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
