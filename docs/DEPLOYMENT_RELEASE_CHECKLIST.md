# Lemma.id Deployment Release Checklist

Use this checklist for each production deployment to `lemma.id`.

## 1) Pre-Deploy

- Confirm launch-gate blockers addressed in code:
  - `api/passkey_auth.py` (algorithm placeholder removed)
  - `api/wallet_revocation.py` (immediate revocation sync path)
  - frontend safety updates in templates/JS
- Run local syntax checks:
  - `python -m py_compile api/passkey_auth.py api/wallet_revocation.py`
- Run smoke checks against current production baseline:
  - `python scripts/launch_gate_smoke_ci.py`
- Ensure checklist/docs are current:
  - `docs/GA_LAUNCH_READINESS_CHECKLIST.md`
  - `docs/SECURITY_CHECKLIST.md`

## 2) Deploy

- Deploy to Heroku app backing `lemma.id`.
- Record deploy metadata:
  - git commit SHA
  - deploy timestamp
  - responsible operator

## 3) Post-Deploy Automated Verification

Run:

`powershell -ExecutionPolicy Bypass -File scripts/post_deploy_launch_gate.ps1 -BaseUrl https://lemma.id`

Expected:

- Smoke checks pass
- Redirect check success
- TLS <=1.1 check fails (expected)
- TLS1.2 check succeeds
- Origin/CORS checks produce expected header behavior

Capture generated evidence files in `docs/launch-evidence/`.

## 4) Post-Deploy Manual Validation

- Passkey registration/auth matrix (Chrome, Firefox, Safari where supported)
  - verify `wallet_storage.algorithm` is populated when browser provides metadata
- Revocation propagation flow:
  - revoke credential
  - sync revocations
  - verify credential rejection after propagation
- Admin dashboard quick checks:
  - open Admin Dashboard
  - run "Launch Gate Quick Check"
  - confirm all checks show `Pass`

## 5) Launch Gate Status Update

- Update:
  - `docs/GA_LAUNCH_READINESS_CHECKLIST.md`
  - `docs/SECURITY_CHECKLIST.md`
- Promote only evidence-backed controls from `IN_PROGRESS` to `PASS`.
- Keep unresolved controls as `IN_PROGRESS`/`UNKNOWN` with explicit owner/date.

## 6) Rollback Criteria

Rollback immediately if any of the following occur:

- Auth endpoints fail smoke checks
- passkey auth begin fails unexpectedly
- revocation endpoints fail or return malformed payloads
- critical CORS/header regressions

Rollback steps:

- Revert to prior stable release on Heroku.
- Re-run `scripts/post_deploy_launch_gate.ps1`.
- Annotate rollback reason and evidence in `docs/launch-evidence/`.

