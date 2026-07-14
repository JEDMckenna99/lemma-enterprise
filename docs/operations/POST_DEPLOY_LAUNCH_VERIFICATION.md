# Post-Deploy Launch Verification Runbook

Use this runbook immediately after deploying launch-gate remediations to Heroku.

## Purpose

Provide a repeatable, non-destructive verification process that confirms:

- core auth/revocation endpoints are healthy,
- transport and header controls are still enforced,
- CORS/origin behavior remains constrained,
- auth scope matrix policy is unchanged,
- launch evidence is captured for the GA gate.

## Authoritative CI gate

[`.github/workflows/auth-launch-gate.yml`](../../.github/workflows/auth-launch-gate.yml) runs on every push to `main` and is the deploy gate of record. Manual runs below should mirror that workflow.

Required GitHub Actions secret: `LEMMA_PLATFORM_API_KEY` (falls back to `LEMMA_API_KEY`).

## Prerequisites

- Deployment completed to the `lemma.id` Heroku app.
- Workspace at repository root.
- Python available for `scripts/launch_gate_smoke_ci.py`.
- PowerShell available (Windows runner/local shell).
- `LEMMA_PLATFORM_API_KEY` set locally for strict scope-matrix enforcement.

## Command

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/post_deploy_launch_gate.ps1 `
  -BaseUrl https://lemma.id `
  -PlatformApiKey $env:LEMMA_PLATFORM_API_KEY `
  -StrictScopePolicy `
  -RequirePlatformApiKey
```

Scope matrix preflight (also run in CI before post-deploy):

```powershell
python scripts/generate_auth_scope_matrix.py
python scripts/review_auth_scope_matrix.py --strict-state-changing
```

## Output Artifacts

The script writes timestamped artifacts to `ops/evidence/launch/`:

- `*-post-deploy-smoke.txt`
- `*-post-deploy-transport.txt`
- `*-post-deploy-origin.txt`
- `*-post-deploy-summary.md`

## Acceptance Criteria

- Scope matrix review passes (`--strict-state-changing`).
- Smoke checks pass (script returns success).
- HTTP traffic is redirected to HTTPS.
- TLS <=1.1 handshake fails; TLS1.2 succeeds.
- Passkey auth begin endpoint:
  - allowed origin returns expected ACAO/ACAC on `POST`,
  - disallowed origin does not receive credentialed ACAO on `POST`.

## Required Manual Validation (still needed for GA)

- Passkey browser/device compatibility matrix:
  - verify `wallet_storage.algorithm` is populated where browser provides algorithm metadata.
- Revocation propagation:
  - execute revoke -> sync -> deny test flow on deployed build and store evidence.
- Security sign-off:
- review `docs/security/SECURITY_CHECKLIST.md` and close remaining `IN_PROGRESS`/`UNKNOWN` controls.

## Evidence Linking

After each run, update:

- `docs/status/GA_LAUNCH_READINESS_CHECKLIST.md` (latest verification run + P0 statuses),
- `docs/security/SECURITY_CHECKLIST.md` (control statuses and notes).
