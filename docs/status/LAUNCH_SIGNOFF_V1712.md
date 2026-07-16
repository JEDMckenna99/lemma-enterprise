# Lemma.id Launch Sign-off: v1712

Date: 2026-02-14  
Environment: Production (`https://lemma.id`)  
Release: Heroku `v1712`

## Executive Decision
**Historical release sign-off (v1712)** for passkey SSO + login + IAM delegation foundation.
This document reflects the release state at the time it was written and should not be treated as a current global readiness claim.

## Validation Summary

### 1) Production test gates
- `node mcp-server/run-tests.js` → **39/39 passed (100%)**
- `node mcp-server/run-interaction-tests.js` → **19/19 passed (100%)**

### 2) Revocation regression (critical)
- `node mcp-server/run-revocation-regression.js` → **PASS**
- Verified flow: **issue → validate → revoke → deny**
- Verified denied response remains machine-readable (`invalid_token`) on validate endpoint after revoke.

### 3) Auth contract hardening status
- Canonical auth error semantics in core paths are in place (`auth_required`, `invalid_token`, `missing_scope`, etc.).
- Lemma-bound admin token path implemented for delegated issuance/revocation machine flow.
- Scope/permission normalization centralized in auth layer.

## What shipped in this launch hardening cycle
- Auth preflight hard-stop in test harnesses
- Scope/permission canonicalization helpers
- Agent session/token auth code normalization
- Delegation issuance/revocation consistency fixes
- Revocation regression harness automation

## Residual risks (non-blocking for launch)
1. Some auth-adjacent endpoints may still need a final consistency sweep for machine-code parity.
2. Heroku build logs include Python runtime deprecation guidance (`runtime.txt` -> `.python-version`) and patch update advisory.

## Rollback Runbook (fast path)

### A) Roll back app release on Heroku
1. View recent releases:
   - `heroku releases -a lemma-enterprise`
2. Roll back to prior stable release:
   - `heroku rollback v1711 -a lemma-enterprise`
   - (or chosen known-good version)
3. Verify health:
   - `curl https://lemma.id/health`
   - rerun test gates (`run-tests.js`, `run-interaction-tests.js`)

### B) Emergency auth containment
1. Revoke any active delegated credentials from admin dashboard/API.
2. Rotate admin-scoped agent tokens used during launch validation.
3. If needed, temporarily tighten issuance policy via env/config and redeploy.

### C) Post-rollback validation
- Confirm admin and developer pages load.
- Confirm `/api/agent/validate` and `/api/agent/credentials` behavior matches expected auth contract.
- Re-run revocation regression before re-promoting release.

## Operational recommendation
- Proceed with launch announcement.
- Schedule a short post-launch hardening pass for endpoint-wide error-code parity and runtime file cleanup (`.python-version` migration).
