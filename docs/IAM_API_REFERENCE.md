# Lemma IAM API Reference

Complete API reference for Lemma Identity & Access Management.

**Wallet-first authentication**: Passkey unlocks wallet → Site issues permission → User stays signed in.

---

## 🌐 Base URL

```
Production: https://lemma.id
```

---

## 🔐 **Two Authentication Methods**

| Method | Use Case | Server Calls |
|--------|----------|--------------|
| **Wallet-First** (Primary) | User login, browser apps | One-time permission issue |
| **Email Confirmation** (Legacy) | Server-side, no passkey support | Email round-trip |

---

## 🔑 **Wallet-First Authentication** (Recommended)

### How It Works

```
1. User unlocks wallet with passkey (local, no server)
2. Site requests permission from Lemma
3. Lemma issues credential to user's wallet
4. User presents credential to site (local verification)
5. User stays signed in until credential expires/revoked
```

### Privacy: PPID (Pairwise Pseudonymous Identifier)

Each site gets a **different identifier** for the same user:

```
User at example.com → did:lemma:ppid_abc123...
User at another.com → did:lemma:ppid_def456...

Sites CANNOT correlate these - user privacy preserved!
```

---

## 📋 **Wallet-Auth Endpoints**

### 1. Issue Permission to Wallet

Issue a permission credential directly to an unlocked wallet.

**Endpoint:** `POST /api/wallet-auth/issue`

**Headers:**
```http
Content-Type: application/json
```

**Request Body:**
```json
{
    "site_id": "example.com",
    "wallet_secret": "64-char-hex-string",
    "passkey_credential_id": "base64url-credential-id"
}
```

**Parameters:**
- `site_id` (required): Your site domain/identifier
- `wallet_secret` (preferred): Wallet's master secret for PPID derivation
- `passkey_credential_id` (fallback): Passkey credential ID if wallet_secret unavailable

**Note:** Provide either `wallet_secret` OR `passkey_credential_id`. The `wallet_secret` is preferred as it's derived client-side.

**Response:**
```json
{
    "success": true,
    "ppid": "did:lemma:ppid_7f8a9b2c3d4e5f6a...",
    "site_id": "example.com",
    "is_new_user": true,
    "permission_lemma": {
        "id": "perm_abc123...",
        "issuer": "did:lemma:77f58c892d20c386...",
        "subject": "did:lemma:ppid_7f8a9b2c3d4e5f6a...",
        "issuanceDate": 1704067200000,
        "expirationDate": 1706659200000,
        "credentialSubject": {
            "type": "permission",
            "siteId": "example.com",
            "permissions": "read,write,access",
            "issuedAt": "2025-01-01T00:00:00.000Z",
            "expiresAt": "2025-01-31T00:00:00.000Z"
        },
        "proof": {
            "type": "Ed25519Signature2020",
            "verificationMethod": "did:lemma:77f58c892d20c386...",
            "signatureValue": "128-char-hex-signature"
        },
        "packageType": "permission",
        "issuerInfo": {
            "did": "did:lemma:77f58c892d20c386...",
            "publicKey": "77f58c892d20c386...",
            "name": "example.com IAM",
            "verified": true
        }
    },
    "message": "Permission lemma issued. Store in wallet."
}
```

**Client-Side Usage:**
```javascript
// After wallet unlock
const walletSecret = await wallet.getWalletSecret();

const response = await fetch('https://lemma.id/api/wallet-auth/issue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        site_id: 'yoursite.com',
        wallet_secret: walletSecret
    })
});

const result = await response.json();
if (result.success) {
    // Store credential in wallet
    await wallet.storeCredential(result.permission_lemma);
}
```

---

### 2. Register and Issue (Combined)

Register a new passkey and issue permission in one step.

**Endpoint:** `POST /api/wallet-auth/register-and-issue`

**Headers:**
```http
Content-Type: application/json
```

**Request Body:**
```json
{
    "site_id": "example.com",
    "wallet_secret": "64-char-hex-string",
    "passkey_credential_id": "base64url-credential-id"
}
```

**Response:**
```json
{
    "success": true,
    "ppid": "did:lemma:ppid_7f8a9b2c...",
    "site_id": "example.com",
    "is_new_user": true,
    "permission_lemma": { /* signed credential */ },
    "message": "Wallet registered and permission issued!"
}
```

---

### 3. Verify Wallet Session

Verify wallet unlock status and check permissions.

**Endpoint:** `POST /api/wallet-auth/verify-session`

**Headers:**
```http
Content-Type: application/json
```

**Request Body:**
```json
{
    "site_id": "example.com",
    "wallet_secret": "64-char-hex-string",
    "passkey_credential_id": "base64url-credential-id",
    "permissions": ["example.com:read", "example.com:write"]
}
```

**Response:**
```json
{
    "success": true,
    "authenticated": true,
    "ppid": "did:lemma:ppid_7f8a9b2c...",
    "site_id": "example.com",
    "has_permission": true,
    "needs_permission": false
}
```

---

## 📧 **Email-Based Authentication** (Legacy)

For environments without passkey support or server-side flows.

### 1. Request Access via Email

**Endpoint:** `POST /api/v1/iam/request-access`

**Headers:**
```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
    "site_id": "your_site_id",
    "site_domain": "yoursite.com",
    "user_email": "user@example.com",
    "permission_level": "user",
    "redirect_url": "https://yoursite.com/dashboard"
}
```

**Parameters:**
- `site_id` (required): Your site identifier
- `site_domain` (required): Your domain name
- `user_email` (required): User's email address
- `permission_level` (optional): `user`, `admin`, `editor`, `viewer` (default: `user`)
- `redirect_url` (optional): Where to redirect after confirmation

**Response:**
```json
{
    "success": true,
    "message": "Confirmation email sent to user@example.com",
    "token": "conf_abc123...",
    "expires_in": 86400
}
```

---

### 2. Admin Self-Issue

Bootstrap admin credential using API key (for site owner).

**Endpoint:** `POST /api/v1/iam/admin/self-issue`

**Headers:**
```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
    "site_id": "your_site_id",
    "site_domain": "yoursite.com",
    "user_email": "admin@yoursite.com",
    "permission_level": "super_admin"
}
```

**Response:**
```json
{
    "success": true,
    "credential": { /* Signed Ed25519 credential */ },
    "user_did": "did:lemma:user_abc123...",
    "issuer_did": "did:lemma:issuer_xyz...",
    "issue_time_us": 148.23
}
```

---

## 🔍 **Credential Verification**

### Verify Credential (Server-Side)

Verify a credential with fresh nonce for bot defense.

**Endpoint:** `POST /api/sdk/verify-permission-lemma`

**Headers:**
```http
Content-Type: application/json
```

**Request Body:**
```json
{
    "credential": { 
        "id": "cred_abc123",
        "issuer": "did:lemma:...",
        "subject": "did:lemma:ppid_...",
        "claims": { /* credential claims */ },
        "proof": { /* Ed25519 signature */ }
    },
    "nonce": "32-byte-hex-string",
    "site_domain": "yoursite.com",
    "timestamp": 1700000000000
}
```

**Response (Success):**
```json
{
    "success": true,
    "verified": true,
    "claims": {
        "email": "user@example.com",
        "permissionId": "admin",
        "siteDomain": "yoursite.com"
    },
    "verification_time_us": 182.5
}
```

**Response (Failure - Nonce Reused):**
```json
{
    "success": false,
    "verified": false,
    "error": "Nonce already used (possible replay attack)",
    "security_alert": true
}
```

---

## 👥 **User Management**

### List Users

Get all users with permissions for your site.

**Endpoint:** `GET /api/platform/users`

**Query Parameters:**
- `site_id` (optional): Filter by site ID

**Response:**
```json
{
    "users": [
        {
            "email": "user@example.com",
            "ppid": "did:lemma:ppid_abc123...",
            "permission": "admin",
            "granted_at": "2025-01-01T10:00:00Z",
            "expires_at": "2025-04-01T10:00:00Z",
            "status": "active"
        }
    ],
    "total": 1
}
```

### Revoke Permission

Revoke user's credential (propagates in <100ms).

**Endpoint:** `POST /api/platform/revoke-permission`

**Headers:**
```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
    "email": "user@example.com",
    "site_id": "your_site_id",
    "reason": "access_violation"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Permission revoked for user@example.com",
    "propagation_time_ms": 87,
    "affected_credentials": 1
}
```

---

## 🔄 **Revocation System**

### Get Revocation List (Bloom Filter)

Download Bloom filter for client-side revocation checking.

**Endpoint:** `GET /api/revocation/bloom-filter`

**Response:**
```json
{
    "success": true,
    "filter_type": "global_sha256",
    "count": 15,
    "filter_bytes": "base64-encoded-bloom-filter",
    "filter_size_bytes": 2048,
    "last_updated": "2025-01-01T10:30:00Z"
}
```

**Features:**
- ✅ Privacy-preserving (SHA-256 hashed credential IDs)
- ✅ Cached 7 days client-side
- ✅ Enables offline revocation checking
- ✅ <1µs lookup time

---

## ⚡ **Performance**

| Operation | Time |
|-----------|------|
| Client-side signature check | 18µs |
| Revocation check (Bloom filter) | <1µs |
| PPID derivation | <1ms |
| Permission issuance | ~50ms |
| **Total wallet-auth flow** | **~100ms** |

---

## ❌ **Error Codes**

| Code | Meaning | Action |
|------|---------|--------|
| `validation_error` | Invalid site_id or parameters | Check input format |
| `no_wallet_identifier` | Missing wallet_secret and passkey_credential_id | Provide at least one |
| `nonce_reused` | Nonce already used | Possible replay attack |
| `timestamp_old` | Timestamp >5 min old | Request too old |
| `domain_mismatch` | Wrong domain | Credential for different site |
| `signature_invalid` | Bad signature | Credential tampered |
| `credential_revoked` | Admin revoked | User access removed |
| `credential_expired` | Past expiration | Need new credential |

---

## 🔐 **Security Model**

### Session-Free Architecture

```
Traditional:
  Server session DB: { session_abc: { user: 'alice', ip: '1.2.3.4' } }
  Server KNOWS who's logged in

Lemma:
  Server state: {}  // Empty!
  Credentials stored in USER'S wallet
  Server has NO IDEA who's "logged in"
```

### What Lemma Prevents

- ✅ **Credential forgery** - Ed25519 signatures (2^128 security)
- ✅ **Replay attacks** - Fresh nonce required
- ✅ **Session hijacking** - No sessions exist
- ✅ **Cross-site tracking** - PPID unlinkability
- ✅ **Phishing** - Passkey domain-bound

---

## 🎯 **Integration Patterns**

### Pattern 1: Pure Wallet-First (Recommended)

```javascript
// Client-side only - no server session needed
const wallet = new LemmaWallet();
await wallet.init();

if (wallet.isAuthenticated()) {
    const cred = await wallet.getCredential('permission', 'yoursite.com');
    if (cred) {
        showApp(cred.claims);
    }
}
```

### Pattern 2: Wallet + Server Verification

```javascript
// Client gets credential
const credential = await wallet.getCredential('permission', 'yoursite.com');

// Server verifies with nonce
const nonce = crypto.getRandomValues(new Uint8Array(32));
const response = await fetch('/api/verify', {
    method: 'POST',
    body: JSON.stringify({ credential, nonce: Array.from(nonce) })
});
```

### Pattern 3: Email Fallback

```javascript
// Try wallet first
const wallet = new LemmaWallet();
await wallet.init();

if (!wallet.isUnlocked()) {
    // Passkey not available - fall back to email
    await requestEmailAccess(userEmail);
}
```

---

## 📖 **Additional Resources**

- [SDK Documentation](../sdk/README.md) - Client SDK reference
- [Quick Start](./QUICK_START_SIMPLE_LOGIN.md) - 5-minute integration
- [Architecture](./ARCHITECTURE_WALLET_FIRST.md) - Wallet-first design
- [Whitepaper](./WHITEPAPER_DIGITAL_LEMMAS.md) - Technical foundation

---

## 🆘 **Support**

- **Documentation**: https://lemma.id/docs
- **Email**: support@lemma.id
- **Status**: https://status.lemma.id
