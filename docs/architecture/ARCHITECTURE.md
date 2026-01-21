# Lemma Platform Architecture

*Generated: 2026-01-21 13:56*

## Components

| Component | Type | Description | Files |
|-----------|------|-------------|-------|
| **User Wallet** | client | Browser IndexedDB storage for credentials and secrets | `static/js/lemma-wallet.js` |
| **Wallet Bridge** | client | Cross-origin iframe for SSO session sharing | `templates/wallet_bridge.html` |
| **Crypto Engine (WASM)** | library | Client-side Ed25519 verification and Bloom filter | `lemma-crypto/src/lib.rs`, `lemma-crypto/src/minimal_core.rs` |
| **Third-Party Site** | external | Customer sites using Lemma SDK | - |
| **New Device** | client | Device being linked to existing wallet | - |
| **Lemma Backend** | server | Flask API server - auth, issuance, revocation | `app.py`, `api/lemma_shield.py` |
| **PostgreSQL** | storage | Persistent storage for sites, passkeys, revocations | `api/database.py`, `database_schema.sql` |
| **Redis** | storage | Ephemeral storage for sessions and transfers | - |

## Data Flows

### Auth Flow

| Step | From | To | Data | Privacy |
|------|------|-----|------|---------|
| 1. Passkey registration/auth | wallet | backend | WebAuthn challenge/response | public_key only (private key never leaves device) |
| 2. Session token | backend | wallet | JWT or session cookie | Identifies wallet_id, not user identity |

### Sso Flow

| Step | From | To | Data | Privacy |
|------|------|-----|------|---------|
| 3. Load bridge iframe | site | bridge | iframe src=lemma.id/wallet/bridge | Site origin visible to bridge |
| 4. Check IndexedDB | bridge | wallet | Read session, secrets | Same-origin access only |
| 5. Return auth state | wallet | bridge | {authenticated, walletSecret, expiresAt} | walletSecret enables PPID derivation |
| 6. postMessage response | bridge | site | {authenticated, walletSecret} | Site receives secret for local PPID derivation |

### Ppid Flow

| Step | From | To | Data | Privacy |
|------|------|-----|------|---------|
| 7. Derive PPID | site | crypto_wasm | HMAC(wallet_secret, site_domain) | LOCAL ONLY - no network call |

### Verify Flow

| Step | From | To | Data | Privacy |
|------|------|-----|------|---------|
| 8. Verify credential | site | crypto_wasm | Ed25519 signature check | LOCAL ONLY - no network call |
| 9. Check revocation | site | wallet | Bloom filter lookup | LOCAL ONLY - uses cached bloom filter |

### Revocation Flow

| Step | From | To | Data | Privacy |
|------|------|-----|------|---------|
| 10. Fetch bloom filter | wallet | backend | GET /api/v1/revocation/bloom | Public data, no user identification |
| 11. Read revocation list | backend | postgres | SELECT from revocation_list | Server-side only |
| 12. Return bloom filter | backend | wallet | Bloom filter bytes + metadata | Public data, cached 1 hour |

### Device Link Flow

| Step | From | To | Data | Privacy |
|------|------|-----|------|---------|
| 13. Create transfer session | wallet | backend | Encrypted wallet_secret | Encrypted, only recipient can decrypt |
| 14. Store transfer session | backend | redis | transfer_session:{id} | 5 minute TTL, auto-deleted |
| 15. Poll transfer session | device_b | backend | GET /api/wallet/transfer/{id} | Requires session ID from QR/link |
| 16. Return encrypted wallet | backend | device_b | Encrypted wallet_secret | Decrypted locally on Device B |

### Data Flow

| Step | From | To | Data | Privacy |
|------|------|-----|------|---------|
| Data persistence | backend | postgres | Sites, passkeys, revocations | Server-side storage |

## Data Storage

### User's Browser (IndexedDB)

| Data | Description |
|------|-------------|
| `wallet_secret` | 32-byte hex - NEVER transmitted |
| `passkey` | WebAuthn credential ID + public key |
| `lemmas` | Signed credentials from issuers |
| `revocations` | Bloom filter cache |
| `session` | Auth state (unlocked_at, expires_at) |

### PostgreSQL

| Data | Description |
|------|-------------|
| `passkeys` | credential_id, public_key (can verify, can't sign) |
| `sites` | domain, api_key, signing_key |
| `revocation_list` | revoked credential IDs |

### Redis (Ephemeral)

| Data | Description |
|------|-------------|
| `transfer_session` | Encrypted wallet (5 min TTL) |
| `wallet_session` | Unlock timestamp (24 hour TTL) |

## Privacy Guarantees

| Property | Mechanism | Result |
|----------|-----------|--------|
| **Pairwise Unlinkability** | PPID = HMAC(wallet_secret, site_domain) | Same user has different ID per site |
| **No Central Tracking** | Verification is local (Ed25519 in WASM) | Lemma cannot see which sites user visits |
| **Wallet Secret Protection** | Never leaves IndexedDB, derived from passkey | Only user can derive their PPIDs |
| **Revocation Privacy** | Bloom filter (probabilistic, no queries) | Lemma cannot see revocation checks |