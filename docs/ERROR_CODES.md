# lemma.id developer error reference

This reference covers errors a relying-site developer may receive from the
`ProofVerifier` browser SDK, local backend verifiers, and optional site-policy
APIs. It does not describe lemma.id operator or wallet-internal errors.

## Handling rules

1. Fail closed whenever verification returns `human: false` or `ok: false`.
2. For signup and account creation, verify a signed `presentation` on the
   backend and use the verified `result.ppid`. Never trust a bare client PPID.
3. Require `assurance: ishuman` when the action needs one verified human per
   account. A successful `passkey` result proves continuity, not Sybil
   resistance.
4. Do not retry signature, site-binding, or replay failures as if they were
   ordinary network errors.

## Browser SDK reasons

`verify()` returns a reason with `{ human, ppid, assurance, reason }`.
`verifyForBackend()` returns the same decision as `{ ok, presentation, ppid,
assurance, reason }`.

| Reason | Meaning | Developer action |
|--------|---------|------------------|
| `valid`, `vc_valid`, `session_valid` | Verification succeeded | Continue only if the returned assurance satisfies your policy |
| `no_credential`, `site_proof_required`, `wallet_locked`, `no_ishuman_credential` | User interaction is required | Call with `autoProvision: true` from a user-initiated entry point |
| `expired` | The 30-day site credential needs renewal | Allow the Lemma popup to renew it |
| `revoked` | Credential appears in the signed global revocation set | Deny now; `autoProvision: true` may offer fresh issuance unless your site blocked the PPID |
| `invalid_signature` | Credential is tampered with, corrupted, or unverifiable | Hard deny; do not accept client fields or silently retry |
| `site_id_mismatch` | Credential hostname does not match your configured `siteId` | Use the same canonical hostname in the browser and backend |
| `assurance_insufficient`, `not_ishuman` | Proof is weaker than the endpoint requires | Request the required assurance; use `ishuman` for Sybil-resistant actions |
| `site_blocked` | Your site has blocked this PPID | Deny; only an authenticated site-unblock operation clears it |
| `doubt_required` | Your site requires fresh IDV | Deny the current action, then deliberately call `verifyFreshForBackend()` |
| `idv_cancelled` | User closed the popup or cancelled IDV | Keep the action denied and offer a user-initiated retry |
| `revocation_data_untrusted` | Signed trust or revocation data could not be validated | Fail closed, retry later, and check server or device clock if persistent |

## Local backend verifier reasons

The Node package is `@lemma/proof-verifier`; the Python package is
`lemma-proof-verifier`.

| Reason | Meaning | Developer action |
|--------|---------|------------------|
| `credential_missing` | No signed credential was supplied | Reject the request; send a presentation from `verifyForBackend()` |
| `untrusted_issuer` | Issuer is not in the signed trust list | Reject and refresh trusted data |
| `invalid_signature` | Credential signature verification failed | Hard deny |
| `invalid_assurance`, `assurance_insufficient` | Assurance is invalid or below policy | Reject and request the required assurance |
| `site_id_mismatch` | Presentation is bound to another hostname | Align backend `siteId` with the browser SDK's canonical hostname |
| `expired` | Site credential has expired | Require browser renewal |
| `revoked` | Credential is globally revoked | Reject |
| `session_assertion_required` | Endpoint requires a session assertion but none was supplied | Request and verify a full presentation |
| `invalid_session_signature`, `session_expired`, `session_too_old`, `session_site_id_mismatch` | Session proof is invalid, stale, or for another site | Reject and obtain a fresh correctly bound presentation |
| `stamp_missing_proof` | Audit stamp lacks verifiable evidence | Produce the stamp with `{ includeCredential: true }` |
| `stamp_ppid_mismatch`, `stamp_credential_mismatch` | Stamp fields do not match its signed credential | Hard deny |

## Site-policy reasons

These apply when using a local policy store or the server-only
`GET /api/ishuman/check` integration.

| Reason | Meaning | Developer action |
|--------|---------|------------------|
| `site_blocked` | Canonical or legacy PPID is blocked by your site | Deny |
| `doubt_required` | Your site requires a fresh identity check | Deny, then run the deliberate fresh-IDV flow |
| `site_policy_not_configured` | Policy enforcement was required but no store was provided | Configure a policy store before serving the endpoint |
| `site_policy_unavailable` | Required policy data could not be loaded | Fail closed; restore the policy service or cache |

API keys are needed only for site-policy APIs such as `site-block`,
`site-unblock`, and `check`. Create them at
https://lemma.id/developer/external-api-keys and keep them on your backend.

## Action-stamp and replay reasons

Use `stampAction()` plus `verifyActionStamp()` / `verify_action_stamp()` for
fraud-sensitive mutations.

| Reason | Meaning | Developer action |
|--------|---------|------------------|
| `action_stamp_missing`, `action_stamp_incomplete` | Required action proof fields are absent | Reject and recreate the action stamp |
| `action_body_hash_mismatch` | Request body differs from the signed body | Hard deny |
| `action_name_mismatch`, `action_method_mismatch`, `action_path_mismatch`, `action_site_id_mismatch` | Signed action context differs from the endpoint | Hard deny and correct the client/server contract |
| `action_expired`, `action_too_old` | Action proof is stale | Request a fresh proof |
| `action_nonce_missing` | No replay-protection nonce was supplied | Issue and require a server nonce |
| `action_nonce_store_required` | Production verification requires a nonce store | Configure a shared nonce store, such as Redis |
| `action_nonce_reused` | Nonce was already consumed | Reject as a replay; do not automatically retry the mutation |
| `invalid_action_signature` | Action signature is invalid | Hard deny |
| `fresh_passkey_missing`, `fresh_passkey_expired`, `fresh_passkey_too_old`, `fresh_passkey_invalid_signature` | Required fresh-presence proof is absent or invalid | Reject and run a new fresh-passkey ceremony |

Use an in-memory nonce store only for tests. Multi-process production
deployments need a shared atomic store.

## Optional HTTP API errors

Optional abuse APIs return JSON with an `error` field and an appropriate HTTP
status:

| HTTP | Typical meaning | Developer action |
|------|-----------------|------------------|
| `400` | Missing or invalid request data | Correct the request; do not retry unchanged |
| `401` | Missing, invalid, or revoked site API key | Check the server-side `X-API-Key` |
| `403` | API key is not authorized for the requested site or operation | Confirm the key's registered `site_domain` matches SDK `siteId` |
| `404` | Resource is absent or the documentation path is not public | Check the documented relying-site endpoint |
| `409` | State conflict or replay | Re-read state; do not blindly repeat a mutation |
| `429` | Rate limit exceeded | Apply bounded backoff and honor `Retry-After` when present |
| `500`, `502`, `503` | Temporary service failure | Keep the protected action denied and retry with bounded backoff |

## Troubleshooting checklist

- `siteId` is the canonical hostname, not an internal `site_...` identifier.
- Browser and backend use the same normalized hostname.
- Signup sends a signed `presentation`, not only `{ ppid }`.
- Backend binds accounts to `result.ppid` from successful verification.
- `requiredAssurance` matches the business policy.
- `autoProvision: true` is used only at user-initiated entry points.
- Site API keys remain server-side.

See the canonical integration guide:
https://lemma.id/docs/integration/ISHUMAN_AGENT_INTEGRATION.md
