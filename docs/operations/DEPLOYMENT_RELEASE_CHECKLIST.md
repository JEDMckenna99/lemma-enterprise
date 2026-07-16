# Lemma.id Deployment Release Checklist

Use this checklist for each production deployment to `lemma.id`.

## 0) CI Auth Launch Gate (authoritative)

Every push to `main` runs [`.github/workflows/auth-launch-gate.yml`](../../.github/workflows/auth-launch-gate.yml). Treat a green run as the deploy gate of record.

The workflow:

1. Runs local security gates (CSP pytest + auth scope matrix generation/review).
2. Waits for production deploy health.
3. Runs strict post-deploy launch gate with scope-matrix enforcement.

Required GitHub Actions secret:

- `LEMMA_PLATFORM_API_KEY`, live scope-matrix and post-deploy gates (falls back to `LEMMA_API_KEY`).

Local preflight (mirrors CI scope matrix step):

```powershell
python scripts/generate_auth_scope_matrix.py
python scripts/review_auth_scope_matrix.py --strict-state-changing
```

## 1) Pre-Deploy

- Confirm environment safety for the target Heroku app:
  - Staging:
    - `powershell -ExecutionPolicy Bypass -File scripts/check_heroku_env_parity.ps1 -AppName <staging-app> -Environment staging -LocalEnvFile .env.local`
  - Production:
    - `powershell -ExecutionPolicy Bypass -File scripts/check_heroku_env_parity.ps1 -AppName <production-app> -Environment production`
- Confirm launch-gate blockers addressed in code:
  - `api/passkey_auth.py` (algorithm placeholder removed)
  - `api/wallet_revocation.py` (immediate revocation sync path)
  - frontend safety updates in templates/JS
- Run local syntax checks:
  - `python -m py_compile api/passkey_auth.py api/wallet_revocation.py`
- Run smoke checks against current production baseline:
  - `python scripts/launch_gate_smoke_ci.py`
- Ensure checklist/docs are current:
  - `docs/status/GA_LAUNCH_READINESS_CHECKLIST.md`
  - `docs/security/SECURITY_CHECKLIST.md`

## 2) Deploy

- Deploy to Heroku app backing `lemma.id`.
- Record deploy metadata:
  - git commit SHA
  - deploy timestamp
  - responsible operator

## 3) Post-Deploy Automated Verification

Run (same bundle as CI auth launch gate):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/post_deploy_launch_gate.ps1 `
  -BaseUrl https://lemma.id `
  -PlatformApiKey $env:LEMMA_PLATFORM_API_KEY `
  -StrictScopePolicy `
  -RequirePlatformApiKey
```

Default MCP-free bundle (can also be run directly):

`powershell -ExecutionPolicy Bypass -File scripts/run_cli_api_proof_regression.ps1 -LemmaUrl https://lemma.id`

Expected:

- Auth launch gate / scope matrix review passes
- Smoke checks pass
- Redirect check success
- TLS <=1.1 check fails (expected)
- TLS1.2 check succeeds
- Origin/CORS checks produce expected header behavior

Capture generated evidence files in `ops/evidence/launch/`.

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
  - `docs/status/GA_LAUNCH_READINESS_CHECKLIST.md`
  - `docs/security/SECURITY_CHECKLIST.md`
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
- Annotate rollback reason and evidence in `ops/evidence/launch/`.

