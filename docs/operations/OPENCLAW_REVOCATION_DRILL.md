# OpenClaw Revocation Drill

## Objective

Verify that revoked delegated credentials are denied consistently and quickly.

## Steps

1. Issue a short-lived delegated token (`aud=openclaw`, `scope=["read"]`).
2. Validate token (`/api/agent/validate`) returns `valid: true`.
3. Revoke token via `/api/agent/credentials/<token_id>/revoke`.
4. Re-validate same token.
5. Record:
   - response code
   - machine error code (`token_revoked` expected when contract is fully normalized)
   - elapsed time between revoke and deny.

## Pass Criteria

- Token is denied after revoke.
- Deny response remains machine-parseable.
- Revoke-to-deny latency meets p95 target.
