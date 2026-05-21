# isHuman — Local-First Hardening Implementation Outline

Single checklist for hardening the isHuman wallet + verifier stack into a local-first, Ed25519-signature-everywhere system. Each phase is independently shippable; later phases depend on earlier signing primitives.

**Demo URL:** `https://lemma.id/demo/ishuman`
**Companion plan:** [docs/demo/ISHUMAN_DEMO_IMPLEMENTATION_OUTLINE.md](../demo/ISHUMAN_DEMO_IMPLEMENTATION_OUTLINE.md)
**Threat model reference:** [docs/security/THREAT_MODEL.md](THREAT_MODEL.md)

---

## Guiding principles

1. **Local-first.** Customer-site verification is offline by default. Phone-home only at issuance, derivation, revocation propagation, and bloom refresh.
2. **Sign everything.** Every server endpoint accepts a fresh signed assertion, never a bare identifier. Every cross-trust boundary carries an Ed25519 signature.
3. **Keys are derived, not stored.** `wallet_secret` is the only root; per-purpose Ed25519 keys come from HKDF. Rotation = re-derive.
4. **Passkey protects the root, signatures protect everything else.** PRF-encrypts `wallet_secret`; Ed25519 sub-keys carry the load on hot paths.
5. **No bearer credentials in routine verify.** Possession of credential JSON is insufficient; presentation requires a fresh per-site signature.
6. **Privacy first.** No cross-site linkage. lemma.id never learns which sites a user is currently active on after the per-site credential has been issued.

---

## Goals (what "done" looks like)

A user with a stolen IndexedDB blob cannot:

1. Replay any credential on a different device.
2. Mint new per-site credentials without the original passkey-bound device.
3. Forge an unlocked session to bypass the passkey.
4. Read `wallet_secret` or stored credentials in cleartext.

A customer site can:

5. Verify locally, with no per-action call to lemma.id.
6. Refuse stale revocation data using a signed Bloom timestamp.
7. Reject replay across devices via per-presentation challenge.
8. Block, force-reverify, or escalate at any time, applied on every action.

A user experiences:

9. One passkey tap per device per 24h session.
10. One additional tap per brand-new customer site (issuance moment only).
11. Zero taps for routine browsing, repeat verifies, or non-state-changing actions.

---

## Phase map

| Phase | Priority | Theme | Est. effort |
| ----- | -------- | ----- | ----------- |
| 1 | P1 | Wallet identity Ed25519 + endpoint auth | 1 week |
| 2 | P2 | Per-site signing keys + per-presentation challenges | 1 week |
| 3 | P3 | Signed + timestamped Bloom revocation | 0.5 week |
| 4 | P4 | Bridge hardening + demo prod-guard | 0.5 week |
| 5 | P5 | PRF-encrypted at-rest storage | 1 week |
| 6 | P6 | Local-first verifier (one call per session) | 1.5 weeks |
| 7 | P7 | Multi-issuer trust list + rotation | 2 weeks |

Implement **in order** — Phase 2+ depends on Phase 1's signing primitives; Phase 6 depends on Phases 1–3.

---

## Phase 1 — Wallet identity Ed25519 + endpoint authentication (P1)

**Status:** complete (2026-05-20)

### 1.1 Derive `wallet_signing_key` from `wallet_secret`

**Files:**

- [static/js/lemma-wallet.js](../../static/js/lemma-wallet.js) — add `_deriveWalletSigningKey()`, `_signWithWalletKey(payload)`, expose pubkey export
- New: [static/js/lemma-keys.js](../../static/js/lemma-keys.js) — pure crypto helpers (HKDF, Ed25519 sign/verify wrappers around `crypto.subtle` and a small `tweetnacl`-style fallback)

**Derivation:**

```
wallet_signing_seed = HKDF-SHA256(
  ikm    = wallet_secret_bytes,
  salt   = "lemma:hkdf:v1",
  info   = "wallet-signing-key-v1",
  length = 32
)
wallet_signing_keypair = Ed25519.fromSeed(wallet_signing_seed)
```

Generated lazily; never persisted (re-derived on each unlock from `wallet_secret`).

### 1.2 Register wallet public key

**Files:** [api/wallet_session_sync.py](../../api/wallet_session_sync.py), [api/database.py](../../api/database.py)

- Add `wallet_signing_pubkey` column to the `Wallet` (or equivalent) table.
- New endpoint `POST /api/wallet/register-signing-key`: client sends `{wallet_id, pubkey, signature_over_wallet_id}` proving possession of the matching private key. Server stores pubkey only after self-signature verifies.
- Idempotent: re-registering the same key is a no-op; replacing requires a fresh passkey-gated session.

### 1.3 Server-side signature verifier

**Files:** new [api/wallet_authn.py](../../api/wallet_authn.py)

- `def verify_wallet_assertion(wallet_id, payload_bytes, signature, *, max_age_seconds=120)`: looks up registered pubkey, verifies Ed25519 signature, enforces timestamp/nonce window.
- Replay protection via short-lived nonces: server pre-issues nonces from `POST /api/wallet/challenge` (returns `{nonce, expires_at}`); client signs `nonce + payload_hash`; server burns nonce on use.

### 1.4 Authenticate `derive-site-proof`

**Files:** [api/ishuman.py](../../api/ishuman.py) (`derive_site_proof`), [templates/wallet_bridge.html](../../templates/wallet_bridge.html)

- Request body now requires `wallet_assertion = { nonce, signature }` over `(wallet_id, master_credential_id, target_site, nonce)`.
- Reject with `403 wallet_assertion_required` when missing or invalid.
- Bridge constructs the assertion before posting; demo JS uses the same path.

### 1.5 Authenticate `start-verification`

**Files:** [api/ishuman.py](../../api/ishuman.py) (`start_verification`)

- Same assertion pattern over `(wallet_id, return_url, nonce)`.
- Pin `return_url` to a server-canonical value if the assertion does not match the requested URL.

### 1.6 Authenticate demo endpoints that mint or revoke

**Files:** [api/ishuman_demo.py](../../api/ishuman_demo.py)

- `verify-once-test-mode`, `force-reverify`, `approve-network-revocation`, `probe-derive`: all accept a wallet assertion when used by a real wallet. Synthetic test paths still gated by env tokens; production deploys require the assertion path.

### 1.7 Acceptance criteria

- [x] `wallet_signing_key` derives identically across reloads from the same `wallet_secret`.
- [x] Public key persists across page reloads; private key never leaves memory.
- [x] `derive-site-proof` returns 403 without a valid assertion.
- [x] `start-verification` returns 403 without a valid assertion.
- [x] Replaying the same assertion within the nonce window fails (nonce burned).
- [x] Existing demo guided wizard runs end-to-end with one passkey tap and the new assertions.
- [x] Unit tests cover assertion verification, nonce reuse, and clock skew tolerance.

### 1.8 Phone-home and UX delta

- **Phone-home delta:** none — assertions ride existing requests.
- **UX delta:** zero additional taps. Assertions are signed silently using the in-memory `wallet_signing_key` derived at unlock time.

---

## Phase 2 — Per-site signing keys + per-presentation challenges (P2)

**Status:** not started

### 2.1 Derive per-site Ed25519 keypairs

**Files:** [static/js/lemma-wallet.js](../../static/js/lemma-wallet.js)

```
site_signing_seed = HKDF-SHA256(
  ikm    = wallet_secret_bytes,
  salt   = "lemma:hkdf:v1",
  info   = "site-signing-key-v1:" + canonical_site_domain,
  length = 32
)
```

Re-derived on demand; never persisted. Each customer site gets a unique keypair, providing cross-site unlinkability at the keying layer (PPID already provides it at the identifier layer).

### 2.2 Embed per-site public key in credential

**Files:** [api/ishuman.py](../../api/ishuman.py) (`_issue_ishuman_credential`, `derive_site_proof`)

- Client posts the per-site public key alongside the derive request, signed by `wallet_signing_key`.
- Server includes `claims.site_signing_pubkey` in the issued credential.
- Issuer signs the whole credential as today; the per-site pubkey is part of what is signed, so it cannot be substituted.

### 2.3 Verifier issues per-presentation nonce

**Files:** [static/js/ishuman-verifier.js](../../static/js/ishuman-verifier.js), [templates/wallet_bridge.html](../../templates/wallet_bridge.html)

- Verifier generates a 32-byte nonce locally; sends to the bridge with `GET_CREDENTIAL` request.
- Bridge returns credential + `presentation_signature = Ed25519(site_signing_key, nonce || credential_id || timestamp)`.
- Verifier checks: issuer signature on credential, presentation signature against `claims.site_signing_pubkey`, timestamp staleness, expiry, revocation.

### 2.4 Acceptance criteria

- [ ] Same wallet on the same site always derives the same site signing pubkey.
- [ ] Two different sites for the same wallet derive different pubkeys (no key reuse).
- [ ] A credential copied to a different device is rejected: signature over the verifier's nonce fails.
- [ ] Replaying a presentation signature past the staleness window fails.
- [ ] Verifier never makes a network call in the verify hot path beyond the same-origin bridge.

### 2.5 Phone-home and UX delta

- **Phone-home delta:** none — bridge is same-origin to lemma.id wallet (cross-origin via iframe, but no new endpoints touched).
- **UX delta:** zero additional taps. Per-site keys derived silently from in-memory `wallet_secret`.

---

## Phase 3 — Signed + timestamped Bloom revocation (P3)

**Status:** not started

### 3.1 Issuer signs Bloom snapshots

**Files:** [api/revocation_sync.py](../../api/revocation_sync.py), [api/revocation_verifier.py](../../api/revocation_verifier.py)

- Server publishes Bloom updates with `{filter_bytes, generated_at, sequence_number, signature}` — issuer Ed25519 signature over `(filter_bytes, generated_at, sequence_number)`.
- SSE stream emits the signed envelope; pull endpoint returns the same shape.

### 3.2 Verifier enforces freshness and signature

**Files:** [static/js/ishuman-verifier.js](../../static/js/ishuman-verifier.js)

- Verifier ships with the issuer pubkey pinned (or a small trust list in Phase 7).
- On Bloom load: verify signature, store `generated_at`. Reject if signature invalid.
- On verify: refuse `human: true` when `now - generated_at > MAX_BLOOM_STALENESS` (default 15 minutes); fall through to direct server check `/api/ishuman/check` (signed) before failing closed.

### 3.3 Signed direct check fallback

**Files:** [api/ishuman.py](../../api/ishuman.py) (`check_ppid`)

- Response body now includes `{result, generated_at, signature}` so the verifier can cache and prove freshness for offline propagation.

### 3.4 Acceptance criteria

- [ ] Bloom updates are rejected when the signature does not verify.
- [ ] Verifiers refuse to use a Bloom filter older than `MAX_BLOOM_STALENESS`.
- [ ] Falsifying a sequence number (downgrading to older filter) is rejected.
- [ ] `/api/ishuman/check` responses are signed and timestamp-bound.

### 3.5 Phone-home and UX delta

- **Phone-home delta:** none in steady state (SSE push). One emergency direct check when Bloom expires offline.
- **UX delta:** none.

---

## Phase 4 — Bridge hardening + demo production guard (P4)

**Status:** not started

### 4.1 Gate bridge `GET_CREDENTIAL` on active session

**Files:** [templates/wallet_bridge.html](../../templates/wallet_bridge.html)

- Remove the "reads allowed without active session" exemption.
- Bridge checks `wallet.isUnlocked()` before returning credentials.
- For sites that legitimately need session-less reads (e.g. low-stakes verifiers), require a wallet-issued **session token**: short-lived signed token from the wallet authorizing read access for `[origin, ttl]`.

### 4.2 Origin allowlist for bridge requests

**Files:** [templates/wallet_bridge.html](../../templates/wallet_bridge.html), new [api/wallet_origin_allowlist.py](../../api/wallet_origin_allowlist.py)

- Postmessage handler verifies the requesting origin against a server-fetched (cached) allowlist — initially the demo sites, then any site that has registered.
- Unknown origins receive `origin_not_authorized` and zero data.

### 4.3 Production guard for demo blueprint

**Files:** [api/ishuman_demo.py](../../api/ishuman_demo.py)

- Top-level guard: blueprint registers no routes when `FLASK_ENV=production` unless `LEMMA_DEMO_ALLOWED_IN_PROD=1`.
- Per-route guard: every demo route checks `request.path.startswith('/demo/') or request.referrer is /demo/ishuman` to reject lateral discovery.

### 4.4 Fix dual PPID derivation paths

**Files:** [api/ishuman.py](../../api/ishuman.py) (`_derive_ppid_for_site`)

- Remove the `wallet_id`-only fallback. Require `wallet_secret` for canonical derivation. Server-side flows that previously relied on the fallback must be audited and updated.
- Document the canonical derivation: `did:lemma:ppid_<HMAC-SHA256(wallet_secret, canonical_rp_id)>`.

### 4.5 Acceptance criteria

- [ ] Bridge `GET_CREDENTIAL` rejected without active session or signed read token.
- [ ] Postmessage from un-allowlisted origin returns no data.
- [ ] `api/demo/*` routes return 404 in production unless explicit env flag set.
- [ ] `_derive_ppid_for_site(wallet_secret=None, wallet_id=...)` raises instead of warning.
- [ ] All site PPIDs across both client and server flows are byte-identical for the same `(wallet_secret, site_domain)` input.

### 4.6 Phone-home and UX delta

- **Phone-home delta:** one server fetch for origin allowlist on bridge cold load (cached aggressively).
- **UX delta:** none for happy paths.

---

## Phase 5 — PRF-encrypted at-rest storage (P5)

**Status:** not started

### 5.1 Derive storage key via WebAuthn PRF

**Files:** [static/js/lemma-wallet.js](../../static/js/lemma-wallet.js)

- During `unlock()` and `registerPasskey()`, request the `prf` extension with a stable salt: `prf_salt = SHA256("lemma:idb-prf-v1")`.
- Output: 32 bytes from the authenticator. Derive `storage_key = HKDF-SHA256(prf_output, salt="prf-storage-v1", info="lemma-storage-aead")`.
- Stored in memory only; cleared on `lock()`.

### 5.2 Encrypted IDB writes

**Files:** [static/js/lemma-wallet.js](../../static/js/lemma-wallet.js)

- `_putEncrypted(storeName, value)`: encrypts the JSON-serialized value with AES-GCM under `storage_key`, writes `{id, ciphertext, iv, tag, version}`.
- `_getEncrypted(storeName, id)`: reads, verifies, decrypts. Throws `STORAGE_KEY_UNAVAILABLE` if not unlocked.
- Stores migrated: `secrets`, `lemmas`, `profiles`. `passkey` and `session` remain plaintext (forging session no longer grants secret access since storage_key is gone).

### 5.3 Migration

**Files:** [static/js/lemma-wallet.js](../../static/js/lemma-wallet.js)

- IDB version bump (v4 → v5). On upgrade, on first unlock with PRF support, migrate plaintext records to encrypted records and delete originals.
- Devices without PRF support (rare on modern platforms): graceful fallback to plaintext with a security-mode flag exposed to UI.

### 5.4 Acceptance criteria

- [ ] `wallet_secret` is unreadable from raw IDB without invoking the passkey.
- [ ] Locking the wallet purges `storage_key` from memory; subsequent reads fail until unlock.
- [ ] PRF-unsupported devices continue to work (with a documented security degradation).
- [ ] Migration is idempotent and reversible if PRF support is detected later.

### 5.5 Phone-home and UX delta

- **Phone-home delta:** none.
- **UX delta:** one passkey tap per 24h session (already in flow). No per-action taps.

---

## Phase 6 — Local-first verifier (one call per session) (P6)

**Status:** not started

### 6.1 Issue session presentation token at first verify

**Files:** [static/js/ishuman-verifier.js](../../static/js/ishuman-verifier.js), [templates/wallet_bridge.html](../../templates/wallet_bridge.html)

- First `verify()` per customer-site session opens the bridge, retrieves the per-site credential + a **presentation token**: a short-lived signed envelope containing `{credential, site_signing_pubkey, expires_at, signature}`.
- Token stored in customer-site `sessionStorage` (origin-scoped, never sent to lemma.id).

### 6.2 Per-action verify is local

**Files:** [static/js/ishuman-verifier.js](../../static/js/ishuman-verifier.js)

- Each subsequent `verify()` consumes the cached token, runs the full check stack locally:
  - Issuer signature on credential
  - Issuer signature on presentation envelope
  - Token freshness against `expires_at`
  - Local Bloom check
  - Site block list (server-pushed via SSE, also local cache)
  - Optional per-action challenge: customer site issues nonce, wallet signs (one bridge round-trip; opt-in for high-value actions only)
- On token expiry: re-fetch from bridge.

### 6.3 Customer-site SDK hardening

**Files:** [static/js/ishuman-verifier.js](../../static/js/ishuman-verifier.js)

- Pin issuer pubkey at SDK build time (with `trust_list_url` for hot-reload).
- No `fetch()` calls to `lemma.id` from the SDK in steady state.
- Bridge calls only when token is missing, expired, or per-action assertion is requested.

### 6.4 Acceptance criteria

- [ ] First `verify()` in a customer-site session: one bridge call.
- [ ] Subsequent `verify()` calls: zero network activity.
- [ ] Network panel shows zero requests to `lemma.id` from a customer site during routine browsing.
- [ ] Token forgery without `wallet_secret` is impossible.
- [ ] Revocation propagation latency unchanged (SSE-driven Bloom updates still hit clients within seconds).

### 6.5 Phone-home and UX delta

- **Phone-home delta:** ~99% reduction. Per-site verify drops from N round-trips to lemma.id origin to one per session, with steady-state zero.
- **UX delta:** none.

---

## Phase 7 — Multi-issuer trust list and key rotation (P7)

**Status:** not started

### 7.1 Trust list format

**Files:** new [api/issuer_trust_list.py](../../api/issuer_trust_list.py), [static/js/ishuman-verifier.js](../../static/js/ishuman-verifier.js)

- Trust list = signed JSON of `[{issuer_id, pubkey, valid_from, valid_until, status}]`.
- Signed by a long-lived **trust root** key held in cold storage.
- Verifiers fetch trust list once per day; pin trust root at SDK build time.

### 7.2 Issuer rotation playbook

**Files:** [docs/operations/ISSUER_KEY_ROTATION.md](../operations/ISSUER_KEY_ROTATION.md) (new)

- New issuer key activated with `valid_from = now + 24h`.
- Old key marked `status = retired` with `valid_until = now + 30d` (covers in-flight credential lifetimes).
- Compromise scenario: trust root signs revocation of the old key, broadcast via SSE; verifiers refuse new credentials signed by it within seconds.

### 7.3 Multi-issuer interop

- Credentials carry `issuer_id` referencing the trust list entry.
- Verifiers accept any active issuer in the list.
- Enables federated networks: external partners can join the trust list under explicit governance.

### 7.4 Acceptance criteria

- [ ] Trust list signature verifies against pinned root.
- [ ] Verifiers reject credentials signed by issuers not in the active list.
- [ ] Hot rotation completes without verifier downtime.
- [ ] Compromised issuer revocation propagates within SSE round-trip time.

### 7.5 Phone-home and UX delta

- **Phone-home delta:** one trust-list fetch per verifier per day (cached aggressively).
- **UX delta:** none.

---

## Cross-cutting test plan

Each phase ships with:

- **Unit tests** in [tests/](../../tests/) — at minimum: signature round-trip, key derivation determinism, replay rejection, expiry enforcement.
- **Integration tests** that boot a Flask app with the new authn middleware and assert known-bad requests are rejected.
- **Smoke tests** added to `scripts/run_ishuman_prod_revocation_smoke.py` and `scripts/smoke_ishuman_customer_sites.py`.
- **Workflow guard** in `.github/workflows/ishuman-issuance-tests.yml` and `ishuman-demo-smoke.yml`.

End-to-end checks:

- [ ] A user with stolen IDB cannot replay any credential on a different device (Phase 2 verifies).
- [ ] `derive-site-proof` cannot be called without a valid assertion (Phase 1 verifies).
- [ ] Locking the wallet renders IDB unreadable (Phase 5 verifies).
- [ ] Customer-site verify generates zero network calls to lemma.id in steady state (Phase 6 verifies).
- [ ] Issuer key rotation completes without rejecting valid credentials (Phase 7 verifies).
- [ ] Existing isHuman demo guided run still completes in under 3 minutes with one tap.

---

## Out of scope (do not block local-first v1)

- WebAuthn `largeBlob` storage (PRF is sufficient for this iteration).
- Hardware wallet integration (USB / NFC authenticator paths).
- Cross-issuer federation governance and economic model.
- DBSC (Device Bound Session Credentials) once browser support stabilizes — revisit in Q3+.
- Post-quantum signatures.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| PRF not supported on a user's device | Fall back to plaintext IDB with a visible "reduced security" UI flag; log a metric so we can measure unsupported share. |
| Nonce service availability becomes a hot path | Pre-mint nonces in batches client-side; server signs a batch when the wallet unlocks. |
| Issuer key compromise mid-rotation | Trust root's revocation broadcast is the failsafe; verifier staleness budget enforces upper bound. |
| Customer SDK shipped before per-site signing keys exist | Phase 1 deploys server changes; Phase 2 SDK update is opt-in via a feature flag for ~2 weeks before becoming required. |
| Demo UX regression from extra assertions | All assertions are silent (no taps); regression is purely server-side risk; covered by smoke tests. |

---

## File index (quick reference)

| Area | Primary files |
|------|---------------|
| Wallet identity Ed25519 | `static/js/lemma-wallet.js`, new `static/js/lemma-keys.js` |
| Server assertion verification | new `api/wallet_authn.py`, `api/wallet_session_sync.py` |
| Endpoint hardening | `api/ishuman.py`, `api/ishuman_demo.py` |
| Bridge | `templates/wallet_bridge.html`, new `api/wallet_origin_allowlist.py` |
| Verifier SDK | `static/js/ishuman-verifier.js` |
| Revocation | `api/revocation_sync.py`, `api/revocation_verifier.py` |
| PRF storage | `static/js/lemma-wallet.js` |
| Trust list | new `api/issuer_trust_list.py`, new `docs/operations/ISSUER_KEY_ROTATION.md` |
| Tests | `tests/test_ishuman_*`, new `tests/test_wallet_authn.py`, new `tests/test_wallet_prf_storage.py` |
| Smoke | `scripts/run_ishuman_prod_revocation_smoke.py`, `scripts/smoke_ishuman_customer_sites.py` |
| Workflows | `.github/workflows/ishuman-issuance-tests.yml`, `.github/workflows/ishuman-demo-smoke.yml` |

---

## Suggested new-thread prompt (copy/paste)

```
Implement the local-first hardening plan from
docs/security/ISHUMAN_LOCAL_FIRST_IMPLEMENTATION_OUTLINE.md.

Work phase by phase (1 → 7). After each phase:
- run pytest for touched tests
- run scripts/run_ishuman_prod_revocation_smoke.py if backend changed
- update the outline's status + checkboxes
- briefly note what to click on https://lemma.id/demo/ishuman to verify

Constraints:
- Local-first: customer-site verify must remain offline-capable.
- Sign everything: every server endpoint requires an Ed25519 assertion.
- Preserve site-bound PPID guardrails: hostname binding, no cross-site
  ID leakage, fail closed on mismatched bindings.
- Keep the existing demo UX: one passkey tap per 24h session, none per
  routine action.
- Phone-home budget: reduce to issuance + per-site derivation +
  Bloom/SSE only. Routine verify must hit zero lemma.id endpoints.
```
