# Lemma Privacy Architecture

> **Verification is Not Data Sale**: A technical design goal with explicit assumptions

## Executive Summary

Lemma provides identity verification services with a privacy-focused architecture intended to reduce data exposure and resale risk. This document explains the technical controls and their assumptions.

---

## Core Privacy Commitments

### 1. Lemma Cannot Observe Verification Events

**How:** Verification happens entirely client-side using Ed25519 signatures.

```
User's Browser                    Relying Party Site
     │                                    │
     │  credential + signature            │
     ├───────────────────────────────────►│
     │                                    │
     │         Ed25519.verify()           │
     │         (local, ~1ms)              │
     │                                    │
     │        valid/invalid               │
     │◄───────────────────────────────────┤
     
     Lemma Server: NOT INVOLVED
```

**Result:** Lemma has no technical ability to know:
- Which sites users authenticate to
- When authentications occur
- How frequently users visit sites
- Whether verification succeeded or failed

### 2. Cross-Site Correlation is Cryptographically Hard by Design

**How:** Pairwise Pseudonymous Identifiers (PPIDs)

```javascript
// User's wallet derives different ID for each site
PPID = HMAC(wallet_master_secret, site_domain)

Site A sees: did:lemma:ppid_7f3a9b2c1d...
Site B sees: did:lemma:ppid_e4c8f6a2b5...
Site C sees: did:lemma:ppid_9d1e7c4a8f...
```

**Result:** 
- Sites are not given a shared global identifier by default
- Lemma's PPID design reduces direct cross-site correlation risk
- No central user database exists

### 3. No PII Stored for Verification

| Data Type | Stored? | Purpose |
|-----------|---------|---------|
| Email addresses | Only if user provides for recovery | Optional account recovery |
| IP addresses | **No** | Not collected |
| User agents | **No** | Not collected |
| Login timestamps | **No** | Not collected |
| Site visit history | **No (intended)** | Local verification reduces observability in standard flows |
| Verification results | **No (intended)** | Standard local-verify flows do not require Lemma-side verification logs |

### 4. Minimal Data for Billing

MAU (Monthly Active Users) tracking uses:
- **Hashed PPIDs** (HMAC-SHA256) - cannot be reversed to identify users
- **Aggregate counts** - "Site X had 1,234 active users" not "User Y visited Site X"

---

## Architecture Guarantees

### What Sites Receive

When a site verifies a Lemma credential, they receive ONLY:

```json
{
  "verified": true,
  "ppid": "did:lemma:ppid_7f3a9b2c1d...",  // Site-specific, unlinkable
  "claims": {
    "isHuman": true,                        // Only what user consented to share
    "verificationLevel": "stripe_identity"
  }
}
```

They do NOT receive:
- Global user identifier
- User's activity on other sites
- When the credential was issued
- How many times it's been used
- Any KYC data (name, DOB, address)

### What Lemma Stores

| Event | Data Stored | Data NOT Stored |
|-------|-------------|-----------------|
| Credential Issuance | Credential ID, site_id, timestamp | User's other credentials |
| Permission Grant | PPID (hashed), permission_type, site_id | IP address, user agent |
| Revocation | Credential ID | Why user was revoked |

### What Lemma Cannot Access

1. **Verification events** - happen client-side
2. **Cross-site user activity** - PPIDs are unlinkable
3. **Real user identities** - only hashed PPIDs stored
4. **KYC source data** - Stripe Identity data not retained

---

## Technical Enforcement

These aren't policy promises - they're architectural constraints:

### Client-Side Verification (Enforced by Code)

```javascript
// From wallet_bridge.html - verification is LOCAL
case 'VERIFY_CREDENTIAL':
    // NO SERVER CALLS
    const verification = await wallet.verifyLemma(credToVerify);
    respond({
        verifiedLocally: true,
        networkCalls: 0  // Guaranteed
    });
```

### PPID Derivation (Enforced by Cryptography)

```python
# From api/ppid.py - PPID derived client-side
def derive_ppid_from_wallet_secret(wallet_secret: str, rp_id: str) -> str:
    # Server never sees wallet_secret - stored only in user's browser
    master = derive_master_secret_from_wallet_secret(wallet_secret)
    ppid = hmac.new(master, rp.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"did:lemma:ppid_{ppid}"
```

### No Tracking Infrastructure (Enforced by Schema)

```python
# From api/database.py - NetworkActivity model
class NetworkActivity(Base):
    """
    PRIVACY COMMITMENT: This table does NOT log verification events.
    - No IP addresses are collected
    - No user agents are collected
    - Only administrative actions (grants/revokes) are logged
    """
    # REMOVED: ip_address
    # REMOVED: user_agent
    # REMOVED: activity_metadata (could leak context)
```

---

## Comparison: Verification Service vs. Data Sale

| Aspect | Selling Data | Lemma Verification |
|--------|--------------|-------------------|
| What buyer receives | User profiles, behaviors | Boolean: verified/not |
| Can buyer resell? | Yes | No (nothing to resell) |
| Creates tracking profile? | Yes | No |
| User loses control? | Yes | No (user holds credentials) |
| Cross-site correlation? | Usually possible | Designed to be strongly reduced (PPID separation) |
| Revenue model | Per-record pricing | Per-verification/issuance |

---

## Audit Checklist

To verify these commitments, auditors can check:

1. **No verification logging**: Search codebase for `NetworkActivity` writes - should only be for grant/revoke operations
2. **No IP collection**: `grep -r "ip_address" api/` - should not appear in verification flows
3. **PPID derivation is client-side**: Check `static/js/lemma-wallet.js` - wallet_secret never sent to server
4. **Verification is local**: Check `templates/wallet_bridge.html` - `VERIFY_CREDENTIAL` case makes no fetch() calls

---

## Regulatory Alignment

### GDPR

| Requirement | How Lemma Complies |
|-------------|-------------------|
| Data minimization | Only hashed PPIDs stored |
| Purpose limitation | No verification event logging |
| Right to erasure | User deletes wallet = credentials gone |
| Data portability | Full wallet export supported |

### CCPA

| Requirement | How Lemma Complies |
|-------------|-------------------|
| Right to know | User can export full wallet |
| Right to delete | User controls credentials locally |
| Right to opt-out of sale | No data sale occurs |

---

## Summary

Lemma is architected to make broad user-data resale and cross-site tracking technically difficult, not merely disallowed by policy:

1. **Verification is local** → Lemma can't observe it
2. **PPIDs are site-specific** → Cross-site correlation is significantly reduced  
3. **No tracking infrastructure** → IP/UA fields removed from schema
4. **Minimal logging** → Only administrative actions, not verifications

This is the difference between a privacy policy and a privacy architecture.
