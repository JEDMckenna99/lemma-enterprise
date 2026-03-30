# Lemma.id GA Launch Readiness Checklist

Objective launch gate for Lemma.id general availability (GA).  
Use this document as a pass/fail control sheet, not a roadmap narrative.

---

## Launch Decision Rules

- GA is approved only if all P0 items are marked `PASS`.
- Any P0 item in `FAIL`, `UNKNOWN`, or `IN_PROGRESS` blocks GA.
- P1 items may remain open only with a documented risk acceptance and target remediation date.
- All evidence links must point to reproducible artifacts (test logs, screenshots, reports, dashboards, commit SHAs).
- Status normalization source of truth: `docs/status/GA_GATE_STATUS.md`.

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

- Date: 2026-03-04
- Environment: production `https://lemma.id` (Heroku deploy)
- Deployment Version: production current at run time (see evidence artifacts)
- Type: post-deploy launch gate verification + incident drill
- Evidence:
  - `ops/evidence/launch/2026-03-04-114217-ga-launch-gate-smoke.txt`
  - `ops/evidence/launch/2026-03-04-114520-post-deploy-summary.md`
  - `ops/evidence/launch/2026-03-04-114534-incident-drill-auth-control-plane.md`
  - Strict scope policy output: `admin routes missing explicit admin auth: 0`
  - Strict scope policy output: `state-changing routes missing explicit auth: 0`
  - Proof exchange baseline checks passed
- Current launch sheet:
  - `docs/status/GA_GATE_STATUS.md`
- Coverage in this run:
  - core endpoint availability
  - transport/security header validation on root + bridge
  - HTTP to HTTPS redirect enforcement check
  - TLS version behavior checks (reject <=1.1, accept 1.2)
  - allowed vs disallowed origin CORS behavior on passkey auth endpoint
  - static scan evidence for `eval`/`innerHTML` usage patterns
  - repository code remediation for passkey/revocation/frontend safety blockers
  - post-deploy verification automation run (scripted)
  - deployed-release verification on Heroku `v1682`
  - full token-driven UX automation (comprehensive + interaction suites) passed
  - bridge security/cache headers
  - revocation status endpoint behavior
  - unauthenticated guardrail behavior on selected auth/session APIs
  - CI gate scaffolding with local validation

---

## P0 Launch Gates (Blocking)

### P0-1 Security Controls Sign-off

- Requirement:
  - Complete `docs/security/SECURITY_CHECKLIST.md` with explicit pass/fail per control.
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
  - `ops/evidence/launch/2026-02-11-heroku-smoke.md`
  - `ops/evidence/launch/2026-02-11-heroku-extended-smoke.md`
- Control status baseline:
  - `docs/security/SECURITY_CHECKLIST.md`
- Remaining requirement: security lead review and sign-off with closure plan for `UNKNOWN`/`IN_PROGRESS` controls

### P0-2 End-to-End Test Execution Evidence

- Requirement:
  - Execute critical flows from `docs/testing/FULL_TEST_SUITE.md` in production-like environment.
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
  - `ops/evidence/launch/2026-03-04-114217-ga-launch-gate-smoke.txt`
  - `ops/evidence/launch/2026-03-04-114520-post-deploy-summary.md`
- Full browser/token automation artifacts:
  - `ops/evidence/launch/2026-02-11-agent-token-ux-automation.md`
  - `ops/evidence/launch/2026-02-11-agent-ux-suite-full-pass.txt`
  - `ops/evidence/launch/2026-02-11-agent-ux-suite-interaction-pass.txt`
- Remaining requirement: execute manual critical scenarios from `docs/testing/FULL_TEST_SUITE.md` and attach screenshots/logs for sign-off

### P0-3 CI Release Gate for Auth/Security Paths

- Requirement:
  - Add automated pre-release checks for security-critical paths.
  - Minimum: smoke tests, credential verification tests, revocation tests, passkey auth tests.
- Pass Criteria:
  - CI must fail build on any regression in P0 scenarios.
  - Required checks must pass before deploy tag/release.
- Current Known Gap:
  - No current blocker for baseline auth gate coverage. Expand over time as new critical paths are added.

Status: `PASS`  
Owner: Platform/DevOps  
Target Date: __________  
Evidence:
- `.github/workflows/auth-launch-gate.yml`
- `.github/workflows/launch-gate-smoke.yml`
- `scripts/post_deploy_launch_gate.ps1`
- `scripts/proof_exchange_contract_check.py`
- `scripts/auth_scope_matrix_check.py`
- Strict workflow enforces required secret check and `-RequirePlatformApiKey` gate behavior (no silent skip).

### P0-4 Revocation Data Path Completeness

- Requirement:
  - Ensure revocation actions update the active revocation data path used by verifiers.
  - Remove or close TODOs in production revocation flow.
- Pass Criteria:
  - Revoked credential is consistently rejected across clients after sync SLA.
  - Verified by automated and manual tests.
- Current Known Gap:
  - Persistence/visibility now validated on production, but end-user deny-path validation across clients is still pending.

Status: `IN_PROGRESS`  
Owner: Backend Lead  
Target Date: __________  
Evidence:
- `ops/evidence/launch/2026-02-11-code-remediation.md`
- `ops/evidence/launch/2026-02-11-revocation-path-post-deploy.md`
- `ops/evidence/launch/2026-02-11-revocation-path-post-dbfix.md`
- Active route fixed in `api/services/wallet_service.py` and deployed (`v1679`)
- Remaining requirement: revoke -> client sync -> credential deny evidence across supported clients

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
- `ops/evidence/launch/2026-02-11-code-remediation.md`
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
Evidence:
- `monitoring/UPTIME_MONITORING_SETUP.md`
- `monitoring/SENTRY_SETUP_GUIDE.md`
- `docs/operations/INCIDENT_DRILL_RUNBOOK.md`
- `monitoring/UPTIME_MONITORING_SETUP.md`
- `scripts/run_sentry_alert_routing_drill.py`
- `ops/evidence/launch/2026-03-04-114534-incident-drill-auth-control-plane.md` (MTTD=6s, MTTR=10s)
- Remaining requirement: attach on-call escalation routing outcome from a live alert path test

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
  - `docs/operations/POST_DEPLOY_LAUNCH_VERIFICATION.md`
- Deployment release checklist:
  - `docs/operations/DEPLOYMENT_RELEASE_CHECKLIST.md`
- Solo operator execution sheet:
  - `docs/status/SOLO_GA_TEST_EXECUTION_SHEET.md`
- Agent monitoring API (custom dashboard integration):
  - `docs/operations/AGENT_MONITORING_API.md`
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

