# Lemma isHuman — v2 Design Improvements

> **For the next agent picking this up:** this document is self-contained.
> You don't need prior conversation context. Read this top-to-bottom before
> touching code. The codebase is currently at SDK 1.5.6, deployed to
> production on Heroku. The design works end-to-end but carries debt from
> being built across multiple phases. This document proposes a v2 refactor.

---

## 0. Codebase orientation

Read these files first to internalize the current architecture:


| File                                      | What it is                                                                                                                                                                                                       |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `static/js/ishuman-verifier.js`           | The relying-site SDK. Embeds in customer sites, verifies isHuman credentials locally with WebCrypto Ed25519. Handles popup-first issuance, Bloom revocation checks, cross-tab broadcast, session-cache hot path. |
| `static/js/lemma-wallet.js`               | The user-facing wallet SDK. Manages IndexedDB storage, passkey unlock, PRF-derived at-rest encryption, credential issuance helpers, daily-unlock bundle, BroadcastChannel sync.                                  |
| `static/js/lemma-keys.js`                 | Crypto primitives (HKDF, Ed25519, canonicalization). Shared by wallet and verifier.                                                                                                                              |
| `api/ishuman.py`                          | Production isHuman API: `/api/ishuman/start-verification`, Stripe Identity webhook, `/api/ishuman/derive-site-proof`, `/api/ishuman/verify-presentation`. Master credential issuance lives here.                 |
| `api/ishuman_demo.py`                     | Demo orchestration: test-mode IDV, demo site blocks, network revocation drill, reset endpoints. Gated by `LEMMA_ISHUMAN_DEMO_`* env vars.                                                                        |
| `api/site_ppid_revocation.py`             | Canonical PPID revocation + the shared `clear_amnesty_eligible_wallet_revocations` helper.                                                                                                                       |
| `api/revocation_api.py`                   | Serves `/api/revocation/bloom-filter` — the signed Bloom snapshot + trust list every relying site fetches.                                                                                                       |
| `api/ppid.py`                             | PPID derivation primitives (HMAC-based, pairwise per (person_root, site)).                                                                                                                                       |
| `api/identity_roots.py`                   | document_root + person_root derivation from Stripe Identity document fields.                                                                                                                                     |
| `api/issuer_trust_list.py`                | Signed multi-issuer trust list construction + verification.                                                                                                                                                      |
| `api/bloom_snapshot.py`                   | Bloom snapshot building, signing, cache invalidation.                                                                                                                                                            |
| `templates/wallet_ishuman_idv.html`       | The lemma.id popup that runs IDV and derives site proofs.                                                                                                                                                        |
| `templates/wallet_bridge.html`            | The hidden iframe relying sites embed to talk to the wallet. (Subject of v2 removal — see Phase 2.)                                                                                                              |
| `packages/ishuman-verify-js/`             | Node/Deno/browser backend verifier package (relying-site backends).                                                                                                                                              |
| `packages/ishuman-verify-py/`             | Python backend verifier package.                                                                                                                                                                                 |
| `examples/relying_site_offline_verify.py` | Reference Python implementation, also served at `/sdk/lemma_ishuman_verify.py`.                                                                                                                                  |
| `tests/test_ishuman_*.py`                 | Regression suite. 52 tests at time of writing. Run with `python -m pytest`.                                                                                                                                      |


### Terminology cheat-sheet


| Term                 | Definition                                                                                                                                                                                                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `wallet_secret`      | 32-byte random secret generated client-side at wallet creation. Stored in IndexedDB encrypted under passkey PRF key. Used today for site signing keys AND legacy PPID derivation.                                                                                                    |
| `person_root`        | 32-byte server-derived secret. `person_root = HKDF(document_root_hash, salt=LEMMA_PERSON_ROOT_SALT_V1, info="lemma.id/person-root/v1")`. Same human + same documents → same person_root, forever.                                                                                    |
| `document_root`      | `HMAC(LEMMA_IDENTITY_ROOT_PEPPER_V1, canonical_json(document_fields))`. Deterministic fingerprint of an identity document.                                                                                                                                                           |
| `PPID`               | Pairwise pseudonymous identifier. `did:lemma:ppid_<hex>`. Today: `HMAC(person_root, "lemma.id/site-ppid/v1" + canonical_site_domain)` for post-IDV wallets, or `HMAC(HMAC(LEMMA_PPID_ROOT_KEY, wallet_secret), site_domain)` for pre-IDV wallets. Note the two paths — this is debt. |
| Master credential    | A signed VC issued at IDV completion. Subject=user's lemma.id PPID, siteId="lemma.id". `credential.id = ishuman_master_<random>`. User holds it in wallet.                                                                                                                           |
| Per-site VC          | Derived from master + site_domain. Subject=user's site PPID. Includes `claims.site_signing_pubkey` = HKDF-derived per-site keypair pubkey.                                                                                                                                           |
| Session presentation | A signed assertion (`session_assertion` + `session_signature`) the user produces at verify time. Signed with the site_signing_keypair (proof of possession). Has bloom_sequence binding for freshness.                                                                               |
| `bloom_sequence`     | Monotonic counter on Bloom snapshot generation. SDK rejects sessions if their `bloom_sequence` ≠ current. Fixed in 1.5.5 with post-reset fetch in the popup.                                                                                                                         |
| `signatureValueWeb`  | Browser-canonical-format Ed25519 signature on the VC (vs `signatureValue` which is Rust binary-concat format). Added so the JS verifier can locally validate.                                                                                                                        |


### Deploy targets

Three Heroku apps:

- `lemma-enterprise` — main app at [https://lemma.id](https://lemma.id), current `ENVIRONMENT=production` (this is causing demo issues; see Phase 6)
- `lemma-demo-tickets` — at [https://lemma-demo-tickets-1d3d7411af33.herokuapp.com](https://lemma-demo-tickets-1d3d7411af33.herokuapp.com)
- `lemma-demo-trials` — at [https://lemma-demo-trials-7090f46cae0d.herokuapp.com](https://lemma-demo-trials-7090f46cae0d.herokuapp.com)

Deploy via:

```bash
git push heroku deploy-heroku-deep-claims:main                            # main app
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git deploy-heroku-deep-claims:main
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-trials.git deploy-heroku-deep-claims:main
```

Regression run: `cd <repo>; python -m pytest tests/test_ishuman_*.py -q`

---

## 1. What problems v2 is solving

After delivering a working popup-first issuance flow, post-revocation fresh-IDV reset, dual-signed credentials, and a deployable demo, the architecture has these specific debts:

1. **Two parallel identity anchors** (`wallet_secret` + `person_root`) with no unification path
2. **Master credential is a load-bearing dependency** in several server flows it doesn't need to be
3. **Bridge iframe + popup duality** carries cruft from the pre-storage-partitioning era; both code paths can drift
4. **Pepper/salt rotation has no story** — single-point-of-failure for the entire network's privacy guarantee
5. **Single-issuer dependence on Stripe Identity** for IDV
6. **Bloom filter is a single global structure** that won't scale past ~1M revocations
7. **Cross-device transfer is undocumented** — the explicit token flow exists but isn't the advertised story
8. **Demo and production share an app** — `ENVIRONMENT=production` on the main app breaks demo flows and vice versa
9. **No threat model document** — invariants live in code only, not in human-readable form

The core insight of the design — **document-anchored stable identity with pairwise PPIDs and portable signed credentials** — is sound. The smart parts are:

- `person_root` is the right anchor (vs. account or wallet)
- Pairwise PPIDs are mathematically clean
- Local Ed25519 verification at relying sites (~3 ms per verify, no per-request calls to lemma.id)
- Bloom-based revocation that doesn't leak credential IDs

This document keeps all of those. It removes the surrounding bookkeeping.

---

## 2. Execution order (recommended)

If you're picking one item at a time, do them in this order:

1. **Phase 6** — Split demo from production. Unblocks current operational pain; tiny cost.
2. **Phase 1.2 + 1.3** — Make master credential non-load-bearing + reissuable. Enables the rest without risk.
3. **Phase 5** — Pin invariants in tests, document threat model + canonical message spec. Cheap insurance.
4. **Phase 2** — Remove the bridge iframe. Big simplification, ~1 week of focused work.
5. **Phase 1.1** — Consolidate `wallet_secret` + `person_root`. Most disruptive; feature-flag rollout.
6. **Phase 4** — Formalize recovery flows.
7. **Phase 3** — Operational hardening (pepper rotation, multi-issuer, Bloom scaling). Necessary before scale, not urgent at current volume.

Each phase is independently shippable. Don't try to do all of them in one PR.

---

## Phase 1 — Identity layer simplification

### 1.1 Consolidate `wallet_secret` and `person_root` into a single derivation tree

**Problem:** Today two parallel root secrets exist with overlapping responsibilities. Cross-wallet recovery is awkward; the trust-domain story is muddier than it needs to be; users get confused.

**Design:**

```text
Pre-IDV wallet (anonymous mode):
    wallet_seed = random 32 bytes at registration
    site signing key = HKDF(wallet_seed, "site-signing-key-v1:" + canonical_site)
    legacy PPID = HMAC(HMAC(LEMMA_PPID_ROOT_KEY, wallet_seed), site_domain)
    (Same as today's wallet_secret. This path stays for anonymous flows.)

Post-IDV wallet (verified mode):
    person_root = HKDF(document_root_hash, salt=LEMMA_PERSON_ROOT_SALT_V1, info="...person-root/v1")
                  (server-only, never leaves)
    wallet_local_seed = HKDF(person_root, salt, info="lemma.id/wallet-local-seed/v1" || wallet_id)
                       (server delivers ONCE during IDV completion, encrypted under
                        the wallet's passkey-PRF key, in a new `seed_envelope` field)
    site signing key = HKDF(wallet_local_seed, "site-signing-key-v1:" + canonical_site)
    PPID  (client-side, if needed for display) = HMAC(person_root_proxy, site_domain)
          where person_root_proxy is delivered identically to wallet_local_seed
          (so the client can compute its own PPIDs without round-trip)
    PPID  (server-side) = HMAC(person_root, "lemma.id/site-ppid/v1" + canonical_site)
```

Mathematically the client-side PPID and server-side PPID are computed from the same input space, so they agree.

**Concrete change set:**

1. Add column to `IsHumanVerification`:
  - `wallet_seed_envelope` (LargeBinary) — encrypted blob, ciphertext only
  - `person_root_proxy_envelope` (LargeBinary) — encrypted blob for client-side PPID derivation
2. Modify `_complete_verified_ishuman_from_stripe` in `api/ishuman.py` to:
  - Derive `wallet_local_seed = HKDF(person_root, ...)` and `person_root_proxy = HKDF(person_root, ...)`
  - Encrypt both with the wallet's signing-key-derived envelope key (the wallet posts its current public encryption key during IDV start)
  - Store envelopes on the verification record
3. Add `GET /api/ishuman/seed-envelope` endpoint:
  - Wallet sends `wallet_id` + signed assertion
  - Server returns the latest envelopes
  - Wallet decrypts with its passkey-PRF key, stores the cleartext seeds
4. Migrate `lemma-wallet.js`:
  - On post-IDV path, use `wallet_local_seed` for site signing key derivation
  - On post-IDV path, use `person_root_proxy` for client-side PPID computation
  - Keep `wallet_secret` path alive for anonymous (pre-IDV) wallets
5. Feature flag: `LEMMA_ISHUMAN_USE_PERSON_ROOT_SEEDS` (default false → existing behavior; true → new derivation). Roll out per-wallet via a `seed_version` column on `IsHumanVerification`.

**Test additions** (`tests/test_ishuman_identity_derivation.py`):

- Same person_root + same wallet_id → same wallet_local_seed
- Different wallet_id, same person_root → different wallet_local_seed (cross-wallet isolation)
- Round-trip the envelope: server encrypt → client decrypt → matches expected bytes
- PPIDs from `person_root_proxy` (client) and `person_root` (server) match for same site

**Migration plan:**


| Step | Action                                                                                                    |
| ---- | --------------------------------------------------------------------------------------------------------- |
| 1    | Deploy v2 server with seed-envelope generation but feature flag OFF                                       |
| 2    | Pre-IDV: do nothing. Post-IDV: generate envelopes on next verification, store, don't yet require them     |
| 3    | Update wallet to read seed-envelope if present, use new derivation; fall back to wallet_secret if absent  |
| 4    | Enable flag for new wallets. Old wallets continue on `wallet_secret` path until next IDV                  |
| 5    | After ~90 days, deprecate the legacy wallet_secret PPID path. Anonymous flows continue on their own path. |


**Risk:** Two derivation paths during migration window. Carefully namespaced (legacy uses `wallet_secret`, post-IDV uses `wallet_local_seed`). Cross-checks: server-derived and client-derived PPIDs must always match.

### 1.2 Make `master_credential_id` optional in server flows

**Problem:** `/api/ishuman/derive-site-proof` requires `master_credential_id` in the body. The wallet's `findIsHumanMasterCredential()` is on the critical path. This couples the master VC to runtime correctness — a wallet that lost its local master copy can't issue site proofs even though the server has all needed state.

**Concrete change in `api/ishuman.py`:**

```python
# Today:
master_credential_id = body.get("master_credential_id")
if not master_credential_id or not wallet_id or not target_site:
    return jsonify({"success": False, "error": "..."}), 400

master = db.query(IsHumanVerification).filter_by(
    credential_id=master_credential_id, wallet_id=wallet_id, status="verified"
).first()
if not master:
    return jsonify({"success": False, "error": "master_credential_not_found"}), 404

# v2:
master_credential_id = (body.get("master_credential_id") or "").strip()
if not wallet_id or not target_site:
    return jsonify({"success": False, "error": "..."}), 400

# Hint-based lookup: prefer the body's hint, fall back to latest verified.
master = None
if master_credential_id:
    master = db.query(IsHumanVerification).filter_by(
        credential_id=master_credential_id, wallet_id=wallet_id, status="verified"
    ).first()
if not master:
    master = (
        db.query(IsHumanVerification)
        .filter_by(wallet_id=wallet_id, status="verified")
        .order_by(IsHumanVerification.verified_at.desc())
        .first()
    )
if not master:
    return jsonify({"success": False, "error": "wallet_not_verified"}), 403
```

Update the wallet's `deriveAndStoreSiteProof` in `lemma-wallet.js` to omit `master_credential_id` when not available locally.

**Test additions** (`tests/test_derive_site_proof.py`):

- Request without `master_credential_id` succeeds when wallet has verified IDV
- Request with valid `master_credential_id` hint still works
- Request with stale hint falls back to latest verified
- Request for unverified wallet returns `wallet_not_verified`

### 1.3 Add `/api/ishuman/reissue-master` endpoint

**Problem:** If a wallet loses its local master VC (clear IndexedDB, new device, etc.), there's no way to re-fetch it. Today the only "recovery" is re-IDV.

**Endpoint design:**

```python
@ishuman_bp.route("/api/ishuman/reissue-master", methods=["POST"])
@cross_origin()
def reissue_master_credential():
    """Reissue a fresh master credential for an already-verified wallet.

    Auth: wallet_assertion proving possession of the wallet's signing key.
    No fresh IDV required — the wallet was already verified, we just hand
    back a fresh signed copy.

    Body: { wallet_id, wallet_assertion: { nonce, signature } }
    Returns: { success: true, credential: <new master VC>, old_credential_id }
    """
    body = request.get_json(silent=True) or {}
    wallet_id = (body.get("wallet_id") or "").strip()
    err, _ = _require_wallet_assertion(body, field_names=["wallet_id"])
    if err:
        return err

    db = SessionLocal()
    try:
        verified = (
            db.query(IsHumanVerification)
            .filter_by(wallet_id=wallet_id, status="verified")
            .order_by(IsHumanVerification.verified_at.desc())
            .first()
        )
        if not verified:
            return jsonify({"success": False, "error": "wallet_not_verified"}), 404

        # Revoke old master credential id (lemma.id-scoped)
        old_id = verified.credential_id
        new_credential = _issue_ishuman_credential(
            ppid=verified.ppid,
            wallet_id=wallet_id,
            ppid_derivation=(verified.metadata_json or {}).get("ppid_derivation"),
        )
        verified.credential_id = new_credential["id"]
        verified.metadata_json = {
            **(verified.metadata_json or {}),
            "reissued_from": old_id,
            "reissued_at": int(time.time()),
        }
        # Add old master to RevocationList so leaked copies can't be replayed.
        db.add(RevocationList(
            lemma_id=old_id, credential_id=old_id,
            lemma_type="ishuman", revocation_type="credential",
            revoked_by="reissue_master", reason="superseded by reissue",
        ))
        db.commit()
        invalidate_bloom_filter_cache()
        return jsonify({"success": True, "credential": new_credential, "old_credential_id": old_id})
    finally:
        db.close()
```

Rate-limit: at most 5 reissues per wallet per day (env-tunable). Standard `Flask-Limiter` decorator.

**Test additions:**

- Verified wallet can reissue
- Unverified wallet gets 404
- Reissued credential has new ID, same PPID
- Old credential ID lands in Bloom snapshot
- Reissue rate-limited

---

## Phase 2 — Bridge elimination

### 2.1 Remove the bridge iframe

**Problem:** The `<iframe src="lemma.id/wallet/bridge">` model was designed before Chrome's storage partitioning rolled out. Today a third-party iframe of lemma.id cannot reliably see the wallet's storage. The popup-first design we deployed works around this, but the bridge still exists as a fallback, and both code paths can drift (we've hit several bugs from divergence).

**Concrete deletions:**

In `static/js/ishuman-verifier.js`:

- Remove `_setupBridge()` and `_bridgeIframe` field
- Remove `_requestSessionFromBridge`, `_requestCredentialFromBridge`, `_sendBridgeRequest`
- Remove `BRIDGE_PATH`, `BRIDGE_TIMEOUT_MS`
- Remove `_pendingRequests` Map and the `message` event listener that handles bridge responses
- Remove `_handleBridgeMessage`
- Remove `_syncBridgeAfterIdv` and `_syncBridgeAfterUnlock` (popup now handles all sync)

In `templates/wallet_bridge.html`:

- Delete the file entirely

In `api/ishuman.py`:

- Delete the `@app.route('/wallet/bridge')` handler
- Delete `/api/wallet/bridge-audit`

**New verify flow (popup-only):**

```text
SDK.verify():
  1. Check ishuman_site_vc:v1:<siteId> localStorage cache → if valid, return
  2. Check Bloom + trust list (local cache or refresh)
  3. If no cache hit:
        Open popup at /wallet/ishuman-idv?issue_mode=site_proof&...
        Popup runs ensureIsHumanIssuanceReady, derives site proof, returns
     If user has no master yet: popup runs IDV first (Stripe or test mode)
  4. Verify the returned credential locally (browser-canonical Ed25519)
  5. Cache to localStorage
  6. Return result
```

**Trade-off:** First verify in a fresh tab has a popup flash (~~500 ms). Subsequent verifies hit localStorage (~~3 ms). Net UX is cleaner than today's hybrid where the bridge sometimes works and sometimes doesn't.

**Implementation steps:**

1. Add a feature flag `LEMMA_DISABLE_BRIDGE_IFRAME` checked by `IsHumanVerifier` constructor
2. When flag is on, never call `_setupBridge()`; route all credential requests through popup
3. Update tests to expect popup-only path
4. Roll out to demo apps first, then production after a week of clean operation
5. Delete the bridge code paths once stable

**Risk:** Popup blockers. Mitigation: every popup open is on a user gesture (click handler), never auto-fire.

### 2.2 Drop the daily-unlock bundle, use per-popup unlock

**Problem:** "One passkey per day" persistence requires a `lemma_ishuman_lock:v1` localStorage bundle that survives reloads. This bundle has been the source of multiple bugs (`envelope_invalid`, stale state across storage partitioning, encrypted credential reads without PRF key).

**v2 design:** Each popup invocation does its own passkey check if needed. With `userVerification: "preferred"` and modern browser credential discovery, recently-authenticated users may not see a prompt at all (browser handles "I just passkey'd" silently).

**Concrete change:**

In `lemma-wallet.js`:

- Remove `_persistIsHumanLockBundle`, `_restoreIsHumanLockBundleIfValid`, `_clearIsHumanLockBundle`, `isIsHumanLockValid`
- Remove the `ISHUMAN_LOCK_STORAGE_KEY` localStorage entry
- Simplify `ensureIsHumanIssuanceReady` to: try in-memory session → try IndexedDB session restore → if neither has PRF key for encrypted data → run passkey unlock

In `templates/wallet_ishuman_idv.html`:

- The popup's `ensureWalletUnlocked` now does a fresh passkey gesture each open (unless the wallet's in-memory state has a valid PRF key, which it will if the popup was just opened from the same lemma.id context with a recent unlock)

**Risk:** Users may see more passkey prompts than today's "once per day" feel. Mitigated by browser credential discovery + silent re-auth on recent auth events. Need to A/B test the perceived friction.

---

## Phase 3 — Operational hardening

### 3.1 Design pepper/salt rotation

**Problem:** `LEMMA_IDENTITY_ROOT_PEPPER_V1` and `LEMMA_PERSON_ROOT_SALT_V1` are network-root secrets. If compromised, an attacker can compute `person_root` for any documents they know. No rotation path exists today.

**v2 design — versioned, overlapping:**

1. Maintain `LEMMA_IDENTITY_ROOT_PEPPER_V1`, `_V2`, etc. concurrently in env config
2. Each `IsHumanVerification` row has `root_version` column (already exists, partially used). Mark which pepper version produced its `document_root_hash`.
3. Active pepper version is configurable (`LEMMA_ACTIVE_ROOT_VERSION=V2`)
4. New IDVs use the active version
5. Old rows continue working until their credential expires (default 2 years from `ISHUMAN_CREDENTIAL_TTL_DAYS`)
6. Eventually retire old version when no active rows reference it

**Concrete additions:**

In `api/identity_roots.py`:

```python
def _get_identity_root_pepper(version: str = None) -> bytes:
    version = version or os.environ.get("LEMMA_ACTIVE_ROOT_VERSION", "V1")
    env_key = f"LEMMA_IDENTITY_ROOT_PEPPER_{version}"
    val = os.environ.get(env_key)
    if not val or len(val) < 32:
        raise RuntimeError(f"missing or short pepper: {env_key}")
    return val.encode("utf-8")

def _get_person_root_salt(version: str = None) -> bytes:
    # Same shape
```

In `_complete_verified_ishuman_from_stripe`:

```python
active = os.environ.get("LEMMA_ACTIVE_ROOT_VERSION", "V1")
record.root_version = active
record.document_root_hash = compute_document_root_hash(material, version=active)
```

**Cross-version PPID continuity (UX cost):**

A user verified pre-rotation has different PPIDs than post-rotation. To preserve identity continuity across rotation:

- The new master VC issued post-rotation carries a `legacy_ppid` claim if the wallet has a pre-rotation record
- Sites that opt in honor the legacy PPID for migration (treat user as the same identity)

This is a UX cost — sites must do the migration, or accept that rotation creates a discontinuity. Acceptable as an emergency operation, not a routine one.

### 3.2 Multi-issuer trust list

**Problem:** Stripe Identity is the only configured IDV provider. Trust list architecture already supports multiple issuers but only one is integrated.

**v2 design:**

1. Add a second issuer (Persona or Veriff)
2. Each issuer has its own pepper: `LEMMA_IDENTITY_ROOT_PEPPER_<ISSUER>_V1`
3. `IsHumanVerification` gets an `issuer_id` column (`"stripe_identity"`, `"persona"`, etc.)
4. Trust list publishes all active issuers; relying sites verify any signature from any listed issuer
5. Reissuance / reset works regardless of which issuer originally verified

**Implementation effort:** ~2-3 weeks per additional issuer (webhook integration, document canonicalization, error handling, billing).

Defer until the first issuer is stable at production scale and there's a business case for redundancy.

### 3.3 Bloom filter scaling

**Problem:** Current Bloom is global, sized for ~100K capacity at 1e-6 FPR. Beyond ~1M revocations, false positives become operationally meaningful.

**Two options:**

**Option A — Cascaded Bloom (CRLite-style):**

```text
Layer 1: large Bloom of all revoked credential IDs (FPR ~1e-3)
Layer 2: smaller Bloom of false positives from layer 1
         (real credentials that hash-collide with revoked ones)
Layer 3 (if needed): smaller still

Verify: query layer 1 → if hit, query layer 2 → if hit, NOT REVOKED
         (because the credential is a known false positive of layer 1)
        otherwise: revoked

Net FPR: 1e-6 with ~4x smaller total size vs. single Bloom
```

Add a Rust/C++ helper for cascade construction (Mozilla's `filter-cascade` crate).

**Option B — Per-issuer partitioned Bloom:**

Each issuer publishes its own Bloom for credentials it issued. Clients fetch only the Bloom for the issuer whose credential they're verifying.

Simpler than cascaded; requires multi-issuer to be in production first.

**Decision criteria:** Pick when revocation volume exceeds ~500K (well in advance of operational issues). Both are well-understood patterns.

---

## Phase 4 — Recovery & transfer

### 4.1 Document re-IDV as the primary recovery path

**Problem:** Re-IDV restores everything (post-Phase 1 changes), but it's undocumented and users don't know it's an option.

**Concrete change:**

1. Add a "Lost your device?" affordance in the lemma.id wallet UI that explains: "Verify identity → restore your network identity across all sites."
2. Add docs at `/docs/wallet/recovery` explaining the model: identity lives in the network, not the device.
3. Marketing: lead with "you can never lose your verified-human status, only the device that held your wallet."

No code change required beyond ensuring Phase 1.3 (reissue master) is shipped — re-IDV + reissue gives the full recovery story.

### 4.2 Explicit cross-device wallet transfer (QR-based)

**Problem:** `_processCredentialTransferToken` exists but is URL-fragment based. Not the primary UX. Best for users who explicitly want to transfer without re-IDV.

**v2 design:**

1. "Add device" button in wallet UI → generates a one-time QR code with:
  - `wallet_id`
  - One-time challenge nonce signed by wallet
  - Short TTL (60 s)
2. New device scans QR → exchanges with server via `POST /api/wallet/sync-device`
3. Server validates signature against the wallet's registered signing pubkey
4. Server returns:
  - `seed_envelope` (Phase 1.1 artifact, encrypted under a fresh transient key the new device proposes)
  - Master VC (re-fetched fresh)
  - Per-site VCs the user opts to transfer
5. New device decrypts and stores under its own passkey

**Implementation:** Re-uses Phase 1.1 envelope machinery. Mostly UI + endpoint plumbing.

---

## Phase 5 — Documentation & tests

### 5.1 Pin cryptographic invariants in tests

**Problem:** The system has crypto invariants enforced only by code. Refactoring can silently break them. Need lock-in.

**New test file `tests/test_cryptographic_invariants.py`:**

```python
def test_ppid_derivation_is_deterministic():
    """Same (person_root, site) → same PPID, byte-exact."""
    person_root = bytes.fromhex("a" * 64)  # known input
    site = "example.com"
    ppid = derive_ppid_from_person_root(person_root, site)
    assert ppid == "did:lemma:ppid_<expected_hex>"  # known output

def test_document_root_canonicalization_is_stable():
    """Same document fields → same document_root."""
    material = StripeIdentityRootMaterial(
        country="US",
        document_type="driving_license",
        document_number="D1234567",
        date_of_birth="1985-03-12",
    )
    root = compute_document_root(material)
    assert root.hex() == "<expected hex>"

def test_browser_canonical_message_byte_pin():
    """JS canonicalMessage() and Python _browser_canonical_message() agree."""
    credential = {...}  # fixed input
    py_bytes = _browser_canonical_message(credential)
    js_bytes_expected = b'{"issuer":...}'  # produced by running the JS once and pinning
    assert py_bytes == js_bytes_expected

def test_session_presentation_payload_format():
    """The newline-joined session_assertion payload must remain stable."""
    assertion = {...}  # fixed input
    payload = build_session_presentation_payload(assertion)
    assert payload == b"lemma:site-session-presentation:v1\n<...>"

def test_wallet_signing_key_derivation():
    """HKDF(wallet_seed, "wallet-signing-key-v1") yields the same key."""
    seed = bytes.fromhex("..." * 4)
    key = derive_wallet_signing_key(seed)
    assert key.public_key_hex() == "<expected pubkey hex>"
```

These should be the first tests to break if anyone introduces a canonical-format-changing refactor. Each pinned value must be produced by running the live code once and copy-pasting.

### 5.2 Threat model document

**New file `docs/security/THREAT_MODEL.md`:**

Structure:

```markdown
# Lemma isHuman Threat Model

## 1. Actors and trust assumptions
- Real human (the user)
- Wallet (browser process + IndexedDB + passkey)
- Relying site (frontend SDK + backend verifier)
- Lemma.id network (issuer, trust list publisher, Bloom snapshot publisher)
- IDV provider (Stripe Identity, etc.)
- Adversaries (see §3)

## 2. Trust assumptions (the things we believe)
- Browser WebCrypto correctly implements Ed25519, SHA-256, HKDF
- Passkey + PRF extension protects the wallet's at-rest key
- IDV provider correctly verifies identity documents
- LEMMA_IDENTITY_ROOT_PEPPER_V* and LEMMA_PERSON_ROOT_SALT_V* are kept secret
- The issuer's Ed25519 signing key is kept secret
- Network-trusted issuer DIDs are pinned in clients

## 3. Adversary capabilities and guarantees

### 3.1 Network observer (sees TLS-decrypted lemma.id traffic)
- Can see: PPIDs in transit, credential bodies, revocation events
- Cannot see: wallet_secret, person_root (server-side only), browser passkey

### 3.2 Compromised relying site (RP backend has all bytes it sees)
- Can see: per-site VC + PPID for users at that site
- Cannot see: PPIDs at other sites (pairwise unlinkability)
- Cannot forge VCs (issuer signature required)
- Cannot revoke (Lemma controls Bloom)

### 3.3 Compromised wallet (attacker exfiltrates IndexedDB)
- If passkey not stolen: encrypted data is unreadable (PRF key gated by passkey)
- If passkey also stolen (e.g. user shared device): attacker can act as wallet
  until revocation, but cannot mint credentials for different identity

### 3.4 Compromised browser (malware in browser process)
- Can read decrypted wallet contents during a passkey-unlocked session
- Cannot persist (each unlock is per-session)

### 3.5 Compromised IDV provider (Stripe Identity fooled by a fake document)
- Network mints a credential for a fraudulent identity
- Mitigated by: multi-issuer triangulation, ongoing document quality monitoring

### 3.6 Compromised Lemma.id (pepper/salt or issuer key exposed)
- pepper/salt exposure: attacker can compute PPIDs given documents
  → privacy guarantee broken; identity continuity unaffected
  → mitigation: pepper/salt rotation (Phase 3.1)
- Issuer key exposure: attacker can mint arbitrary credentials
  → trust list rotation cuts off old issuer key; clients refetch
  → mitigation: multi-issuer (Phase 3.2)

## 4. Failure modes
- What fails open (degraded UX)
- What fails closed (security violation impossible)

## 5. Things this design does NOT protect against
- Coerced IDV (gunpoint identity verification)
- Government-mandated key escrow
- Side-channel attacks on the browser
- Physical compromise of a device with an unlocked wallet
```

Fill in details from current implementation. Make it living document; update with each Phase.

### 5.3 Canonical message specification

**New file `docs/cryptographic/CANONICAL_MESSAGES.md`:**

For each signed payload in the system, document:

- Inputs (named fields, types)
- Canonicalization rules (e.g., "claims sorted by key", "JSON.stringify with no whitespace", "newline-joined with \n")
- Test vectors (input bytes → expected output bytes)

Cover:

- isHuman credential `signatureValueWeb` canonical message
- Session presentation payload
- Wallet assertion payload
- Bloom snapshot envelope
- Trust list envelope

Third-party SDKs (Go, Rust) need this to produce verifiable signatures. Without a spec, they reverse-engineer from the JS reference and miss edge cases.

---

## Phase 6 — Demo / production split

### 6.1 Run two Heroku apps

**Problem:** `lemma-enterprise` Heroku app has `ENVIRONMENT=production`, which:

- Suppresses `demo_test_token` and `demo_admin_token` from popup HTML rendering
- Causes `/api/demo/ishuman/verify-once-test-mode` to return `prod_test_verify_forbidden`
- Causes `/api/demo/ishuman/self-reset` to return `not_available_in_production`

But the same app serves the demo at `lemma.id/demo/ishuman`. Demo and production semantics fight each other.

**v2 design — two apps:**


| App                                          | Purpose                     | ENVIRONMENT  | Demo endpoints | Real customers |
| -------------------------------------------- | --------------------------- | ------------ | -------------- | -------------- |
| `lemma-enterprise`                           | Production identity network | `production` | disabled       | yes            |
| `lemma-enterprise-demo` (or `lemma-staging`) | Demo + staging              | `staging`    | enabled        | no             |


The demo subtree apps (`lemma-demo-tickets`, `lemma-demo-trials`) point at the **demo app** by setting `LEMMA_ORIGIN=https://demo.lemma.id` (or wherever staging lives).

**Concrete actions:**

1. Provision new Heroku app: `heroku create lemma-staging --remote lemma-staging`
2. Copy all relevant env vars from `lemma-enterprise`:
  ```bash
   heroku config -a lemma-enterprise --json \
     | jq 'with_entries(select(.key | test("LEMMA|STRIPE|DATABASE_URL")))' \
     | jq -r 'to_entries | map("\(.key)=\(.value)") | join("\n")' \
     | xargs -L 1 heroku config:set --app lemma-staging
  ```
3. Override `ENVIRONMENT=staging` and set demo tokens
4. Point a domain at it (e.g., `demo.lemma.id`)
5. Update demo subtree apps' `LEMMA_ORIGIN` to point at `https://demo.lemma.id`
6. Production `lemma.id` only serves real customers; demo lives under demo.lemma.id

**Risk:** Operationally simple but takes a few hours to provision and verify.

### 6.2 Document the env var contract

**New file `docs/operations/ENVIRONMENT_CONFIG.md`:**

Table of every env var the system reads, what it does, what the production vs staging values should look like, and what breaks if it's missing.

This is the single most important operational artifact. Without it, future maintenance is archaeology.

---

## Acceptance criteria (per phase)

Each phase should ship with:

1. All existing tests pass
2. New tests covering the changed behavior
3. A short post-deploy verification script that hits the relevant endpoints and asserts expected responses
4. A rollback note: what env var or feature flag reverts the change
5. A migration note in `CHANGELOG.md`: what users / integrators must do, if anything

Sample post-deploy verification (Phase 1.2):

```bash
#!/bin/bash
# Test that derive-site-proof now works without master_credential_id
TOKEN=$(your_test_token)
WALLET=wallet_test_xxxxx
SITE=test-site.example.com

curl -s -X POST https://lemma.id/api/ishuman/derive-site-proof \
  -H "Content-Type: application/json" \
  -d "{\"wallet_id\": \"$WALLET\", \"target_site\": \"$SITE\", \"wallet_assertion\": {...}}" \
  | jq '.success'
# Expected: true
```

---

## Out of scope for v2

These improvements are deliberately deferred:

- Migration to Verifiable Credentials Data Model 2.0 (current code uses VCDM 1.0 with custom extensions)
- Zero-knowledge proof attestations (would let users prove "isHuman" without revealing PPID; nice but huge scope)
- Decentralized issuer model (multi-org issuers, not just multi-vendor)
- Real-time push of revocations via WebSocket / SSE (today's 15-minute Bloom refresh is acceptable)
- Mobile app wallets (web-only for now)

These are good v3 candidates after v2 lands.

---

## Open questions for the agent

If you (the next agent picking this up) hit any of these, surface them to a human before guessing:

1. **Pepper rotation policy:** Do we accept identity discontinuity across rotations, or do we publish migration tables? (Section 3.1)
2. **Master credential expiry:** Today's 2-year default — change for v2, or keep?
3. **Wallet local seed storage format:** Encrypt under passkey PRF directly, or wrap in a per-device key first?
4. **Demo app domain:** `demo.lemma.id` (clean) or `staging.lemma.id` (clearer)? Branding choice.
5. **Re-issuance rate limit:** Per wallet per day, per IP per day, both?

When in doubt, do the simpler thing and document the choice.

---

## Final note

The current design's smart parts are:

- Document-anchored identity (person_root from documents)
- Pairwise PPIDs (HMAC, well-grounded)
- Portable signed credentials with local Ed25519 verify
- Bloom-based revocation that doesn't leak credential IDs
- Per-site signing keys for proof of possession
- Pepper + salt separation as defense-in-depth

Do not change those. They are the architectural foundation. Everything in this document is about cleaning up the bookkeeping around them — not replacing the core.

If a v2 change you're considering would alter any of those primitives, stop and ask first.