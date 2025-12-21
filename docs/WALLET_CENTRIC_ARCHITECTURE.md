# Wallet-Centric Architecture Plan

**Status:** Complete  
**Date:** 2025-12-21  
**Version:** v2 (Passkey-Rooted)

## Overview

A wallet-centric model where:
- **Passkey is the root of trust** (free, no PoH required to start)
- Sites can issue their own lemmas to the user's wallet (free)
- PoH is **optional** - only needed for anti-bot protection
- Lemma provides issuer registry and revocation network

## Key Insight: PoH is Optional

| Layer | What It Proves | Cost | Required? |
|-------|----------------|------|-----------|
| **Passkey** | "This is my device" | Free | Yes (wallet root) |
| **Site Lemmas** | "User has role X" | Free | Site-specific |
| **PoH Lemma** | "This is a real human" | ~$1.50 | Only if site requires |

**The wallet works without PoH.** Users create a wallet with passkey → Sites issue lemmas → Done.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WALLET-CENTRIC ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   USER DEVICE   │
                              │                 │
                              │  ┌───────────┐  │
                              │  │  Passkey  │  │ ← Stored in secure enclave
                              │  │ (private) │  │
                              │  └─────┬─────┘  │
                              │        │        │
                              │        ▼        │
                              │  ┌───────────┐  │
                              │  │  WALLET   │  │ ← Browser-based, encrypted
                              │  │           │  │
                              │  │ • Session │  │ ← Unlock state
                              │  │ • Lemmas  │  │ ← From various issuers
                              │  │ • Issuers │  │ ← Cached public keys
                              │  └─────┬─────┘  │
                              │        │        │
                              └────────┼────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
          ▼                            ▼                            ▼
    ┌───────────┐                ┌───────────┐                ┌───────────┐
    │  SITE A   │                │  SITE B   │                │   LEMMA   │
    │           │                │           │                │  SERVICE  │
    │ Issues    │                │ Verifies  │                │           │
    │ own       │                │ any       │                │ • PoH     │
    │ lemmas    │                │ lemma     │                │ • Registry│
    │           │                │ locally   │                │ • Revoke  │
    └───────────┘                └───────────┘                └───────────┘
```

---

## Components

### 1. Local Wallet (Browser)

**Location:** `static/js/lemma-wallet.js`

**Responsibilities:**
- Store passkey public key for local verification
- Manage unlock session (time-limited)
- Store lemmas from any issuer
- Cache issuer public keys
- Present lemmas to requesting sites

**Storage:** IndexedDB (encrypted with passkey-derived key)

### 2. Passkey Unlock Flow (100% Local)

```
User clicks "Unlock"
       │
       ▼
Wallet generates random challenge
       │
       ▼
Browser prompts biometric (passkey)
       │
       ▼
Secure enclave signs challenge
       │
       ▼
Wallet verifies signature using stored public key
       │
       ▼
Wallet session marked as "unlocked" for 8 hours
```

**No server call required.**

### 3. Site Issuer SDK

**Location:** `static/js/lemma-issuer.js`

**Enables sites to:**
- Generate their own signing keypair
- Issue lemmas to users' wallets
- Register public key with Lemma registry

### 4. Lemma Services (Server)

**Lemma's role in the federated network:**

| Service | Purpose | When Used |
|---------|---------|-----------|
| **PoH Issuance** | Issue "isHuman=true" lemmas | User's first verification |
| **Issuer Registry** | Store/lookup site public keys | Sites registering, cross-site trust |
| **Revocation Network** | Aggregate and distribute revocations | Bad actor detected |

---

## Federated Model: Who Issues What

The federated model separates **identity verification** from **permissions/roles**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FEDERATED ISSUER MODEL                              │
└─────────────────────────────────────────────────────────────────────────────┘

                    LEMMA (Root of Trust)
                    ┌─────────────────────┐
                    │                     │
                    │  Issues:            │
                    │  • isHuman=true     │  ← "I'm a real person"
                    │  • passkey verified │  ← "Device is mine"
                    │  • KYC level        │  ← "Identity verified"
                    │                     │
                    └──────────┬──────────┘
                               │
                    User stores in wallet
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐        ┌───────────┐        ┌───────────┐
    │  SITE A   │        │  SITE B   │        │  SITE C   │
    │           │        │           │        │           │
    │ Issues:   │        │ Issues:   │        │ Issues:   │
    │ • role    │        │ • member  │        │ • access  │
    │ • admin   │        │ • premium │        │ • api_key │
    └───────────┘        └───────────┘        └───────────┘
```

### Why This Separation Matters

| Lemma Issues | Sites Issue |
|--------------|-------------|
| **Human verification** - expensive, one-time | **Roles/permissions** - free, frequent changes |
| **Device binding** - passkey proof | **Membership tiers** - site-specific |
| **KYC level** - regulatory compliance | **Access tokens** - resource-specific |
| **Universal across all sites** | **Only valid for issuing site** |

### Integration with Existing IAM

The existing `issuer_management.py` and KMS-backed issuers **remain unchanged**:

1. **Lemma Server Issues:**
   - PoH credentials (via `PyMinimalIssuer`)
   - IAM permissions (via `get_iam_issuer()`)
   - All KMS-backed for security compliance

2. **Sites Issue (NEW):**
   - Role/membership lemmas (via `LemmaSiteIssuer`)
   - Browser-based Ed25519 signing
   - Registered in `issuer_registry`

3. **Wallet Stores Both:**
   - Lemma's PoH credential (trust anchor)
   - Site-specific credentials (permissions)
   - All verifiable locally

---

## Implementation Plan

### Phase 1: Wallet Core (Tasks 2, 3, 7)
- [ ] Create `LemmaWallet` class with IndexedDB storage
- [ ] Implement local passkey unlock (no server)
- [ ] Add session management (unlock state, expiry)
- [ ] Encrypt wallet data with passkey-derived key

### Phase 2: Site Issuer (Tasks 4, 5)
- [ ] Create `LemmaSiteIssuer` class
- [ ] Generate/store site signing keypairs
- [ ] Issue lemmas with site signature
- [ ] Register site with Lemma's issuer registry

### Phase 3: Presentation & Verification (Task 8)
- [ ] Wallet presents lemmas on request
- [ ] Sites verify lemmas locally
- [ ] Cross-site credential sharing

### Phase 4: Integration & Cleanup (Tasks 6, 9)
- [ ] Update existing passkey endpoints
- [ ] Test all flows
- [ ] Deploy

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `static/js/lemma-wallet.js` | CREATE | Core wallet with local passkey unlock |
| `static/js/lemma-issuer.js` | CREATE | Site issuer SDK |
| `static/js/lemma-passkey.js` | UPDATE | Simplify to just registration helper |
| `api/issuer_registry.py` | CREATE | Issuer public key registry |
| `api/passkey_auth.py` | UPDATE | Support local-first model |

---

## Data Models

### Wallet Storage (IndexedDB)

```javascript
{
  // Passkey for local unlock
  passkey: {
    credentialId: "base64...",
    publicKey: "base64...",
    algorithm: "ES256",
    createdAt: 1734820000000
  },
  
  // Session state
  session: {
    isUnlocked: true,
    unlockedAt: 1734820000000,
    expiresAt: 1734848800000  // +8 hours
  },
  
  // Stored credentials from various issuers
  lemmas: [
    {
      id: "lemma_abc123",
      issuer: "did:web:lemma.id",
      subject: "did:lemma:ppid_xyz",
      claims: { isHuman: true },
      issuedAt: 1734820000000,
      expiresAt: 1737498800000,
      signature: "base64..."
    },
    {
      id: "lemma_def456",
      issuer: "did:web:mysite.com",
      subject: "did:lemma:ppid_abc",
      claims: { role: "member", plan: "premium" },
      issuedAt: 1734820000000,
      expiresAt: 1737498800000,
      signature: "base64..."
    }
  ],
  
  // Cached issuer public keys
  issuers: {
    "did:web:lemma.id": {
      publicKey: "base64...",
      name: "Lemma",
      verified: true
    },
    "did:web:mysite.com": {
      publicKey: "base64...",
      name: "My Site",
      verified: false
    }
  }
}
```

### Issuer Registry (Server DB)

```sql
CREATE TABLE issuer_registry (
  issuer_did VARCHAR(255) PRIMARY KEY,
  domain VARCHAR(255) NOT NULL,
  public_key TEXT NOT NULL,
  name VARCHAR(255),
  verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW(),
  revoked_at TIMESTAMP
);
```

---

## API Endpoints

### New Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/issuers/register` | POST | Site registers their public key |
| `/api/issuers/{did}` | GET | Get issuer's public key |
| `/api/issuers/verify` | POST | Verify issuer owns domain |
| `/api/issuers/list` | GET | List trusted issuers |

### Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `/api/passkey/register/*` | Now stores public key in wallet too |
| `/api/passkey/authenticate/*` | Optional - for PoH issuance only |

---

## Security Considerations

1. **Wallet Encryption:** Data encrypted with passkey-derived key
2. **Session Timeout:** 8-hour unlock window, then requires re-auth
3. **Issuer Verification:** Domain ownership proof before "verified" badge
4. **Revocation Propagation:** Real-time via Redis pub/sub
5. **Cross-Origin:** Strict CORS for wallet interactions

---

## Progress Tracking

- [x] Architecture plan created
- [x] Phase 1: Wallet Core (`lemma-wallet.js`)
  - [x] IndexedDB storage for lemmas, issuers, session
  - [x] Local passkey unlock (no server call)
  - [x] Session management (8-hour expiry)
- [x] Phase 2: Site Issuer (`lemma-issuer.js`)
  - [x] Ed25519 keypair generation
  - [x] Lemma signing and issuance
  - [x] Pairwise ID generation
- [x] Phase 3: Presentation & Verification
  - [x] Wallet presents lemmas to sites
  - [x] Local signature verification
  - [x] Cross-site credential sharing
- [x] Phase 4: Integration & Cleanup
  - [x] Issuer registry API (`issuer_registry.py`)
  - [x] Passkey endpoints return public key for local storage
  - [ ] Deploy and test

---

## Files Created/Modified

| File | Status | Description |
|------|--------|-------------|
| `static/js/lemma-wallet.js` | ✅ Created | Local wallet with passkey unlock |
| `static/js/lemma-issuer.js` | ✅ Created | Site issuer SDK |
| `api/issuer_registry.py` | ✅ Created | Issuer registry API |
| `api/passkey_auth.py` | ✅ Modified | Returns public key for local storage |
| `app.py` | ✅ Modified | Registered issuer registry blueprint |

---

## Next Steps

1. Deploy changes to Heroku
2. Test wallet unlock flow in browser
3. Test site issuer flow
4. Update documentation
