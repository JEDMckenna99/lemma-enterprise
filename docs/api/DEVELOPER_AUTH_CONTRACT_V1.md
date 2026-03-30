# Developer Auth Contract v1

Date: 2026-02-19
Owner: Lemma.id

## Beginner vs Advanced

- **Beginner OpenClaw starter path**: use the wallet-issued full credential flow. The local firewall and starter tooling send `X-Lemma-Credential` on protected requests.
- **Advanced proof-native path**: use `X-Lemma-Proof` plus `X-Lemma-PoP`.
- **Compatibility bearer path**: use `POST /api/auth/exchange-proof` only when a legacy integration still requires bearer mode.

Machine-readable contract:
- `docs/DEVELOPER_AUTH_CONTRACT_V1.openapi.json`

## 1) Lemma vs Token (Different Roles)

- **Lemma**: cryptographic claim (who/what/where) signed by trusted issuer.
- **Access token**: short-lived runtime credential for compatibility flows (optional, runtime-gated).

Lemmas are not just another machine token format. Their utility is the proof itself:
issuer trust, site binding, permission claim, and revocation-aware verification.

## 2) Canonical External Flow (Proof-Chain First)

1. Client obtains a root grant + delegated proof artifact from wallet/issuer flow.
2. Client sends delegated request with:
   - `X-Lemma-Proof`: proof-chain payload (`authz_profile_v2`)
   - `X-Lemma-PoP`: request-bound proof-of-possession payload
3. Server/daemon verifies signature trust, chain continuity, revocation, audience/site binding, scope and resource narrowing.
4. Optional compatibility path (sunsetting): client calls `POST /api/auth/exchange-proof` and server returns:
   - `access_token` (`lm_at_...`, short-lived)
   - optional `refresh_token` in future versions
5. Token mode only: client uses `Authorization: Bearer <access_token>` for controlled actions when bearer runtime auth is enabled.

### Proof-Chain payload (`authz_profile_v2`)

- Top-level required:
  - `version` (`authz_profile_v2` or `v2`)
  - `policy_version`
  - `root_proof`
  - `delegated_proof`
- `root_proof` minimum:
  - `proof_id`
  - `root_grant_id`
  - `subject_ppid`
  - `scope`
  - `aud`
  - `issued_at`
  - `expires_at`
  - optional `resource_bounds`, `revocation_epoch`
- `delegated_proof` minimum:
  - `proof_id`
  - `parent_proof_id` (must equal `root_proof.proof_id`)
  - `root_grant_id` (must equal root)
  - `acting_for_ppid` (PPID continuity with root)
  - `agent_key_id`
  - `scope` (must be subset of root scope)
  - `aud`
  - `delegation_depth`
  - `issued_at`
  - `expires_at`
  - optional `resource_bounds`, `revocation_epoch`
- `X-Lemma-PoP` minimum:
  - `nonce`, `iat`, `exp`, `method`, `path`, `body_hash`, `proof_id`, `agent_key_id`
  - `sig` (Ed25519 signature over canonical PoP envelope fields)
  - `agent_key_id` must match delegated proof key binding
- Unknown `critical_*` fields are rejected.

## 3) Control-Plane Endpoints

- `POST /api/auth/exchange-proof`
  - Input: `credential`, optional `site_id`, optional `requested_scope`, optional `ttl_seconds`
  - Output:
    - `access_token`, `token_type`, `expires_in`, `site_id`, `scope`, `permission_id`
    - `root_proof`, `delegated_proof`, `proof_chain` (new)

- `POST /api/auth/introspect` (requires API key)
  - Input: `token`, optional `site_id`
  - Output: `introspection.active` + claims metadata or error

- `POST /api/auth/revoke` (requires API key)
  - Input: `token` or `jti`, optional `reason`
  - Output: `revoked: true` and revocation metadata

- `POST /api/auth/refresh`
  - Input: `refresh_token`, optional `site_id`
  - Output: rotated `access_token` + rotated `refresh_token`
  - Behavior: fails if refresh token is revoked/expired or auth context was revoked

## 4) Status Code Contract

- `400`: malformed request (missing required fields)
- `401`: missing auth or invalid/expired/revoked credential/token
- `403`: valid auth context but permission/scope/site mismatch
- `200`: success

## 5) Coding Agent Guidance

- Agents should send `X-Lemma-Proof` and `X-Lemma-PoP` by default on protected endpoints.
- Agents should sign `X-Lemma-PoP` with the delegated Ed25519 private key.
- `X-Lemma-Credential` is compatibility fallback only where route policy still allows compat mode.
- Use `POST /api/auth/exchange-proof` only for compatibility integrations that still require bearer token mode.
- On token-mode `401 token_revoked` or `token_expired`, reacquire via proof exchange or migrate that integration to direct lemma verification.
- Do not retry revoked token calls in loops; switch to lemma re-auth or token refresh/re-exchange path.
- Include idempotency keys for mutation endpoints to avoid duplicate writes.

## 6) Security Notes

- Access tokens are short-lived and revocable.
- Lemma remains the trust anchor and should not be replaced by long-lived machine credentials.
- Server is the enforcement boundary for controlled actions.
- Strict VC-only runtime can disable bearer access-token auth with `LEMMA_ENABLE_ACCESS_TOKEN_AUTH=0`.
- Fresh-passkey step-up is optional and policy-gated. Baseline once-daily unlock remains valid unless route/runtime policy requires `X-Lemma-Step-Up: fresh_passkey`.

