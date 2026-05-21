# isHuman — Local-First Hardening Implementation Outline

Single checklist for hardening the isHuman wallet + verifier stack into a local-first, Ed25519-signature-everywhere system.

**Demo URL:** `https://lemma.id/demo/ishuman`  
**Companion plan:** `docs/demo/ISHUMAN_DEMO_IMPLEMENTATION_OUTLINE.md`  
**Threat model reference:** `docs/security/THREAT_MODEL.md`

---

## Guiding principles

1. **Local-first.** Customer-site verification is offline by default.
2. **Sign everything.** Every cross-trust boundary carries an Ed25519 signature.
3. **Keys are derived, not stored.** `wallet_secret` is the root; per-purpose keys are HKDF-derived.
4. **No bearer-only verify.** Presentation requires a fresh challenge-bound signature.
5. **Privacy first.** Preserve site-bound PPID and no cross-site identifier leakage.

---

## Phase map


| Phase | Priority | Theme                                               | Status                |
| ----- | -------- | --------------------------------------------------- | --------------------- |
| 1     | P1       | Wallet identity Ed25519 + endpoint auth             | complete (2026-05-20) |
| 2     | P2       | Per-site signing keys + per-presentation challenges | complete (2026-05-21) |
| 3     | P3       | Signed + timestamped Bloom revocation               | complete (2026-05-21) |
| 4     | P4       | Bridge hardening + demo prod-guard                  | complete (2026-05-21) |
| 5     | P5       | PRF-encrypted at-rest storage                       | not started           |
| 6     | P6       | Local-first verifier (one call per session)         | not started           |
| 7     | P7       | Multi-issuer trust list + rotation                  | not started           |


---

## Phase 1 — Wallet identity Ed25519 + endpoint authentication (P1)

**Status:** complete (2026-05-20)

- Wallet signing key derivation and assertion primitives are implemented.
- `derive-site-proof` and `start-verification` require valid wallet assertions.
- Nonce challenge flow is enforced with replay prevention.

---

## Phase 2 — Per-site signing keys + per-presentation challenges (P2)

**Status:** complete (2026-05-21)

### 2.1 Derive per-site Ed25519 keypairs

**Implemented**

- Added per-site deterministic key derivation in `static/js/lemma-keys.js`:
  - `deriveSiteSigningKeypair(walletSecretHex, siteDomain)`
  - canonical domain normalization for derivation input.
- Added wallet API in `static/js/lemma-wallet.js`:
  - `deriveSiteSigningKeypair(siteDomain)` for bridge/runtime use.

### 2.2 Embed per-site public key in credential

**Implemented**

- Bridge now derives and sends a real `site_signing_pubkey` in derive requests.
- `api/ishuman.py` now validates `site_signing_pubkey` (base64url, 32-byte raw key) and fails closed when missing/invalid.
- Issued credentials carry `claims.site_signing_pubkey` when derived per-site.

### 2.3 Verifier issues per-presentation nonce

**Implemented**

- Verifier (`static/js/ishuman-verifier.js`) now generates a nonce challenge per verify request and sends it to bridge.
- Bridge (`templates/wallet_bridge.html`) signs `(nonce, credential_id, timestamp)` with per-site signing key and returns:
  - `presentation_signature`
  - `presentation_timestamp`
  - `presentation_nonce`
- Verifier validates:
  - issuer credential signature
  - presentation signature against `claims.site_signing_pubkey`
  - nonce match
  - staleness window

### 2.4 Acceptance criteria

- Same wallet on the same site derives deterministic site signing pubkey.
- Different sites derive different pubkeys (HKDF info includes canonical site domain).
- Verifier now requires fresh challenge-bound presentation signature.
- Stale presentation timestamp is rejected.
- Verify hot path remains local except same-origin bridge messaging.

### 2.5 Validation evidence

- Local tests:
  - `pytest tests/test_wallet_authn.py tests/test_site_ppid_revocation.py tests/test_ishuman_issuance_branching.py tests/test_ishuman_issuance_integration.py tests/test_wallet_bridge_ishuman_flow.py tests/test_ishuman_network_regressions.py`
  - Result: 36 passed.
- Production deploy:
  - Heroku app `lemma-enterprise` release `v2073` (`Deploy 3017592f`).
- Production checks:
  - Existing revocation smoke script currently reports 7/8 because it still posts empty `site_signing_pubkey` for derive (pre-Phase-2 behavior).
  - Targeted live checks passed:
    - derive denial path returns `403 site_ppid_blocked` when fixture PPID is blocked.
    - derive success path returns credential with matching `claims.site_signing_pubkey` after unblock.

### 2.6 Follow-up (resolved in Phase 3 smoke)

- `scripts/run_ishuman_prod_revocation_smoke.py` now sends a valid `site_signing_pubkey` on derive requests.

---

## Phase 3 — Signed + timestamped Bloom revocation (P3)

**Status:** complete (2026-05-21)

### 3.1 Signed Bloom snapshot envelope (API)

**Implemented**

- Added `api/bloom_snapshot.py`:
  - `sign_bloom_snapshot`, `verify_bloom_snapshot`, `verify_snapshot_matches_payload`
  - `compute_content_hash`, `fetch_revocation_sequence_number`, `invalidate_bloom_filter_cache`
  - canonical signing message `lemma:bloom-snapshot:v1` with `sequence_number`, `content_hash`, `generated_at`, `valid_until`
  - issuer signing via federated network issuer Ed25519 key (`api/issuer_management`)
- Updated `api/revocation_api.py` `/api/revocation/bloom-filter`:
  - returns signed `snapshot` envelope plus top-level `hashed_revoked_ids`, `sequence_number`, `generated_at`, `issuer_pubkey`, `signature`, `content_hash`
  - cache keyed by monotonic `revocation_list` sequence; invalidated on revocation writes/sync
- `api/revocation_sync.py` and `api/site_ppid_revocation.py` invalidate bloom HTTP cache after revocation events/commits

### 3.2 Verifier trust + freshness enforcement

**Implemented**

- `static/js/ishuman-verifier.js`:
  - `verifyBloomSnapshot()` validates issuer signature, `valid_from`/`valid_until`, and max staleness (`LEMMA_BLOOM_MAX_STALENESS_SECONDS`, default 900s)
  - `_syncBloom()` rejects unsigned/tampered/stale snapshots; sets `revocation_data_untrusted` instead of silently trusting cache
  - count check treats `0` as valid (no falsy `||` coercion)

### 3.3 Tests + CI + smoke

**Implemented**

- `tests/test_ishuman_bloom_snapshot.py` — unit/API tamper/stale/valid paths
- Extended `tests/test_ishuman_network_regressions.py` — verifier signed-bloom checks
- `.github/workflows/ishuman-issuance-tests.yml` includes `test_ishuman_bloom_snapshot.py` and `test_site_ppid_revocation.py`
- `scripts/run_ishuman_prod_revocation_smoke.py` — signed bloom snapshot step + Phase 2 derive pubkey fix

### 3.4 Acceptance criteria

- Bloom endpoint returns signed envelope with monotonic `sequence_number` and `generated_at`.
- Verifier accepts valid signed snapshots; rejects tampered, not-yet-valid, expired, and stale snapshots.
- Revocation integration tests still pass (site block, derive deny, bloom sync).

### 3.5 Validation evidence

- Local tests:
  - `pytest tests/test_ishuman_bloom_snapshot.py tests/test_ishuman_network_regressions.py tests/test_site_ppid_revocation.py -v`
  - Result: 23 passed.
- Production deploy:
  - Heroku app `lemma-enterprise` release `v2074` (`Deploy f48f321f`).
- Production smoke (`scripts/run_ishuman_prod_revocation_smoke.py` against `https://lemma.id`):
  - Result: **9/9 passed** (includes signed bloom snapshot `seq=161 trust=ok payload=ok` and derive deny `403 site_ppid_blocked`).

---

## Phase 4 — Bridge hardening + demo prod-guard (P4)

**Status:** complete (2026-05-21)

### 4.1 Bridge postMessage hardening

**Implemented**

- `templates/wallet_bridge.html`:
  - `event.source === window.parent` before processing inbound RPC
  - `postToParent()` uses captured parent origin (falls back to `*` only for initial `WALLET_BRIDGE_READY`)
  - `reportBridgeDenial()` + beacon to `/api/wallet/bridge-audit`
- `static/js/lemma-wallet.js`: `isLemmaTrustedOrigin()` exact-match (replaces substring `includes('lemma.id')`); response `type` validation
- `static/js/ishuman-verifier.js`: bridge `event.source` + expected response `type` checks
- `app.py` `/wallet/bridge`: removed `X-Frame-Options: ALLOWALL`; added `Referrer-Policy: no-referrer`; `POST /api/wallet/bridge-audit` (rate-limited, no PII)

### 4.2 Demo prod-guard

**Implemented**

- `api/ishuman_demo.py`:
  - `_require_demo_test_verify()` hard-denies when `ENVIRONMENT=production`
  - `verify-once-test-mode` requires `X-Demo-Test-Token`
  - Production `/demo/ishuman` omits demo tokens from HTML
- `static/js/demo/ishuman-demo.js`: hides guided demo + operator test controls when `test_verify_enabled` is false

### 4.3 Tests + CI + smoke

- `tests/test_wallet_bridge_origin_enforcement.py`
- Extended `tests/test_ishuman_demo.py`, `tests/test_env_parity.py`
- `.github/workflows/ishuman-issuance-tests.yml` includes Phase 4 paths/tests
- `scripts/run_ishuman_prod_revocation_smoke.py` adds prod demo-guard steps (11/11 target)

### 4.4 Validation evidence

- Local: `pytest tests/test_wallet_bridge_origin_enforcement.py tests/test_ishuman_demo.py tests/test_env_parity.py -v` — 38 passed
- Production deploy + smoke: see prod-validation notes after Heroku release

---

## Phase 5 — PRF-encrypted at-rest storage (P5)

**Status:** not started

Planned work: WebAuthn PRF-derived storage key and encrypted IDB migration.

---

## Phase 6 — Local-first verifier (one call per session) (P6)

**Status:** not started

Planned work: session presentation token cache and zero-network steady-state verifier path.

---

## Phase 7 — Multi-issuer trust list and key rotation (P7)

**Status:** not started

Planned work: trust-list signature verification and issuer rotation protocol.

---

## Cross-cutting test plan

- Unit + integration coverage for each phase.
- Production smoke checks for revocation and customer-site flow.
- Keep PPID/site-binding guardrails fail-closed.