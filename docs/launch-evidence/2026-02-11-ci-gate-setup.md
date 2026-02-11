# CI Gate Setup Evidence (2026-02-11)

## Goal

Establish a low-risk, non-destructive CI gate for P0-3 (release gating on critical auth/revocation regressions).

## Added Artifacts

- Workflow: `.github/workflows/launch-gate-smoke.yml`
- CI smoke script: `scripts/launch_gate_smoke_ci.py`
- Local execution output: `docs/launch-evidence/2026-02-11-launch-gate-ci-local.txt`

## Scope of Checks

- Endpoint availability:
  - `/`
  - `/wallet/bridge`
  - `/api/revocation/bloom-filter`
  - `/api/v1/revocation/list`
- Bridge header checks:
  - `cache-control` present
  - `content-security-policy` present with `frame-ancestors`
  - `x-frame-options` logged (informational)
- Guardrail behavior without auth context:
  - `POST /api/wallet/session-sync` expects `401/403`
  - `POST /api/passkey/register/begin` expects `401/403`
  - `POST /api/passkey/authenticate/begin` expects `200` + success payload

## Local Validation Result

- Run completed with all assertions passing.
- This validates the check logic before CI runner execution.

## Remaining Work

- Confirm first successful execution on GitHub Actions runner.
- Expand gate coverage with additional SDK/browser flow checks as separate jobs.

