> **Superseded** by [ISHUMAN Agent Integration Guide](ISHUMAN_AGENT_INTEGRATION.md). This document is retained for historical reference only.

# Lemma Platform - Integration Guide

## What is Lemma?

Lemma provides **passwordless authentication** with privacy-preserving identifiers:

- **Passkey-protected wallet**: Users authenticate with biometrics (FaceID/TouchID/fingerprint)
- **Privacy-preserving PPIDs**: Each site gets a unique identifier - no cross-site tracking
- **Cross-device sync**: Unlock once, stay signed in across all linked devices
- **Client-side security**: Wallet secrets are designed to stay client-side in standard flows

---

## Quick Start: Add Login (5 minutes)

### Step 1: Add the SDK

```html
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
```

### Step 2: Initialize and Handle Auth

```javascript
const wallet = new LemmaWallet();
await wallet.init();

// Check if returning from Lemma authentication
const redirectResult = await wallet.checkRedirectReturn();
if (redirectResult?.success) {
    // User just authenticated - send signed lemma to backend
    const auth = await wallet.getAuthenticatedPPID();
    await signInUser(auth.lemma);
    return;
}

// Check current auth state
const auth = await wallet.getAuthenticatedPPID();

if (auth.authenticated) {
    // Already signed in
    await signInUser(auth.lemma);
} else {
    // Show sign-in button
    showSignInButton();
}
```

### Step 3: Add Sign-In Button

```html
<button id="lemma-signin">Sign in with Lemma</button>

<script>
document.getElementById('lemma-signin').addEventListener('click', async () => {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    // This redirects to lemma.id for passkey authentication
    // User will return with encrypted wallet data
    wallet.startRedirectFlow();
});
</script>
```

### Step 4: Backend Verification (Recommended)

```javascript
// Your backend endpoint
app.post('/api/auth/lemma-verify', async (req, res) => {
    const encoded = (req.header('X-Lemma-Credential') || '').trim();
    if (!encoded) return res.status(401).json({ success: false, error: 'missing_lemma_header' });

    const credential = JSON.parse(Buffer.from(encoded, 'base64url').toString('utf8'));
    const verification = await verifyCredentialWithTrust(credential); // issuer + signature + expiry
    if (!verification.valid) return res.status(401).json({ success: false, error: 'invalid_lemma' });

    const claims = credential.claims || credential.credentialSubject || {};
    const ppid = credential.subject || claims.ppid || claims.id;
    let user = await db.users.findOne({ lemma_ppid: ppid });
    if (!user) user = await db.users.create({ lemma_ppid: ppid });

    const token = createSessionToken(user.id);
    res.json({ success: true, token });
});
```

---

## Complete Working Example

```html
<!DOCTYPE html>
<html>
<head>
    <title>My App</title>
</head>
<body>
    <div id="app">
        <div id="loading">Loading...</div>
        <div id="signed-out" style="display: none;">
            <h1>Welcome</h1>
            <button id="signin-btn">Sign in with Lemma</button>
        </div>
        <div id="signed-in" style="display: none;">
            <h1>Welcome back!</h1>
            <button id="signout-btn">Sign Out</button>
        </div>
    </div>

    <script src="https://lemma.id/static/js/lemma-wallet.js"></script>
    <script>
    (async function() {
        const wallet = new LemmaWallet();
        await wallet.init();
        
        // Check for redirect return
        const redirectResult = await wallet.checkRedirectReturn();
        if (redirectResult?.success) {
            const auth = await wallet.getAuthenticatedPPID();
            await handleSignIn(auth.lemma);
            return;
        }
        
        // Check existing auth
        const auth = await wallet.getAuthenticatedPPID();
        
        document.getElementById('loading').style.display = 'none';
        
        if (auth.authenticated) {
            await handleSignIn(auth.lemma);
        } else {
            document.getElementById('signed-out').style.display = 'block';
        }
        
        // Sign in button
        document.getElementById('signin-btn').addEventListener('click', () => {
            wallet.startRedirectFlow();
        });
        
        // Sign out button
        document.getElementById('signout-btn').addEventListener('click', async () => {
            await wallet.lock();
            location.reload();
        });
        
        async function handleSignIn(credential) {
            // Send to your backend
            const response = await fetch('/api/auth/lemma-verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Lemma-Credential': btoa(JSON.stringify(credential))
                        .replace(/\+/g, '-')
                        .replace(/\//g, '_')
                        .replace(/=+$/, '')
                }
            });
            
            if (response.ok) {
                document.getElementById('signed-in').style.display = 'block';
            }
        }
    })();
    </script>
</body>
</html>
```

---

## How It Works

### Authentication Flow

```
1. User clicks "Sign in with Lemma"
   ↓
2. Redirect to lemma.id/wallet/unlock
   ↓
3. User authenticates with passkey (biometric)
   ↓
4. Redirect back with encrypted wallet data
   ↓
5. SDK decrypts locally, derives site-specific PPID
   ↓
6. Your backend verifies the signed credential, then creates/finds user from verified PPID
```

### Cross-Device Sync

- User unlocks wallet on **any device**
- Other devices detect this via background sync
- No re-authentication needed for 24 hours (configurable)
- Locking on any device locks all devices

### Privacy Model

- **Wallet secret**: Generated on first device and intended to stay client-side
- **PPID derivation**: `HMAC(wallet_secret, site_domain)` - computed locally
- **No tracking**: Each site gets a different PPID
- **Server storage model**: Wallet secrets stay client-side; apps/platform services may retain PPID and issuance metadata needed for auth and audit

---

## SDK Reference

### Initialization

```javascript
const wallet = new LemmaWallet();
await wallet.init();
```

### Check Auth State

```javascript
const auth = await wallet.getAuthenticatedPPID();
// Returns: { authenticated: boolean, ppid?: string, needsPasskey: boolean }
```

### Start Authentication

```javascript
// Redirect to lemma.id for passkey auth
wallet.startRedirectFlow();
```

### Handle Redirect Return

```javascript
const result = await wallet.checkRedirectReturn();
// Returns: { success: boolean, walletId?: string }
```

### Derive PPID

```javascript
const ppid = await wallet.derivePPID();
// Returns: "did:lemma:ppid_<64-char-hex>"

// Or for a specific site
const ppid = await wallet.derivePPID('example.com');
```

### Lock Wallet

```javascript
await wallet.lock();
// Clears session locally and globally (all devices)
```

### Get Wallet Info

```javascript
const info = await wallet.getWalletInfo();
// Returns: { hasWallet, hasPasskey, isUnlocked, walletId, ... }
```

---

## Session Duration

Users can configure session duration (1-24 hours) in wallet settings. Default is 24 hours.

```javascript
// SDK respects user's session duration preference
// Sessions auto-expire based on this setting
```

---

## Bot Shield (Optional)

Add bot protection to forms:

```html
<script src="https://lemma.id/static/js/lemma-bot-shield-simple.js"></script>

<form data-lemma-protect="true">
    <input type="email" name="email" required>
    <button type="submit">Submit</button>
</form>
```

---

## Troubleshooting

### "Redirect not working"

Ensure your site is served over HTTPS. The redirect flow requires secure context.

### "PPID is undefined"

Make sure to call `checkRedirectReturn()` before `derivePPID()` when returning from authentication.

### "Session expires too quickly"

Users can adjust session duration at `lemma.id/wallet`. Default is 24 hours.

### "Cross-device sync not working"

Ensure both devices have the wallet linked. Use the QR code or copy link feature at `lemma.id/wallet`.

---

## Support

- Documentation: https://lemma.id/docs
- GitHub Issues: https://github.com/lemma-id/sdk/issues
- Email: support@lemma.id
