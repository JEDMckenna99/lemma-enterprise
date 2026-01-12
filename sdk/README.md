# Lemma SDK

> Passkey-protected wallet authentication with microsecond credential verification

[![npm version](https://badge.fury.io/js/%40lemma%2Fverification-sdk.svg)](https://badge.fury.io/js/%40lemma%2Fverification-sdk)
[![TypeScript](https://img.shields.io/badge/TypeScript-Ready-blue.svg)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 **What is Lemma?**

Lemma is a **wallet-first authentication system** where:

- **Passkey (biometric)** unlocks the wallet locally - no server call
- **Credentials** are stored in the user's browser wallet
- **Verification** happens client-side in microseconds
- **Sites cannot track users** across different sites (PPID privacy)

**No passwords. No sessions. No server-side state.**

---

## 🚀 **Quick Start**

### Option 1: Script Tag (Recommended)

```html
<!-- Add to your page -->
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>

<script>
// Initialize wallet
const wallet = new LemmaWallet({ debug: true });
await wallet.init();

// Check if user is authenticated
if (wallet.isAuthenticated()) {
    // User has unlocked wallet today - they're signed in!
    const credential = await wallet.getCredential('permission', 'yoursite.com');
    console.log('Welcome back!', credential.claims.email);
} else {
    // Show sign-in button
    document.getElementById('signin-btn').style.display = 'block';
}
</script>
```

### Option 2: NPM Package

```bash
npm install @lemma/wallet-sdk
```

```javascript
import { LemmaWallet } from '@lemma/wallet-sdk';

const wallet = new LemmaWallet({ debug: true });
await wallet.init();
```

---

## 🔐 **Authentication Flow**

### How Wallet-First Auth Works

```
1. First Visit (New User)
   ├── User clicks "Sign in with Lemma"
   ├── Browser prompts for passkey (Touch ID, Face ID, etc.)
   ├── Passkey registered → Wallet created
   ├── Site issues permission credential → Stored in wallet
   └── User is authenticated ✅

2. Return Visits (Existing User)
   ├── Page loads
   ├── Check: wallet.isAuthenticated()
   ├── If unlocked today → Instant access ✅ (no prompt!)
   ├── If not unlocked → Browser prompts passkey
   └── User is authenticated ✅

3. Different Site (Same User)
   ├── User visits newsite.com
   ├── wallet.unlock() → Same passkey
   ├── newsite.com issues ITS OWN permission
   └── Sites CANNOT correlate users (different PPIDs)
```

---

## 🌉 **Central Wallet Mode (Recommended for Third-Party Sites)**

By default, each site stores credentials in its own browser storage (IndexedDB is same-origin). To have all credentials visible in the user's **central wallet at lemma.id/wallet**, use the central wallet bridge:

### Using the IAM SDK with Central Wallet

```javascript
// Load the IAM SDK
<script src="https://lemma.id/sdk/lemma-iam-sdk.js"></script>

<script>
const lemma = new LemmaIAM({
    apiKey: 'your-api-key',
    siteId: 'yoursite.com',
    useCentralWallet: true,  // ← Store credentials in lemma.id wallet
    debug: true
});

// Sign in - credential stored in central wallet via bridge
const result = await lemma.signIn();
if (result.success) {
    console.log('Signed in!', result.user);
    console.log('View all permissions at: lemma.id/wallet');
}
</script>
```

### How Central Wallet Works

```
Without useCentralWallet (default):
├── yoursite.com issues credential
├── Stored in yoursite.com's IndexedDB
└── NOT visible at lemma.id/wallet ❌

With useCentralWallet: true:
├── yoursite.com issues credential  
├── SDK loads hidden iframe from lemma.id/wallet/bridge
├── Credential sent via postMessage to iframe
├── Stored in lemma.id's IndexedDB
└── Visible at lemma.id/wallet ✅
```

### Storage Mode Info

```javascript
const storageInfo = lemma.getStorageInfo();
console.log(storageInfo);
// { mode: 'central', location: 'lemma.id wallet (via bridge)', viewAt: 'https://lemma.id/wallet' }
```

---

## 📦 **LemmaWallet Class**

The wallet is the core of Lemma authentication.

### Constructor

```javascript
const wallet = new LemmaWallet({
    debug: false,              // Enable console logging
    enableDeviceSync: true,    // Allow multi-device sync
    enableAdvancedFeatures: true
});
```

### Initialization

```javascript
// Always call init() first
await wallet.init();
```

### Core Methods

#### `registerPasskey(): Promise<RegistrationResult>`

Register a new passkey and create the wallet. Call this for first-time users.

```javascript
const result = await wallet.registerPasskey();

// Result:
{
    success: true,
    credentialId: "base64url-credential-id",
    walletId: "wallet_abc123",
    walletSecret: "hex-string-for-ppid-derivation"
}
```

#### `unlock(): Promise<UnlockResult>`

Unlock the wallet using passkey. Browser prompts for biometric verification.

```javascript
const result = await wallet.unlock();

// Result:
{
    success: true,
    walletId: "wallet_abc123",
    walletSecret: "hex-string",
    sessionExpiry: 1704067200000  // Unix timestamp
}
```

#### `isUnlocked(): boolean`

Check if wallet is currently unlocked.

```javascript
if (wallet.isUnlocked()) {
    // Wallet is open - can access credentials
}
```

#### `isAuthenticated(): boolean`

Check if user has unlocked wallet today (primary auth check).

```javascript
if (wallet.isAuthenticated()) {
    // User is "signed in" - unlocked wallet today
    showApp();
} else {
    // Need to unlock or register
    showSignInButton();
}
```

#### `getAuthState(): AuthState`

Get detailed authentication state.

```javascript
const state = wallet.getAuthState();

// Returns:
{
    authenticated: true,
    unlockedToday: true,
    sessionExpiry: 1704067200000,
    hasPasskey: true
}
```

---

## 🎫 **Credential Management**

### Store Credential

```javascript
// Store a permission credential from a site
await wallet.storeCredential(permissionLemma);
```

### Get Credential

```javascript
// Get credential for a specific site
const credential = await wallet.getCredential('permission', 'example.com');

if (credential) {
    console.log('Email:', credential.claims.email);
    console.log('Permission:', credential.claims.permissionId);
}
```

### Get All Credentials

```javascript
const allCredentials = await wallet.getCredentials('permission');
// Returns array of all permission credentials
```

### Check Valid Credential

```javascript
const hasAccess = await wallet.hasValidCredential('example.com', 'permission');
if (hasAccess) {
    // User has valid, non-expired permission for this site
}
```

---

## 🌐 **Site Integration**

### Request Permission from Lemma

When a user doesn't have a credential for your site, request one:

```javascript
async function requestSiteAccess() {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    // Ensure wallet is unlocked
    if (!wallet.isUnlocked()) {
        await wallet.unlock();
    }
    
    // Get wallet identifiers for permission request
    const walletSecret = await wallet.getWalletSecret();
    
    // Request permission from Lemma API
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
        // Store the permission in wallet
        await wallet.storeCredential(result.permission_lemma);
        console.log('Access granted!');
    }
}
```

### Complete Authentication Flow

```javascript
async function authenticateUser() {
    const wallet = new LemmaWallet({ debug: true });
    await wallet.init();
    
    // Step 1: Check if already authenticated
    if (wallet.isAuthenticated()) {
        const credential = await wallet.getCredential('permission', 'yoursite.com');
        if (credential) {
            return { authenticated: true, user: credential.claims };
        }
    }
    
    // Step 2: Check if has passkey (returning user)
    const info = await wallet.getWalletInfo();
    
    if (info.hasPasskey) {
        // Returning user - unlock wallet
        await wallet.unlock();
    } else {
        // New user - register passkey
        await wallet.registerPasskey();
    }
    
    // Step 3: Check for site permission
    let credential = await wallet.getCredential('permission', 'yoursite.com');
    
    if (!credential) {
        // Request permission from Lemma
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
            await wallet.storeCredential(result.permission_lemma);
            credential = result.permission_lemma;
        }
    }
    
    return { 
        authenticated: true, 
        user: credential?.claims || credential?.credentialSubject 
    };
}
```

---

## 🔒 **Privacy: PPID (Pairwise Pseudonymous Identifiers)**

Lemma uses PPIDs to prevent cross-site user tracking.

### How It Works

```
User's wallet_secret: "abc123..."

Site A (example.com):
  PPID = HMAC(wallet_secret, "example.com")
  → did:lemma:ppid_7f8a9b2c...

Site B (another.com):
  PPID = HMAC(wallet_secret, "another.com")  
  → did:lemma:ppid_3d4e5f6a...

Sites CANNOT correlate these identifiers!
Same user appears as different identity to each site.
```

### Privacy Properties

- **Unlinkability**: Sites cannot determine if two PPIDs belong to same user
- **Consistency**: Same user at same site always gets same PPID
- **No Central Tracking**: Lemma server doesn't store user-site mappings

---

## ⚡ **Credential Verification**

Verify credentials locally in microseconds.

### Basic Verification

```javascript
import { LemmaVerifier } from '@lemma/wallet-sdk';

const verifier = new LemmaVerifier();

const result = await verifier.verify(credentialJSON);

console.log('Valid:', result.verified);
console.log('Time:', result.timing.verification + 'µs');
```

### Verification with Revocation Check

```javascript
// Sync revocation list (do this periodically)
await wallet.syncRevocations();

// Verify with revocation check
const credential = await wallet.getCredential('permission', 'example.com');
const isValid = await wallet.verifyCredential(credential);

if (isValid) {
    // Credential is valid AND not revoked
}
```

---

## 🔄 **Offline Support**

Lemma works offline after initial setup.

### Offline Capabilities

- ✅ Wallet unlock (passkey is local)
- ✅ Credential verification (Ed25519 signatures)
- ✅ Revocation check (cached Bloom filter)
- ⚠️ New permission requests (need network)

### Check Online Status

```javascript
if (wallet.isOffline()) {
    console.log('Offline mode - using cached data');
}

// Revocation sync gracefully handles offline
const syncResult = await wallet.syncRevocations();
if (syncResult.offline) {
    console.log('Using cached revocations, age:', syncResult.cacheAge);
}
```

---

## 📱 **Multi-Device Support**

### QR Code Device Sync

Transfer wallet to a new device:

```javascript
// On primary device - generate transfer QR
const session = await wallet.createTransferSession();
showQRCode(session.qr_code);

// On new device - scan and import
const newWallet = new LemmaWallet();
await newWallet.importFromTransfer(scannedData);
```

---

## 🛡️ **Security Model**

### What Lemma Protects Against

| Threat | Protection |
|--------|------------|
| **Password theft** | No passwords - passkey only |
| **Session hijacking** | No sessions - credential in wallet |
| **Cross-site tracking** | PPID unlinkability |
| **Credential replay** | Fresh nonce per verification |
| **Phishing** | Passkey bound to domain |
| **Credential forgery** | Ed25519 signatures (2^128 security) |

### What Users Control

- Their wallet (stored in THEIR browser)
- Which devices have wallets
- When to revoke (delete wallet data)

### What Sites Control

- Permission issuance for their domain
- Permission revocation (<100ms propagation)
- Custom claims in credentials

---

## 📊 **Performance**

| Operation | Time |
|-----------|------|
| Passkey unlock | ~300ms (biometric prompt) |
| Credential verification | 32.8µs |
| Revocation check | <1µs |
| Offline verification | ~35µs total |

---

## 🎯 **API Reference**

### Wallet API Endpoints

#### `POST /api/wallet-auth/issue`

Issue permission credential to wallet.

```javascript
// Request
{
    "site_id": "example.com",
    "wallet_secret": "hex-string",
    "passkey_credential_id": "base64url" // fallback
}

// Response
{
    "success": true,
    "ppid": "did:lemma:ppid_abc123...",
    "site_id": "example.com",
    "permission_lemma": { /* signed credential */ }
}
```

#### `POST /api/wallet-auth/verify-session`

Verify wallet session and permissions.

```javascript
// Request
{
    "site_id": "example.com",
    "wallet_secret": "hex-string",
    "permissions": ["example.com:read", "example.com:write"]
}

// Response
{
    "success": true,
    "authenticated": true,
    "ppid": "did:lemma:ppid_abc123...",
    "has_permission": true
}
```

### Server-Side API (Backend Integration)

#### `POST /api/v1/iam/invite`

**Privacy-Preserving Email Invitation** - Invite users to your site via email. Email is used ONLY for delivery and is **never stored**.

```bash
# cURL example
curl -X POST https://lemma.id/api/v1/iam/invite \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "permission": "admin",
    "redirect_url": "https://yoursite.com/welcome"
  }'
```

```javascript
// Node.js example
const response = await fetch('https://lemma.id/api/v1/iam/invite', {
    method: 'POST',
    headers: {
        'X-API-Key': process.env.LEMMA_API_KEY,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        email: 'user@example.com',
        permission: 'admin',           // user, editor, admin, super_admin
        redirect_url: 'https://yoursite.com/welcome',  // Optional
        expiry_days: 90,               // Optional - credential validity
        claim_window_days: 7           // Optional - link validity
    })
});

const result = await response.json();
// { success: true, message: "Invitation sent...", privacy_mode: true }
```

```python
# Python example
import requests

response = requests.post(
    'https://lemma.id/api/v1/iam/invite',
    headers={
        'X-API-Key': os.environ['LEMMA_API_KEY'],
        'Content-Type': 'application/json'
    },
    json={
        'email': 'user@example.com',
        'permission': 'admin'
    }
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `email` | string | Yes | Recipient email (delivery only - never stored) |
| `permission` | string | No | Permission level: `user`, `editor`, `admin`, `super_admin` (default: `user`) |
| `redirect_url` | string | No | URL to redirect after claiming |
| `expiry_days` | number | No | Credential validity in days (default: 90) |
| `claim_window_days` | number | No | Link validity in days (default: 7) |

**Privacy Guarantees:**
- ✅ Email address is NEVER stored in database, Redis, or credential claims
- ✅ User must authenticate with passkey to claim permission
- ✅ User DID is derived from passkey (not email)
- ✅ Database stores `[privacy-protected]` instead of email

---

## 🐛 **Troubleshooting**

### Passkey Registration Failed

```javascript
// Check WebAuthn support
if (!window.PublicKeyCredential) {
    console.log('WebAuthn not supported');
}

// Ensure HTTPS (required for WebAuthn)
if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
    console.log('HTTPS required for passkeys');
}
```

### Wallet Not Persisting

```javascript
// Check IndexedDB availability
if (!window.indexedDB) {
    console.log('IndexedDB not available');
}

// Check if private browsing (some browsers block storage)
```

### Credential Verification Fails

```javascript
// Enable debug mode
const wallet = new LemmaWallet({ debug: true });

// Check credential structure
const credential = await wallet.getCredential('permission', 'site.com');
console.log('Credential:', JSON.stringify(credential, null, 2));

// Verify issuer is trusted
const issuers = await wallet.getIssuers();
console.log('Trusted issuers:', issuers);
```

---

## 🌍 **Browser Support**

| Browser | Version | Passkey Support |
|---------|---------|-----------------|
| Chrome | 80+ | ✅ Full |
| Firefox | 75+ | ✅ Full |
| Safari | 14+ | ✅ Full |
| Edge | 80+ | ✅ Full |

**Note**: WebAuthn (passkeys) requires HTTPS except on localhost.

---

## 📖 **Additional Resources**

- [Architecture: Wallet-First](https://lemma.id/docs/architecture)
- [IAM API Reference](https://lemma.id/docs/api)
- [Live Demo](https://lemma.id)
- [Whitepaper](https://lemma.id/docs/whitepaper)

---

## 💬 **Support**

- **Documentation**: https://lemma.id/docs
- **Email**: support@lemma.id
- **GitHub Issues**: https://github.com/lemma-id/sdk/issues

---

**Made with ❤️ by the Lemma team**
