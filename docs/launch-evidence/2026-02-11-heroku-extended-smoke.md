# Heroku Extended Smoke Evidence (2026-02-11)

This run extends production checks with additional transport/security header and guardrail validation.

Raw output: `docs/launch-evidence/2026-02-11-heroku-extended-smoke.txt`

## Validated in Production (`https://lemma.id`)

- `HEAD /` returned `200`.
- Transport/security headers observed on root:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - `Content-Security-Policy` present
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- `HEAD /wallet/bridge` returned `200` with:
  - `Cache-Control: public, max-age=31536000, immutable`
  - `X-Frame-Options: ALLOWALL`
  - CSP with `frame-ancestors` restriction
- Revocation endpoints:
  - `GET /api/revocation/bloom-filter` returned `200`
  - `GET /api/v1/revocation/list` returned `200`, `success=true`, `count=2`
  - `GET /api/wallet/revocation-status?...` returned `200`, `success=true`
- Unauthenticated guardrails:
  - `POST /api/wallet/session-sync` returned `403`
  - `POST /api/passkey/register/begin` returned `401`
  - `POST /api/passkey/authenticate/begin` returned `200` challenge response

## Launch-Gate Interpretation

- Confirms baseline transport and key response headers for core public/auth paths.
- Confirms additional non-destructive API behavior relevant to P0-1/P0-2.
- Does not replace full security control sign-off or complete E2E/browser test evidence.

