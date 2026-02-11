# Lemma.id GA Launch Readiness Checklist

Objective launch gate for Lemma.id general availability (GA).  
Use this document as a pass/fail control sheet, not a roadmap narrative.

---

## Launch Decision Rules

- GA is approved only if all P0 items are marked `PASS`.
- Any P0 item in `FAIL`, `UNKNOWN`, or `IN_PROGRESS` blocks GA.
- P1 items may remain open only with a documented risk acceptance and target remediation date.
- All evidence links must point to reproducible artifacts (test logs, screenshots, reports, dashboards, commit SHAs).

---

## Scope Baseline (Must Be True for Claims)

- Product scope: passkey-based wallet auth, local VC/lemma verification, cross-site SSO flow, revocation checking, site-unique identities (PPID model).
- Deployment scope: production `lemma.id` stack and supported SDK/browser versions.
- Security posture claims must match deployed behavior, not planned capabilities.

Status: `UNKNOWN`  
Owner: __________  
Target Date: __________  
Evidence: __________

---

## Latest Verification Run

- Date: 2026-02-11
- Environment: production `https://lemma.id` (Heroku deploy)
- Type: non-destructive smoke checks
- Evidence:
  - `docs/launch-evidence/2026-02-11-heroku-smoke.md`
  - `docs/launch-evidence/2026-02-11-heroku-smoke.txt`
  - `docs/launch-evidence/2026-02-11-heroku-extended-smoke.md`
  - `docs/launch-evidence/2026-02-11-heroku-extended-smoke.txt`
  - `docs/launch-evidence/2026-02-11-transport-tls-checks.md`
  - `docs/launch-evidence/2026-02-11-transport-tls-checks.txt`
  - `docs/launch-evidence/2026-02-11-origin-cors-checks.txt`
  - `docs/launch-evidence/2026-02-11-origin-and-dom-safety-checks.md`
  - `docs/launch-evidence/2026-02-11-code-remediation.md`
  - `docs/launch-evidence/2026-02-11-post-remediation-scan.md`
  - `docs/launch-evidence/2026-02-11-post-fix-smoke-current-prod.txt`
  - `docs/launch-evidence/2026-02-11-130201-post-deploy-summary.md`
  - `docs/launch-evidence/2026-02-11-130201-post-deploy-smoke.txt`
  - `docs/launch-evidence/2026-02-11-130201-post-deploy-transport.txt`
  - `docs/launch-evidence/2026-02-11-130201-post-deploy-origin.txt`
  - `docs/launch-evidence/2026-02-11-ci-gate-setup.md`
  - `docs/launch-evidence/2026-02-11-launch-gate-ci-local.txt`
- Coverage in this run:
  - core endpoint availability
  - transport/security header validation on root + bridge
  - HTTP to HTTPS redirect enforcement check
  - TLS version behavior checks (reject <=1.1, accept 1.2)
  - allowed vs disallowed origin CORS behavior on passkey auth endpoint
  - static scan evidence for `eval`/`innerHTML` usage patterns
  - repository code remediation for passkey/revocation/frontend safety blockers
  - post-deploy verification automation run (scripted)
  - bridge security/cache headers
  - revocation status endpoint behavior
  - unauthenticated guardrail behavior on selected auth/session APIs
  - CI gate scaffolding with local validation

---

## P0 Launch Gates (Blocking)

### P0-1 Security Controls Sign-off

- Requirement:
  - Complete `docs/SECURITY_CHECKLIST.md` with explicit pass/fail per control.
  - Record compensating controls for any partial implementation.
- Pass Criteria:
  - 100 percent of required controls marked and reviewed.
  - No critical control left `TBD`.
- Current Known Gap:
  - Checklist now has explicit statuses, but many controls remain `IN_PROGRESS`/`UNKNOWN` and need formal sign-off.

Status: `IN_PROGRESS`  
Owner: Security Lead  
Target Date: __________  
Evidence:
- Partial production validation:
  - `docs/launch-evidence/2026-02-11-heroku-smoke.md`
  - `docs/launch-evidence/2026-02-11-heroku-extended-smoke.md`
- Control status baseline:
  - `docs/SECURITY_CHECKLIST.md`
- Remaining requirement: security lead review and sign-off with closure plan for `UNKNOWN`/`IN_PROGRESS` controls

### P0-2 End-to-End Test Execution Evidence

- Requirement:
  - Execute critical flows from `docs/FULL_TEST_SUITE.md` in production-like environment.
  - Capture artifacts for each test group: API, SDK, bridge, cross-site flows, error handling.
- Pass Criteria:
  - All critical tests pass or have approved exceptions.
  - Failures have linked fixes and rerun evidence.
- Current Known Gap:
  - Test plan exists, but execution checklist is not completed.

Status: `IN_PROGRESS`  
Owner: QA Lead  
Target Date: __________  
Evidence:
- Smoke/guardrail artifacts:
  - `docs/launch-evidence/2026-02-11-heroku-smoke.md`
  - `docs/launch-evidence/2026-02-11-130201-post-deploy-summary.md`
- Remaining requirement: full browser flow execution and reruns across all critical scenarios in `docs/FULL_TEST_SUITE.md`

### P0-3 CI Release Gate for Auth/Security Paths

- Requirement:
  - Add automated pre-release checks for security-critical paths.
  - Minimum: smoke tests, credential verification tests, revocation tests, passkey auth tests.
- Pass Criteria:
  - CI must fail build on any regression in P0 scenarios.
  - Required checks must pass before deploy tag/release.
- Current Known Gap:
  - Smoke gate exists, but coverage is still limited and CI run history evidence is pending.

Status: `IN_PROGRESS`  
Owner: Platform/DevOps  
Target Date: __________  
Evidence:
- `.github/workflows/launch-gate-smoke.yml`
- `scripts/launch_gate_smoke_ci.py`
- `docs/launch-evidence/2026-02-11-ci-gate-setup.md`
- `docs/launch-evidence/2026-02-11-launch-gate-ci-local.txt`
- Remaining requirement: successful CI runner executions (target: last 3 green runs)

### P0-4 Revocation Data Path Completeness

- Requirement:
  - Ensure revocation actions update the active revocation data path used by verifiers.
  - Remove or close TODOs in production revocation flow.
- Pass Criteria:
  - Revoked credential is consistently rejected across clients after sync SLA.
  - Verified by automated and manual tests.
- Current Known Gap:
  - Code path is remediated in repository; deployed environment still needs post-deploy revocation propagation validation.

Status: `IN_PROGRESS`  
Owner: Backend Lead  
Target Date: __________  
Evidence:
- `docs/launch-evidence/2026-02-11-code-remediation.md`
- Remaining requirement: post-deploy propagation test evidence (revoke -> sync -> deny across clients)

### P0-5 Passkey Algorithm Handling Correctness

- Requirement:
  - Resolve algorithm handling TODO in passkey registration/auth handling.
  - Validate behavior across supported authenticators/browsers.
- Pass Criteria:
  - Algorithm metadata is derived/validated correctly in all supported scenarios.
  - No hardcoded placeholder for algorithm in production response paths.
- Current Known Gap:
  - Code no longer uses hardcoded algorithm placeholder, but cross-browser/device matrix validation is still pending.

Status: `IN_PROGRESS`  
Owner: Auth Lead  
Target Date: __________  
Evidence:
- `docs/launch-evidence/2026-02-11-code-remediation.md`
- Remaining requirement: supported authenticator/browser matrix report

### P0-6 Independent Security Assessment

- Requirement:
  - External security review or penetration test covering wallet, bridge, passkey, revocation, and cross-site flow.
- Pass Criteria:
  - No unresolved critical/high findings.
  - Medium findings have accepted remediation timeline.

Status: `UNKNOWN`  
Owner: Security Lead  
Target Date: __________  
Evidence: final report + remediation tracker

### P0-7 Operational Readiness (Incident + Monitoring)

- Requirement:
  - On-call runbook for auth outages and security incidents.
  - Monitoring/alerting for auth success rate, revocation sync health, bridge errors, passkey failure rates.
- Pass Criteria:
  - Alert thresholds set and tested.
  - Simulated incident drill completed.

Status: `IN_PROGRESS`  
Owner: SRE Lead  
Target Date: __________  
Evidence: basic production availability and header checks captured in `docs/launch-evidence/2026-02-11-heroku-smoke.md`; monitoring/drill evidence still required

---

## P1 Strongly Recommended (Non-Blocking with Risk Acceptance)

### P1-1 Browser/Device Compatibility Matrix

- Define officially supported browser versions and authenticator classes.
- Run matrix tests and document known limitations.

Status: `UNKNOWN`  
Owner: QA Lead  
Target Date: __________  
Evidence: matrix report

### P1-2 Claims and Documentation Alignment

- Ensure whitepaper, integration docs, and marketing pages only claim deployed features.
- Separate "deployed", "available in codebase", and "planned".

Status: `IN_PROGRESS`  
Owner: Product + Security  
Target Date: __________  
Evidence: docs diff + approval

### P1-3 Privacy/Compliance Artifact Pack

- Prepare DPA/privacy statements and data flow diagrams for enterprise buyers.
- Include PPID/site-uniqueness explanation and retention policy.

Status: `UNKNOWN`  
Owner: Legal + Product  
Target Date: __________  
Evidence: approved policy docs

---

## Recommended Timeline (Example)

- Day 0-2:
  - Close P0-4 and P0-5 implementation TODOs.
  - Stand up CI release gates (P0-3).
- Day 3-5:
  - Execute full test suite and collect evidence (P0-2).
  - Complete security checklist and internal sign-off (P0-1).
- Day 6-10:
  - External security review and remediation pass (P0-6).
  - Operational readiness drill and dashboard validation (P0-7).
- GA Decision:
  - Run final gate review; approve only when all P0 are `PASS`.

## Execution Runbook

- Post-deploy validation procedure:
  - `docs/POST_DEPLOY_LAUNCH_VERIFICATION.md`
- Deployment release checklist:
  - `docs/DEPLOYMENT_RELEASE_CHECKLIST.md`
- Automation script:
  - `scripts/post_deploy_launch_gate.ps1`

---

## GA Decision Record

- Decision Date: __________
- Decision: `GO` / `NO-GO`
- Approved By: __________
- Notes: __________

---

## Optional: Controlled Beta Exit Criteria

If running beta before GA, define strict limits:

- Traffic cap: __________
- Allowed relying parties: __________
- SLA expectations: Beta only, best effort
- Must-have beta controls:
  - Revocation propagation validated in pilot tenants
  - Passkey error rate below threshold
  - No unresolved critical security issues

