# Solo GA Test Execution Sheet

Use this as the single-operator checklist before declaring GA.

Gate normalization source of truth: `docs/status/GA_GATE_STATUS.md`

Operator: __________  
Date: 2026-06-08 (security hardening program)  
Target deploy: lemma-enterprise / https://lemma.id

---

## Security hardening program (2026-06-08)

Automated evidence from Phases A–D (see `lemma-security-hardening-plan.canvas.tsx`):

| Phase | Result | Evidence |
|-------|--------|----------|
| A, ishuman_cache encryption | Code complete | `ops/evidence/launch/*-phase-a-summary.md`, `tests/test_ishuman_cache_encryption.py` |
| B, revoke→deny smoke | Script ready; prod blocked `ppid_not_linked` | `ops/evidence/launch/2026-06-08-revoke-to-deny-evidence.md`, `scripts/revoke_to_deny_smoke.py` |
| C, route CSP + innerHTML | Code complete | `ops/evidence/launch/*-phase-c-summary.md`, `tests/test_csp_security.py` |
| D, CSP alert drill | PASS | `ops/evidence/launch/2026-06-08-incident-drill-csp-alert.md` |

- [x] Deploy security hardening to prod (v2186 / `78d52f68`).
  - Result: `PASS`
  - Evidence: `ops/evidence/launch/2026-06-08-security-hardening-deploy-summary.md`, `ops/evidence/launch/2026-06-08-213645-post-deploy-summary.md`

---

## Rules

- Mark each step `PASS` / `FAIL`.
- Attach evidence artifact path for each step.
- If any P0 step is `FAIL`, final decision is `NO-GO`.

---

## P0-1 Security Controls Sign-off

- [x] Review `docs/security/SECURITY_CHECKLIST.md` and update statuses based on current run.
  - Result: `PASS` / `FAIL` (currently IN_PROGRESS - final sign-off pending)
  - Evidence: `docs/security/SECURITY_CHECKLIST.md`
- [ ] Confirm no critical controls are still untested without owner/date.
  - Result: `PASS` / `FAIL`
  - Evidence: __________

---

## P0-2 End-to-End Execution

- [x] Run automated UX suites with current admin token:
  - `node mcp-server/run-tests.js`
  - `node mcp-server/run-interaction-tests.js`
  - Result: `PASS`
  - Evidence:
    - `ops/evidence/launch/2026-02-11-agent-ux-suite-full-pass.txt`
    - `ops/evidence/launch/2026-02-11-agent-ux-suite-interaction-pass.txt`
    - `ops/evidence/launch/2026-02-11-agent-token-ux-automation.md`

- [ ] Manual critical flow: passkey login + wallet unlock + auth on relying site.
  - Result: `PASS` / `FAIL`
  - Evidence: __________

- [ ] Manual critical flow: lock on `lemma.id` and verify remote invalidation behavior.
  - Result: `PASS` / `FAIL`
  - Evidence: __________

---

## P0-3 CI Release Gate

- [x] Confirm launch gate workflow exists:
  - `.github/workflows/launch-gate-smoke.yml`
  - Result: `PASS`
  - Evidence: `.github/workflows/launch-gate-smoke.yml`

- [ ] Record 3 consecutive green runs of required checks.
  - Result: `PASS` / `FAIL`
  - Evidence (run links or logs): __________

---

## P0-4 Revocation Data Path

- [x] Run post-deploy gate script:
  - `powershell -ExecutionPolicy Bypass -File scripts/post_deploy_launch_gate.ps1 -BaseUrl https://lemma.id`
  - Result: `PASS`
  - Evidence:
    - `ops/evidence/launch/2026-03-04-114520-post-deploy-summary.md`
    - `ops/evidence/launch/2026-03-04-114217-ga-launch-gate-smoke.txt`

- [ ] Run revocation deny-path manual UX test:
  - issue credential -> verify accepted -> revoke -> sync -> verify denied
  - do in at least 2 client contexts (two browsers or two devices)
  - Result: `PASS` / `FAIL`
  - Evidence: `scripts/revoke_to_deny_smoke.py` + `ops/evidence/launch/2026-06-08-revoke-to-deny-evidence.md` (re-run when PPID linked)

---

## P0-5 Passkey Algorithm + Compatibility

- [ ] Browser matrix run (minimum): Chrome, Firefox, Safari (if claimed support).
  - register, unlock, session extend, logout/relock
  - Result: `PASS` / `FAIL`
  - Evidence: __________

- [ ] Confirm algorithm metadata behavior:
  - where browser exposes algorithm, server response includes it
  - Result: `PASS` / `FAIL`
  - Evidence: __________

---

## P0-6 Independent Security Assessment

- [ ] External review/pentest report collected.
  - Result: `PASS` / `FAIL`
  - Evidence: __________

- [ ] No unresolved critical/high findings.
  - Result: `PASS` / `FAIL`
  - Evidence: __________

---

## P0-7 Operational Readiness

- [ ] Run one incident drill:
  - auth degradation alert
  - rollback execution
  - post-rollback verification
  - Result: `PASS`
  - Evidence: `ops/evidence/launch/2026-03-04-114534-incident-drill-auth-control-plane.md`

- [x] CSP violation alert drill completed.
  - Result: `PASS`
  - Evidence: `ops/evidence/launch/2026-06-08-incident-drill-csp-alert.md`

- [ ] Confirm alerting/dashboard signals for auth/revocation health.
  - Result: `PASS` / `FAIL`
  - Evidence: __________

---

## Token Hygiene (Required)

- [ ] Revoke/rotate any shared admin-scoped agent token used for testing.
  - Result: `PASS` / `FAIL`
  - Evidence: __________

---

## Final Decision

- P0-1: `PASS` / `FAIL`
- P0-2: `PASS` / `FAIL`
- P0-3: `PASS` / `FAIL`
- P0-4: `PASS` / `FAIL`
- P0-5: `PASS` / `FAIL`
- P0-6: `PASS` / `FAIL`
- P0-7: `PASS` / `FAIL`

Final decision: `GO` / `NO-GO`  
Signed: __________  
Timestamp: __________

