> **Superseded** by [ISHUMAN Agent Integration Guide](ISHUMAN_AGENT_INTEGRATION.md). This document is retained for historical reference only.

# Lemma Integration Guide

> Complete guide for integrating Lemma's wallet-based user authentication. For agent/runtime auth, use the proof-first developer auth contract and runtime docs instead of this user-login guide.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Authentication Flow](#authentication-flow)
4. [SDK Reference](#sdk-reference)
5. [Backend Integration](#backend-integration)
6. [Advanced Topics](#advanced-topics)
7. [Troubleshooting](#troubleshooting)

---

## Overview

### What Makes Lemma Different

| Feature | Traditional Auth | Lemma |
|---------|------------------|-------|
| Authentication | Passwords | Passkeys (biometric) |
| User tracking | Cross-site possible | Reduced by per-site PPIDs |
| Session management | Server-side | Client-side + global sync |
| Re-authentication | Every device | Once per day, all devices |
| Wallet secret | Often server-managed | Designed to remain client-side in standard flows |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  USER'S DEVICE                                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │
│  │   Passkey   │────▶│   Wallet    │────▶│    PPID     │    │
│  │ (Biometric) │     │ (IndexedDB) │     │ (Per-Site)  │    │
│  └─────────────┘     └─────────────┘     └─────────────┘    │
│                              │                               │
│                      ┌───────▼───────┐                       │
│                      │ Global Session │                      │
│                      │   (Server)     │                       │
│                      └───────────────┘                       │
│                              │                               │
│              ┌───────────────┼───────────────┐               │
│              ▼               ▼               ▼               │
│         Device A        Device B        Device C             │
│         (unlocked)      (synced)        (synced)             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Step 1: Add the SDK

```html
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
```

### Step 2: Initialize and Check Auth

```javascript
const wallet = new LemmaWallet();
await wallet.init();

// Handle redirect return (user coming back from lemma.id)
const redirectResult = await wallet.checkRedirectReturn();
if (redirectResult?.success) {
    const ppid = await wallet.derivePPID();
    await handleAuthenticated(ppid);
    return;
}

// Check if already authenticated
const auth = await wallet.getAuthenticatedPPID();
if (auth.authenticated) {
    await handleAuthenticated(auth.ppid);
} else {
    showSignInButton();
}
```

### Step 3: Handle Sign-In

```javascript
document.getElementById('signin-btn').addEventListener('click', async () => {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    // Redirect to lemma.id for passkey authentication
    wallet.startRedirectFlow();
});
```

### Step 4: Backend Verification

```javascript
// Your backend (recommended pattern)
app.post('/api/auth/verify', async (req, res) => {
    const encoded = (req.header('X-Lemma-Credential') || '').trim();
    if (!encoded) {
        return res.status(401).json({
            error: 'auth_required',
            message: 'Provide X-Lemma-Credential',
            auth_method: 'none',
        });
    }

    const credential = JSON.parse(Buffer.from(encoded, 'base64url').toString('utf8'));
    const verification = await verifyCredentialWithTrust(credential); // issuer + signature + expiry
    if (!verification.valid) {
        return res.status(401).json({
            error: `invalid_lemma:${verification.reason || 'verification_failed'}`,
            message: 'Credential verification failed',
            auth_method: 'lemma_header',
        });
    }

    const claims = credential.claims || credential.credentialSubject || {};
    const ppid = credential.subject || claims.ppid || claims.id;

    let user = await db.users.findOne({ ppid });
    if (!user) user = await db.users.create({ ppid });
    res.json({ success: true, userId: user.id });
});
```

---

## Authentication Flow

### Redirect Flow (Recommended)

The redirect flow is broadly compatible across modern browsers, including mobile Safari in current testing:

```
1. User clicks "Sign in with Lemma"
   │
   ▼
2. wallet.startRedirectFlow()
   │
   ▼
3. Redirect to lemma.id/wallet/unlock
   │
   ▼
4. User authenticates with passkey (biometric)
   │
   ▼
5. Redirect back with encrypted wallet data
   │
   ▼
6. wallet.checkRedirectReturn() decrypts locally
   │
   ▼
7. wallet.derivePPID() returns site-specific ID
   │
   ▼
8. Send signed credential to your backend for verification, then derive PPID from verified claims
```

### Code Example

```javascript
class LemmaAuth {
    constructor() {
        this.wallet = new LemmaWallet();
    }
    
    async init() {
        await this.wallet.init();
        
        // Check for redirect return
        const result = await this.wallet.checkRedirectReturn();
        if (result?.success) {
            return { authenticated: true, isRedirectReturn: true };
        }
        
        // Check existing session
        const auth = await this.wallet.getAuthenticatedPPID();
        return { 
            authenticated: auth.authenticated,
            ppid: auth.ppid 
        };
    }
    
    async signIn() {
        this.wallet.startRedirectFlow();
    }
    
    async getPPID() {
        return await this.wallet.derivePPID();
    }
    
    async signOut() {
        await this.wallet.lock();
    }
}
```

---

## SDK Reference

### Initialization

```javascript
const wallet = new LemmaWallet();
await wallet.init();
```

### Authentication Methods

#### `getAuthenticatedPPID()`

Check if user is authenticated and get their PPID:

```javascript
const auth = await wallet.getAuthenticatedPPID();
// Returns:
// {
//   authenticated: boolean,
//   ppid?: string,           // "did:lemma:ppid_<64-char-hex>"
//   needsPasskey: boolean,   // true if redirect needed
//   message: string
// }
```

#### `startRedirectFlow()`

Redirect to lemma.id for passkey authentication:

```javascript
wallet.startRedirectFlow();
// Redirects to lemma.id/wallet/unlock
// Returns to current page with encrypted data
```

#### `checkRedirectReturn()`

Handle return from lemma.id authentication:

```javascript
const result = await wallet.checkRedirectReturn();
// Returns:
// {
//   success: boolean,
//   walletId?: string,
//   authenticated?: boolean
// }
```

#### `derivePPID(siteId?)`

Derive site-specific pseudonymous identifier:

```javascript
const ppid = await wallet.derivePPID();
// Returns: "did:lemma:ppid_<64-char-hex>"

// Or for a specific site
const ppid = await wallet.derivePPID('example.com');
```

### Session Management

#### `lock()`

Lock wallet on all devices:

```javascript
await wallet.lock();
// Clears local session
// Clears global session (affects all linked devices)
```

#### `getWalletInfo()`

Get current wallet state:

```javascript
const info = await wallet.getWalletInfo();
// Returns:
// {
//   hasWallet: boolean,      // Has wallet secret
//   hasPasskey: boolean,     // Has registered passkey
//   isUnlocked: boolean,     // Currently authenticated
//   walletId: string | null,
//   session: { ... }
// }
```

#### `isUnlocked()`

Quick check if wallet is unlocked:

```javascript
if (wallet.isUnlocked()) {
    // User is authenticated
}
```

### Event Handling

#### Session Expiry

```javascript
wallet.onSessionExpired((event) => {
    console.log('Session expired:', event.reason);
    // 'expired' | 'locked' | 'bridge_invalid'
    redirectToLogin();
});
```

#### Session Heartbeat

The SDK automatically monitors session validity on third-party sites:

```javascript
// Heartbeat runs automatically
// - Checks on tab visibility change (fast)
// - Checks every 5 minutes (backup)
// - Triggers onSessionExpired if wallet locked elsewhere
```

---

## Backend Integration

### Verifying Credentials and Extracting PPIDs

PPIDs are deterministic per site (same user + same site => same PPID), but should be used only after signed credential verification:

```javascript
// Node.js example (recommended)
app.post('/api/auth/verify', async (req, res) => {
    const encoded = (req.header('X-Lemma-Credential') || '').trim();
    if (!encoded) {
        return res.status(401).json({
            error: 'auth_required',
            message: 'Provide X-Lemma-Credential',
            auth_method: 'none',
        });
    }

    const credential = JSON.parse(Buffer.from(encoded, 'base64url').toString('utf8'));
    const verification = await verifyCredentialWithTrust(credential);
    if (!verification.valid) {
        return res.status(401).json({
            error: `invalid_lemma:${verification.reason || 'verification_failed'}`,
            message: 'Credential verification failed',
            auth_method: 'lemma_header',
        });
    }

    const claims = credential.claims || credential.credentialSubject || {};
    const ppid = credential.subject || claims.ppid || claims.id;
    
    // Find or create user
    let user = await User.findOne({ lemma_ppid: ppid });
    
    if (!user) {
        user = await User.create({
            lemma_ppid: ppid,
            created_at: new Date()
        });
    }
    
    // Create session
    const token = jwt.sign({ userId: user.id }, process.env.JWT_SECRET);
    
    res.json({ success: true, token });
});
```

### Runtime auth precedence (server-side)

For protected routes, production runtime evaluates auth in this order:

1. Optional bearer compatibility (`Authorization: Bearer lm_at_...`) when enabled.
2. `X-Agent-Token` delegated token.
3. Agent session (`/api/agent/session`).
4. `X-Lemma-Credential` full signed lemma header.
5. API key fallback (`X-API-Key` / bearer API key).

Legacy `X-Credential-ID`-only compatibility paths are non-production defaults and should not be used for new integrations.

### Database Schema

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    lemma_ppid VARCHAR(128) UNIQUE NOT NULL,
    email VARCHAR(255),          -- Optional, user can add later
    display_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP
);

CREATE INDEX idx_users_ppid ON users(lemma_ppid);
```

---

## Advanced Topics

### Cross-Device Sync

When a user unlocks on one device, other linked devices can skip passkey:

```javascript
// This happens automatically in getAuthenticatedPPID()
const auth = await wallet.getAuthenticatedPPID();

if (auth.authenticated) {
    // User may have unlocked on another device
    // SDK synced from global session automatically
    console.log('Authenticated via:', auth.source);
    // 'local' | 'global_sync' | 'redirect'
}
```

### Device Linking

Users can link devices at `lemma.id/wallet`:

```javascript
// Direct user to wallet management
const linkUrl = 'https://lemma.id/wallet';

// Or use SDK method
const state = await wallet.getAuthState();
if (state.canLinkDevice) {
    // Show "Link another device" option
}
```

### Privacy: PPID Derivation

PPIDs are derived client-side using HMAC:

```
PPID = HMAC-SHA256(wallet_secret, site_domain)
```

- **Same user + same site** = Same PPID (deterministic)
- **Same user + different site** = Different PPID (unlinkable)
- **Wallet secret** is designed to remain on-device in standard flows

### Session Duration

Users can configure session duration (1-24 hours) at `lemma.id/wallet`:

```javascript
// SDK automatically respects user's preference
// Default: 24 hours
// Minimum: 1 hour
// Maximum: 24 hours
```

---

## Troubleshooting

### "Redirect not returning data"

Ensure your site is served over HTTPS:

```javascript
if (location.protocol !== 'https:' && !location.hostname.includes('localhost')) {
    console.warn('Lemma requires HTTPS');
}
```

### "PPID is undefined"

Call `checkRedirectReturn()` first when returning from authentication:

```javascript
// Correct order
const redirect = await wallet.checkRedirectReturn();
if (redirect?.success) {
    const ppid = await wallet.derivePPID(); // Now works
}
```

### "Session expires immediately"

The session might be locked from another device. Check the heartbeat:

```javascript
wallet.onSessionExpired((event) => {
    if (event.reason === 'locked') {
        // Wallet was locked on another device
    }
});
```

### Debug Mode

Enable verbose logging:

```javascript
const wallet = new LemmaWallet();
// Logs prefixed with [Lemma] will appear in console
```

### Testing Without Passkey Hardware

On development machines without biometric hardware:
- Windows: Use PIN or Windows Hello
- Mac: Use Touch ID or password
- Browser: Some browsers offer software passkey simulation

---

## Security Considerations

1. **Use HTTPS everywhere** - Required for passkeys and secure redirects
2. **Validate PPID format** - Check `did:lemma:ppid_` prefix
3. **Don't store wallet secrets** - keep them client-side
4. **Do not trust PPID alone** - require signed credential verification on protected routes

---

## Migration from Other Auth

### From Auth0/Okta

```javascript
// Old: Auth0
// const user = await auth0.getUser();
// const userId = user.sub;

// New: Lemma
const auth = await wallet.getAuthenticatedPPID();
const userId = auth.ppid;  // Use as unique identifier
```

### From Firebase Auth

```javascript
// Old: Firebase
// const user = firebase.auth().currentUser;
// const userId = user.uid;

// New: Lemma  
const auth = await wallet.getAuthenticatedPPID();
const userId = auth.ppid;
```

---

## Support

- Documentation: https://lemma.id/docs
- Issues: https://github.com/lemma-id/sdk/issues
- Email: support@lemma.id
