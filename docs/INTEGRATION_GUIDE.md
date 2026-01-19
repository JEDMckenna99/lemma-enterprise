# Lemma Integration Guide

> Complete guide for integrating Lemma's local-first authentication into your application

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Authentication Patterns](#authentication-patterns)
4. [Session Management](#session-management)
5. [Credential Verification](#credential-verification)
6. [React Integration](#react-integration)
7. [Advanced Topics](#advanced-topics)
8. [Troubleshooting](#troubleshooting)

---

## Overview

### What Makes Lemma Different

| Feature | Traditional Auth (Auth0/Okta) | Lemma |
|---------|------------------------------|-------|
| Network calls per login | 5-7 calls | **0 calls** |
| Server dependency | Required | **Works offline** |
| User tracking | Possible | **Impossible (PPIDs)** |
| Verification speed | 200-500ms | **~1ms** |
| Session storage | Server-side | **Client-side (IndexedDB)** |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  USER'S BROWSER                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │
│  │   Passkey   │────▶│   Wallet    │────▶│ Credentials │    │
│  │ (Biometric) │     │ (IndexedDB) │     │  (Lemmas)   │    │
│  └─────────────┘     └─────────────┘     └─────────────┘    │
│         │                   │                   │            │
│         └──────────┬────────┴───────────┬──────┘            │
│                    │                    │                    │
│              ┌─────▼─────┐        ┌─────▼─────┐             │
│              │  Bridge   │        │  Local    │             │
│              │ (iframe)  │        │  Verify   │             │
│              └───────────┘        └───────────┘             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start (Golden Path)

### Step 1: Add the SDK

```html
<!-- Recommended: Script tag -->
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
```

Or via NPM:

```bash
npm install @lemma/wallet-sdk
```

### Step 2: Initialize Wallet

```javascript
// The wallet auto-initializes, but you can wait for it
await lemmaWallet.init();

// Check wallet status
const info = await lemmaWallet.getWalletInfo();
console.log('Has passkey:', info.hasPasskey);
console.log('Is unlocked:', info.isUnlocked);
```

### Step 3: Login + IAM (One Passkey Per Day)

```javascript
async function loginAndGetPermission() {
    await lemmaWallet.init();

    const info = await lemmaWallet.getWalletInfo();
    if (info.hasPasskey) {
        await lemmaWallet.unlock();       // Returning user
    } else {
        await lemmaWallet.registerPasskey(); // New user
    }

    // Fetch or issue a permission lemma for your site
    const credentials = await lemmaWallet.getCredentials('permission');
    const myCredential = credentials.find(c => c.claims?.siteId === 'mysite.com');
    if (!myCredential) {
        throw new Error('No permission lemma for this site yet');
    }

    return myCredential;
}
```

### Step 4: Cross-Site Session Sync (for third-party origins)

If your app runs on a different origin than `lemma.id`, use the session sync flow:

```javascript
// 1) Redirect user to unlock wallet (once per day)
const unlockUrl = `https://lemma.id/wallet/unlock?return_url=${encodeURIComponent(window.location.href)}`;
window.location.href = unlockUrl;

// 2) After redirect back, call session-sync with CSRF header
const csrfToken = getCookie('lemma_wallet_csrf');

const response = await fetch('https://lemma.id/api/wallet/session-sync', {
    method: 'POST',
    credentials: 'include',
    headers: {
        'Content-Type': 'application/json',
        'X-Lemma-CSRF': csrfToken
    }
});

const data = await response.json();
if (data.success) {
    // data.session + data.credentials
    console.log('Session valid until:', new Date(data.session.expires_at * 1000));
}

function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
}
```

**Server configuration required for cross-site session sync:**
- `LEMMA_ALLOWED_ORIGINS` (comma-separated origins)
- `LEMMA_ALLOWED_ORIGIN_SUFFIXES` (comma-separated domain suffixes)
- `LEMMA_ALLOW_DEV_ORIGINS=1` (optional for localhost)
- `SESSION_SECRET` must be set in production

---

## Minimal Integration Checklist (Login + IAM)

- Load `lemma-wallet.js` or install the SDK
- Call `lemmaWallet.init()` on page load
- Use `lemmaWallet.unlock()` (returning) or `lemmaWallet.registerPasskey()` (new)
- Retrieve the permission lemma for your site
- Verify locally with `lemmaWallet.verifyLemma(...)`

---

## Authentication Patterns

### Pattern 1: Check-and-Prompt

Best for: Apps where auth is required on page load

```javascript
document.addEventListener('DOMContentLoaded', async () => {
    await lemmaWallet.init();
    
    const state = lemmaWallet.getAuthState();
    
    if (state.authenticated) {
        // Already authenticated - show app
        showApp();
    } else if (state.state === 'locked') {
        // Has wallet but locked - show unlock prompt
        showUnlockButton();
    } else {
        // No wallet - show registration
        showRegisterButton();
    }
});
```

### Pattern 2: On-Demand Auth

Best for: Apps where auth is optional until a protected action

```javascript
async function purchaseItem(itemId) {
    // Require auth for purchase
    if (!lemmaWallet.isAuthenticated()) {
        await lemmaWallet.unlock();
    }
    
    // Get credential for this site
    const credentials = await lemmaWallet.getCredentials('permission');
    const myCredential = credentials.find(c => c.claims.site === 'mysite.com');
    
    if (!myCredential) {
        // User needs to be issued a credential first
        throw new Error('No permission for this site');
    }
    
    // Proceed with purchase
    await completePurchase(itemId, myCredential);
}
```

### Pattern 3: Session-Aware Auth

Best for: Apps that want to minimize passkey prompts

```javascript
async function smartAuth() {
    const state = await lemmaWallet.getSessionState();
    
    if (state.authenticated && state.timeRemaining > 3600000) {
        // Session valid with >1 hour remaining
        return true;
    }
    
    if (state.shouldPromptExtend && state.canExtend) {
        // Session expiring but can extend with tap
        const extended = await lemmaWallet.extendBridgeSession();
        return extended.success;
    }
    
    // Need full unlock
    await lemmaWallet.unlock();
    return true;
}
```

---

## Session Management

### Understanding Sessions

Lemma uses a **session-based unlock model**:

- **Default session**: 24 hours
- **Extensions**: Up to 7 extensions (tap-only, no biometric)
- **Total**: Up to 8 days without full re-authentication

### Checking Session State

```javascript
const state = await lemmaWallet.getSessionState();

console.log({
    authenticated: state.authenticated,      // Is user authenticated?
    timeRemaining: state.timeRemaining,      // ms until expiry
    canExtend: state.canExtend,              // Can extend session?
    extensionCount: state.extensionCount,    // Extensions used (0-7)
    shouldPromptExtend: state.shouldPromptExtend  // <2 hours remaining
});
```

### Automatic Session Management

```javascript
// Start automatic session management
const manager = startLemmaSessionManager({
    checkInterval: 30 * 60 * 1000,  // Check every 30 minutes
    autoExtend: false,               // Prompt before extending
    
    onExtensionNeeded: async (state) => {
        // Show custom prompt
        return await showExtendPrompt(`Session expires in ${state.timeRemaining / 60000} minutes`);
    },
    
    onSessionExpired: () => {
        // Redirect to login
        window.location.href = '/login';
    }
});

// Stop when component unmounts
manager.stop();
```

### Manual Session Extension

```javascript
// Check if extension is needed
const state = await lemmaWallet.getSessionState();

if (state.shouldPromptExtend && state.canExtend) {
    // This triggers a tap-only passkey check (no biometric)
    const result = await lemmaWallet.extendBridgeSession();
    
    if (result.success) {
        console.log('Session extended!', {
            newExpiry: result.expiresAt,
            extensionsRemaining: result.extensionsRemaining
        });
    }
}
```

---

## Credential Verification

### Local Verification (Recommended)

Verify credentials without any network calls:

```javascript
// Full verification (~1ms)
const result = await lemmaWallet.verifyLemma(credential);

console.log({
    valid: result.valid,
    reason: result.reason,        // 'valid', 'expired', 'revoked', etc.
    issuer: result.issuer,
    claims: result.claims,
    verifyTimeUs: result.verifyTimeUs  // Microseconds
});
```

### Quick Verification (Fastest)

For repeated checks on the same credential:

```javascript
// Quick verify - uses cached signature (~50μs)
const quick = await lemmaWallet.quickVerify(credential);

// 20x faster than full verification!
```

### Revocation Checking

```javascript
// Check if credential is revoked
const revocation = await lemmaWallet.isRevoked(credential.id);

if (revocation.revoked) {
    console.log('Credential has been revoked!');
} else if (revocation.unchecked) {
    console.log('Revocation list not synced - might be stale');
}

// Force sync revocation list
await lemmaWallet.syncRevocations();
```

---

## React Integration

### Using the Hooks

```tsx
import { useLemma, useLemmaSession, useLemmaVerification } from '@lemma/sdk/react';

function App() {
    // Wallet state and methods
    const { 
        isUnlocked, 
        hasPasskey, 
        isLoading,
        unlock, 
        registerPasskey,
        getCredentials 
    } = useLemma();
    
    // Session management
    const { 
        session, 
        extendSession,
        formattedTimeRemaining 
    } = useLemmaSession({ 
        autoManage: true,
        onSessionExpired: () => navigate('/login')
    });
    
    // Verification
    const { verify, isVerifying, lastResult } = useLemmaVerification();
    
    if (isLoading) return <div>Loading...</div>;
    
    if (!hasPasskey) {
        return (
            <button onClick={registerPasskey}>
                Create Wallet
            </button>
        );
    }
    
    if (!isUnlocked) {
        return (
            <button onClick={unlock}>
                Unlock Wallet
            </button>
        );
    }
    
    return (
        <div>
            <p>Session expires in: {formattedTimeRemaining}</p>
            {session.shouldPromptExtend && (
                <button onClick={extendSession}>
                    Extend Session
                </button>
            )}
        </div>
    );
}
```

### Session Provider Pattern

```tsx
// Create a context for session state
import { createContext, useContext } from 'react';
import { useLemmaSession } from '@lemma/sdk/react';

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
    const session = useLemmaSession({
        autoManage: true,
        checkInterval: 5 * 60 * 1000  // Check every 5 minutes
    });
    
    return (
        <SessionContext.Provider value={session}>
            {children}
        </SessionContext.Provider>
    );
}

export const useSession = () => useContext(SessionContext);
```

---

## Advanced Topics

### Cross-Site Wallet Access (Bridge)

For third-party sites to access the user's central wallet:

```javascript
// The bridge is automatically created when needed
// Just use the session methods:

const state = await lemmaWallet.getSessionState();
// This uses the bridge to check the central wallet

const credentials = await lemmaWallet.getCredentials();
// On third-party sites, this fetches from central wallet
```

### PPID (Pairwise Pseudonymous Identifiers)

Each site sees a different user ID:

```javascript
// Get the user's PPID for your site
const walletSecret = await lemmaWallet.getWalletSecret();

// Derive site-specific ID (HMAC)
const ppid = await derivePPID(walletSecret, 'mysite.com');

// This PPID is unique to mysite.com
// Other sites get different PPIDs for the same user
// Cross-site tracking is impossible!
```

### Service Worker Caching

The SDK automatically registers a service worker on `lemma.id` for offline-first caching:

```javascript
// Check service worker status
const registrations = await navigator.serviceWorker.getRegistrations();
const lemmaSW = registrations.find(r => r.scope.includes('lemma.id'));

if (lemmaSW) {
    console.log('Lemma service worker active - 0 network calls!');
}
```

---

## Troubleshooting

### Common Issues

**Issue: "LemmaWallet is not defined"**
```javascript
// Make sure the script is loaded before using it
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
<script>
    // Wait for DOM ready
    document.addEventListener('DOMContentLoaded', async () => {
        await lemmaWallet.init();
    });
</script>
```

**Issue: "Passkey not supported"**
```javascript
// Check passkey support
if (!lemmaWallet._isPasskeySupported()) {
    // Show fallback auth method
    showFallbackAuth();
}
```

**Issue: Session expiring too fast**
```javascript
// Enable auto-extend
startLemmaSessionManager({
    autoExtend: true  // Will extend without prompting
});
```

**Issue: Credentials not syncing to central wallet**
```javascript
// Force sync to central wallet
await lemmaWallet.syncToCentralWallet(credential);
```

### Debug Mode

```javascript
const wallet = new LemmaWallet({ debug: true });

// Or enable on existing instance
lemmaWallet._options.debug = true;

// Now you'll see detailed logs:
// [LemmaWallet] Wallet initialized
// [LemmaWallet] Session check: valid, 23h remaining
// [LemmaWallet] Credential verified in 0.8ms
```

### Network Tab Verification

To verify you're achieving 0 network calls:

1. Open DevTools → Network tab
2. Filter by "lemma.id"
3. Perform unlock/verify operations
4. Should see: `(ServiceWorker)` or `(from disk cache)`

---

## Performance Benchmarks

| Operation | Time | Network Calls |
|-----------|------|---------------|
| Wallet init | ~50ms | 0 |
| Session check | ~5ms | 0 |
| Full verification | ~1ms | 0 |
| Quick verification | ~50μs | 0 |
| Session extend | ~200ms | 0 (passkey prompt) |
| Revocation sync | ~100ms | 1 (background) |

---

## Next Steps

- [API Reference](./API_REFERENCE.md)
- [Security Audit Checklist](./SECURITY_CHECKLIST.md)
- [Example Implementations](../examples/)
- [TypeScript Types](../sdk/src/types.ts)
