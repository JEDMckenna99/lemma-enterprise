# lemma.id Browser Storage Contract

Status: **Active contract** (canonical)  
Audience: Platform engineers, lemma.id SDK maintainers, security reviewers, AI agents working on wallet storage  
Code sources of truth: `static/js/lemma-wallet.js`, `static/js/wallet-at-rest-crypto.js`  
Related: [`LEMMA_ID_PRESENTATION_MODEL.md`](../product/LEMMA_ID_PRESENTATION_MODEL.md) (proofs), [`THREAT_MODEL.md`](THREAT_MODEL.md) (adversaries), [`WALLET_COOKIE_SAMESITE.md`](WALLET_COOKIE_SAMESITE.md) (cookies)

> Prefer the product noun **lemma.id** for the user-held identity store. Internal code may say `wallet_*` (`LemmaWallet`, IndexedDB `LemmaWallet`, `wallet_secret`). Do not invent new user-facing "wallet" language.

This document is the **single source of truth** for what lemma.id persists in the browser, how it is encrypted, and when each write happens. Older architecture notes, Phase 5 diaries, and design improvement docs are historical; if they disagree with this contract or the code above, **this contract + code win**.

---

## 1. Why this contract exists

The user-held identity object accumulated several generations of storage:

| Era | Identity / storage idea | Residue |
|-----|-------------------------|---------|
| Early | Single `wallet_secret` in IndexedDB | `secrets/master` |
| Profiles | Per-profile secret hex | `profiles/{id}.secret` |
| isHuman / person_root | Seed envelopes + dual PPID paths | session seeds, server envelopes |
| Phase 5 | PRF AES-GCM `enc_v1` envelopes | `wallet_meta.migrationComplete` |
| Daily unlock | localStorage bundle (now wrapped) | `lemma_ishuman_lock:v1` + `LemmaWalletWrap` |

Without one inventory, plaintext fallbacks and dual write paths look “normal” in DevTools. This contract defines the **intended steady state** and the **allowed transitional states**.

---

## 2. Storage surfaces (overview)

| Surface | Name / keys | Role |
|---------|-------------|------|
| IndexedDB | `LemmaWallet` (schema v7) | Primary lemma.id credential store |
| IndexedDB | `LemmaWalletWrap` | Non-extractable device wrap key for daily unlock |
| localStorage | `lemma_*`, `ishuman_*` (listed below) | Daily unlock bundle, prefs, verifier caches, optional backups |
| sessionStorage | Enrollment grant (+ legacy lock key migration) | Short-lived only |
| Cookies | `lemma_wallet_session`, `lemma_wallet_csrf`, `lemma_csrf_token` | Server session / CSRF — **not** local identity seeds |
| Cache Storage | `lemma-v19` (service worker) | Static assets only — **never** secrets or credentials |

Relying-site origins may hold **site VC / session presentation caches** via the verifier SDK. They must **never** persist `wallet_secret` / profile secrets (`_canPersistWalletSecret()` is lemma.id / local-dev only; third-party secrets are scrubbed).

---

## 3. Identity material (what the hex “secret” is)

| Name (code) | What it is | Not |
|-------------|------------|-----|
| `wallet_secret` / profile `secret` | 32-byte CSPRNG value as 64-char hex; root for legacy / anonymous PPID and site signing derivation | A password, hash, or ciphertext blob |
| PRF at-rest key | 32 bytes from WebAuthn PRF → non-extractable AES-GCM `CryptoKey` (`_atRestKey`) | Stored as extractable bytes in IDB |
| Device wrap key | Non-extractable AES-GCM key in `LemmaWalletWrap` | Readable key material in JS |
| `walletLocalSeed` / person-root proxies | Post-IDV seed path (feature-flagged); see V2 design notes | Replacement for all wallets yet |

**PPID (account continuity handle):** derived from secret material + canonical hostname. A PPID is **not** an authentication secret. See presentation model + human-auth security contract.

**In-memory while unlocked:** decrypted `walletSecret` lives on `this.session`. XSS on lemma.id during the unlock window can read it — accepted residual risk in the threat model; at-rest encryption does not solve XSS.

---

## 4. Encryption model

### 4.1 PRF envelopes (`enc_v1`)

1. Passkey create / unlock obtains PRF output → `importStorageKey` → `_atRestKey`.
2. Sensitive stores write through `_put` → `_encryptStoredValue` → `encryptEnvelope`.
3. Envelope shape:

```json
{
  "__enc": "enc_v1",
  "store": "profiles",
  "id": "default",
  "iv": "<base64url>",
  "ciphertext": "<base64url>"
}
```

4. AAD binds ciphertext to `enc_v1:{store}:{recordId}`.
5. **Sensitive stores:** `secrets`, `profiles`, `session`, `lemmas`, `ishuman_cache` (`WalletAtRestCrypto.SENSITIVE_STORES`).

### 4.2 Migration

- `_migratePlaintextStores()` runs after a successful PRF bind.
- Rewrites plaintext sensitive rows as `enc_v1`, then sets `wallet_meta.storage.migrationComplete = true`.
- **After migration:** missing at-rest key → fail closed (`storage_key_unavailable` / `prf_required_for_encrypted_storage`).
- **`ishuman_cache`:** always requires an at-rest key (no plaintext fallback).

### 4.3 No plaintext write fallback (fail closed)

`_encryptStoredValue` **never** persists sensitive stores as plaintext JSON. If `_atRestKey` is missing, it throws `storage_key_unavailable`. Register and local unlock throw `prf_required_for_encrypted_storage` when WebAuthn PRF output is unavailable.

| State | DevTools appearance | Verdict |
|-------|---------------------|---------|
| Legacy rows before first PRF unlock after upgrade | Cleartext `secret` / VC JSON still on disk | **Migration debt** — rewritten on next successful PRF unlock via `_migratePlaintextStores()` |
| Post-PRF migration | `__enc: "enc_v1"` envelopes | **Healthy** |
| New writes as cleartext sensitive JSON | Should not happen | **Bug** |
| Authenticator without PRF | Register/unlock fails with `prf_required_for_encrypted_storage` | **Expected** (see `BROWSER_SUPPORT.md`) |

### 4.4 Exceptions (intentionally not JSON-enveloped)

| Record | Why |
|--------|-----|
| `secrets/device_signing` | Non-extractable `CryptoKey`; structured-clone via `_putRaw` only |
| `secrets/device_meta` | Device id/name metadata; low sensitivity; `_putRaw` |
| Non-sensitive stores | `passkey`, `issuers`, `revocations`, `wallet_meta` stay plaintext |

### 4.5 Daily unlock wrap (`wrap_v1`)

- Key: `localStorage` → `lemma_ishuman_lock:v1` (≤10h window; default session hours clamped to 10).
- Metadata (walletId, expiry, flags) may be cleartext for sync validity checks.
- Sensitive payload (`walletSecret`, `atRestKeyB64`) must live only under `bundle.sec` with `__wrap: "wrap_v1"`.
- Wrap key: non-extractable AES-GCM in IndexedDB `LemmaWalletWrap` / `keys` / `device-unlock-wrap:v1`.
- **Fail closed:** if wrap unavailable, do **not** persist plaintext `walletSecret` in localStorage.
- **Legacy:** bundles that still have top-level `walletSecret` are upgraded on next successful restore.

Stale comments in code that claim the daily bundle “persists walletSecret in plaintext localStorage” are **wrong** relative to current behavior; trust this contract and `_persistIsHumanLockBundle()`.

---

## 5. IndexedDB inventory — `LemmaWallet`

Schema version: **7** (`WALLET_DB_VERSION`).

### 5.1 Sensitive stores (must be `enc_v1` after migration)

| Store | Key(s) | Contents | When written |
|-------|--------|----------|--------------|
| `secrets` | `master` | `{ id, secret, createdAt, source?, … }` — active identity seed | Passkey create, unlock, profile sync, device link persist |
| `secrets` | `person_root_seeds` | Intended seed persistence (treat as critical if present) | Seed persist helpers |
| `profiles` | `{profileId}` e.g. `default` | `{ id, name, secret, createdAt, isDefault, linkedFrom? }` | Default migrate, create/rename profile, link |
| `session` | `current` | Unlock state including `walletSecret` while unlocked | Unlock / register / restore / link |
| `session` | `verified_{lemmaId}` | Signature verification cache entries | Verify hydrate paths |
| `lemmas` | `cred_*`, `ishuman_*`, … | VCs, permission lemmas, isHuman credentials | `storeLemma` / credential import; isHuman pruned to 1 master + ≤1 site identity VC per hostname |
| `ishuman_cache` | cache keys | Mirror of durable isHuman identity slots for lock-period reads | Sync/import; pruned with `lemmas` |

### 5.2 Non-sensitive / special stores

| Store | Key(s) | Contents | At rest |
|-------|--------|----------|---------|
| `passkey` | `primary` | credentialId, publicKey, algorithm, attestation, `prfEnabled`, salts | Plaintext |
| `passkey` | `walletId`, `activeProfile` | Wallet / profile pointers | Plaintext |
| `secrets` | `device_meta` | deviceId, deviceName | Plaintext (raw) |
| `secrets` | `device_signing` | Ed25519 CryptoKey handle + publicKeyB64 | Structured clone (not envelope) |
| `issuers` | `{did}` | Issuer public key metadata | Plaintext |
| `revocations` | `current` | Revocation ids + lastSynced | Plaintext |
| `wallet_meta` | `storage` | `prfEnabled`, `migrationComplete`, `migratedAt`, `prfSaltRpId` | Plaintext |

---

## 6. IndexedDB inventory — `LemmaWalletWrap`

| Store | Key | Contents | At rest |
|-------|-----|----------|---------|
| `keys` | `device-unlock-wrap:v1` | Non-extractable AES-GCM `CryptoKey` | Handle only; raw bytes never extractable to JS |

Created on first `wrapBundle` / `getDeviceWrapKey()`.

---

## 7. Web storage keys

### 7.1 localStorage (lemma.id / shared prefixes)

| Key | Sensitivity | Contents / rules |
|-----|-------------|------------------|
| `lemma_ishuman_lock:v1` | High (wrapped) | Daily unlock; `sec` must be `wrap_v1`; no new plaintext `walletSecret` |
| `lemma_session_hours` | Low | Preference; clamped ≤10h |
| `lemma_redirect_state` | Medium | Cross-origin redirect resume |
| `lemma_log_level` | Low | Debug |
| `lemma_wallet_backups` | **Critical if opted in** | Last N backups; secrets only when `lemma_allow_sensitive_local_backup=true` |
| `lemma_allow_sensitive_local_backup` | Control | Opt-in for sensitive backups |
| `lemma_had_global_session`, `lemma_debug_auth`, register pending/result/error keys | Low–medium | UX / debug / register handoff |
| `ishuman_site_vc:v1:{siteId}`, `ishuman_session_v1:{siteId}` | Medium | Verifier site VC / session cache (not wallet_secret) |
| `ishuman_bloom`, `ishuman_trust_list` | Low–medium | Public crypto material |
| `ishuman_master_provisioned_v1`, `ishuman_idv_popup_session_id` | Low | Flags / ceremony |

Exact wipe list: `LemmaWallet.LEMMA_STORAGE_EXACT_KEYS` + prefixes `lemma_`, `ishuman_`, `__lemma_`.

### 7.2 sessionStorage

| Key | Role |
|-----|------|
| `lemma_enrollment_grant` | Short-lived device enroll grant (~5 min TTL) |
| `lemma_ishuman_lock:v1` (legacy) | Migrated to localStorage on read |

### 7.3 Cookies

Server-set; see [`WALLET_COOKIE_SAMESITE.md`](WALLET_COOKIE_SAMESITE.md). Client JS may read CSRF cookies only — never treat cookies as the local identity seed store.

| Cookie | HttpOnly | Holds wallet_secret? |
|--------|----------|----------------------|
| `lemma_wallet_session` | yes | **No** |
| `lemma_wallet_csrf` | no | **No** |
| `lemma_csrf_token` | no | **No** |

### 7.4 Cache Storage

Service worker cache `lemma-v19`: static assets. Cleared on full device purge. **Must not** contain secrets or VCs.

### 7.5 Legacy (non-canonical)

`encrypted-wallet-transparent.js` / fingerprint-derived localStorage credential blobs used by older bot-shield paths are **not** the LemmaWallet PRF model. Do not extend them for new lemma.id identity storage.

---

## 8. Lifecycle (when writes happen)

```text
Create passkey
  → bind PRF (if available) → migrate plaintext → write passkey + secrets/master + profiles
  → unlock session → optional daily unlock wrap on lemma.id

Unlock (passkey)
  → bind PRF → migrate if needed → read/decrypt secrets & profiles
  → session.current (+ server cookie sync on lemma.id)
  → persist daily unlock wrap

Daily restore (same browser, lock valid)
  → unwrap localStorage bundle → restore session + _atRestKey in memory
  → upgrade legacy plaintext bundle if present

Store credential / lemma
  → lemmas (+ ishuman_cache when applicable) via encrypted _put

Lock / purge / revoke device
  → clear session + lock bundle; full purge deletes LemmaWallet + LemmaWalletWrap + lemma_/ishuman_ keys + caches
```

**Origin rule:** persist identity seeds only on lemma.id (and local-dev hosts treated as lemma). Third-party origins scrub `secrets/master` and session `walletSecret`.

---

## 9. Invariants (must hold)

1. After `migrationComplete`, new writes to sensitive stores are `enc_v1` or fail closed.
2. `ishuman_cache` never persists without an at-rest key.
2b. Durable isHuman identity storage is bounded: **1** `ishuman_master_*` and **≤1** site identity VC per canonical hostname (highest assurance wins; superseded ids deleted from `lemmas` + `ishuman_cache` via `pruneIsHumanCredentialsLocally`).
3. Daily unlock never newly persists plaintext `walletSecret` in localStorage.
4. Third-party origins never keep `wallet_secret` / profile secrets at rest.
5. Cache Storage never holds identity seeds or credentials.
6. Cookies never hold `wallet_secret`.
7. `device_signing` never goes through JSON envelope encryption.
8. Opt-in backups are the only supported path for plaintext secret copies in localStorage — off by default.
9. User-facing copy says **lemma.id**, not "wallet"; storage DB names may remain `LemmaWallet*` for compatibility.

---

## 10. DevTools triage

| Observation | Interpretation |
|-------------|----------------|
| Sensitive rows are `{ __enc: "enc_v1", … }` | Healthy PRF wallet |
| Cleartext 64-hex `secret` in `profiles` / `secrets` | Legacy rows pending PRF migration — unlock once with PRF-capable passkey |
| `wallet_meta.storage.migrationComplete === true` but sensitive plaintext | Bug / incomplete rewrite |
| `lemma_ishuman_lock:v1` has `sec.__wrap === "wrap_v1"` and no top-level `walletSecret` | Healthy daily unlock |
| Top-level `walletSecret` in lock bundle | Legacy; should upgrade on next restore |
| Secrets inside Cache Storage | Bug |
| Hex secret only in memory / console while unlocked | Expected for PPID derivation; XSS threat, not storage bug |

---

## 11. Test pins

| Area | Tests |
|------|-------|
| PRF / encrypted IDB wiring | `tests/test_wallet_prf_storage.py` |
| Daily unlock wrap / fail-closed | `tests/test_wallet_daily_unlock_bundle.py` |
| Threat / crypto invariants | `tests/test_cryptographic_invariants.py` (where applicable) |

When changing storage: update **this contract first** (or in the same PR), then code, then tests.

---

## 12. Doc map (avoid drift)

| Document | Role vs this contract |
|----------|----------------------|
| **This file** | Canonical browser storage inventory + encryption rules |
| `LEMMA_ID_PRESENTATION_MODEL.md` | Identity / permission **proofs**, not disk layout |
| `THREAT_MODEL.md` | Adversary capabilities; links here for storage mechanics |
| `ISHUMAN_LOCAL_FIRST_IMPLEMENTATION_OUTLINE.md` Phase 5 | Historical implementation diary — superseded for inventory |
| `architecture/ARCHITECTURE.md` Data Storage section | Historical snapshot — superseded for browser inventory |
| `architecture/V2_DESIGN_IMPROVEMENTS.md` | Migration / dual-path design history |
| `WALLET_COOKIE_SAMESITE.md` | Cookie SameSite / CSRF detail |
| `WALLET_COMPROMISE_RESPONSE.md` | Operator response (clear site data, reissue) |

---

## 13. Known gaps (honest backlog)

Documented so they are not rediscovered as “undefined behavior”:

| Gap | Notes |
|-----|-------|
| Legacy plaintext rows on disk | Readable until next PRF unlock runs `_migratePlaintextStores()`; new writes never plaintext |
| Authenticators without PRF | Register/unlock fail closed; cannot create or persist new lemma.id identity material |
| Opt-in `lemma_wallet_backups` | Can place secrets in localStorage when enabled |
| XSS during unlock window | Memory / unwrap still exposed; CSP + short lock window mitigate, not eliminate |
| Incomplete seed persist helpers | `person_root_seeds` path historically fragile; verify before relying on it |
| Index helpers bypassing `_get` | e.g. raw IDB index reads may return undecrypted envelopes — treat as bug if user-facing |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-08-03 | Initial active contract; consolidates live `LemmaWallet` v7 + wrap + daily unlock behavior |
| 2026-08-03 | Remove plaintext `_encryptStoredValue` fallback; require PRF on register/unlock |
| 2026-08-05 | One site identity slot per hostname; prune superseded isHuman VCs on sync/derive/import |
