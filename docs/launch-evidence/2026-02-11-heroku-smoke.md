# Heroku Production Smoke Evidence (2026-02-11)

This run is a non-destructive production smoke check against `https://lemma.id`.

Raw output: `docs/launch-evidence/2026-02-11-heroku-smoke.txt`

## What Was Checked

- GET availability:
  - `/`
  - `/wallet/bridge`
  - `/api/revocation/bloom-filter`
  - `/api/v1/revocation/list`
- Bridge headers on `HEAD /wallet/bridge`
- Guardrail behavior with no auth context:
  - `POST /api/wallet/session-sync` (no cookie)
  - `POST /api/passkey/authenticate/begin`
  - `POST /api/passkey/register/begin` (no authenticated session)

## Observed Results

- Availability:
  - All checked GET endpoints returned `200`.
- Revocation endpoints:
  - Both returned `success=True` with `count=2` at test time.
- Bridge security/cache headers:
  - `Cache-Control: public, max-age=31536000, immutable`
  - `X-Frame-Options: ALLOWALL`
  - `Content-Security-Policy` present with `frame-ancestors` restrictions.
- Guardrails:
  - Session sync without cookie returned `403` (expected denial).
  - Passkey register begin without authenticated state returned `401`.
  - Passkey authenticate begin returned `200` and challenge payload.

## Interpretation for Launch Gate

- Confirms baseline production availability for key auth/revocation read paths.
- Confirms at least some unauthenticated access controls are active.
- Does **not** satisfy full P0 test evidence requirements (SDK/browser flows, cross-site flows, error-path matrix, CI-gated regression suite still pending).

