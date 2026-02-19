# Developer Auth Contract v1

Date: 2026-02-19
Owner: Lemma.id

Machine-readable contract:
- `docs/DEVELOPER_AUTH_CONTRACT_V1.openapi.json`

## 1) Lemma vs Token (Different Roles)

- **Lemma**: cryptographic claim (who/what/where) signed by trusted issuer.
- **Access token**: short-lived runtime credential for controlled API actions.

Lemmas are not just another machine token format. Their utility is the proof itself:
issuer trust, site binding, permission claim, and revocation-aware verification.

## 2) Canonical External Flow

1. Client obtains a lemma (wallet/issuer flow).
2. Client calls `POST /api/auth/exchange-proof` with the proof.
3. Server verifies trust/signature/revocation/site/scope and returns:
   - `access_token` (`lm_at_...`, short-lived)
   - optional `refresh_token` in future versions
4. Client uses `Authorization: Bearer <access_token>` for controlled actions.

## 3) Control-Plane Endpoints

- `POST /api/auth/exchange-proof`
  - Input: `credential`, optional `site_id`, optional `requested_scope`, optional `ttl_seconds`
  - Output: `access_token`, `token_type`, `expires_in`, `site_id`, `scope`, `permission_id`

- `POST /api/auth/introspect` (requires API key)
  - Input: `token`, optional `site_id`
  - Output: `introspection.active` + claims metadata or error

- `POST /api/auth/revoke` (requires API key)
  - Input: `token` or `jti`, optional `reason`
  - Output: `revoked: true` and revocation metadata

## 4) Status Code Contract

- `400`: malformed request (missing required fields)
- `401`: invalid/expired/revoked token or invalid proof
- `403`: valid auth context but permission/scope/site mismatch
- `200`: success

## 5) Coding Agent Guidance

- Agents should always call `exchange-proof` before protected actions unless a valid token is cached.
- On `401 token_revoked` or `token_expired`, reacquire token via proof exchange.
- Do not retry revoked token calls in loops; switch to token refresh/re-exchange path.
- Include idempotency keys for mutation endpoints to avoid duplicate writes.

## 6) Security Notes

- Access tokens are short-lived and revocable.
- Lemma remains the trust anchor and should not be replaced by long-lived machine credentials.
- Server is the enforcement boundary for controlled actions.

