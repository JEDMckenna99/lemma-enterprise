# Quick Start: Add User Login in 5 Minutes

Lemma provides passkey-protected wallet authentication via a redirect flow. **This guide is for end-user website login, not the default agent runtime auth path.** For agent integrations, use the proof-first developer contract and send `X-Lemma-Credential` on protected requests.

---

## What Makes Lemma Different

| Traditional Auth | Lemma |
|------------------|-------|
| Passwords to remember | Passkey (biometric) |
| Session expires every 30 min | Session persists 24 hours |
| Re-login on every device | Single unlock syncs all devices |
| Server tracks all sessions | Privacy-preserving PPIDs |
| Add reCAPTCHA for bots | Cryptographic bot resistance built-in |

**Wallet secrets are designed to remain client-side in standard flows; encryption/decryption occurs in the browser wallet.**

---

## Step 1: Add Lemma SDK

```html
<!-- Add before </body> -->
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
```

---

## Step 2: Initialize and Check Auth State

```javascript
const wallet = new LemmaWallet();
await wallet.init();

// Check for redirect return (user coming back from lemma.id)
const redirectResult = await wallet.checkRedirectReturn();
if (redirectResult?.success) {
    // User just authenticated via redirect
    console.log('Authenticated!', redirectResult.walletId);
}

// Check current auth state
const auth = await wallet.getAuthenticatedPPID();
if (auth.authenticated) {
    // User is authenticated - show app
    console.log('User PPID:', auth.ppid);
    showApp(auth.ppid);
} else {
    // Not authenticated - show sign in button
    showSignInButton();
}
```

---

## Step 3: Handle Sign-In Button

```javascript
async function signInWithLemma() {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    const auth = await wallet.getAuthenticatedPPID();
    
    if (auth.needsPasskey) {
        // Redirect to Lemma for authentication
        // This will redirect user to lemma.id/wallet/unlock
        // After passkey verification, they return with encrypted wallet data
        wallet.startRedirectFlow();
    } else if (auth.authenticated) {
        // Already authenticated
        handleAuthenticated(auth.ppid);
    }
}
```

---

## Step 4: Add UI

```html
<!-- Sign-in button -->
<button id="signin-btn" onclick="signInWithLemma()">
    Sign in with Lemma
</button>

<!-- App content (hidden until authenticated) -->
<div id="app" style="display: none;">
    <p>Welcome! Your site-specific ID is: <code id="user-ppid"></code></p>
    <button onclick="signOut()">Sign Out</button>
</div>

<script>
async function initAuth() {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    // Handle redirect return
    const redirectResult = await wallet.checkRedirectReturn();
    
    // Check auth state
    const auth = await wallet.getAuthenticatedPPID();
    
    if (auth.authenticated) {
        document.getElementById('signin-btn').style.display = 'none';
        document.getElementById('app').style.display = 'block';
        document.getElementById('user-ppid').textContent = auth.ppid;
    } else {
        document.getElementById('signin-btn').style.display = 'block';
        document.getElementById('app').style.display = 'none';
    }
}

async function signOut() {
    const wallet = new LemmaWallet();
    await wallet.init();
    await wallet.lock();
    window.location.reload();
}

initAuth();
</script>
```

---

## Complete Working Example

```html
<!DOCTYPE html>
<html>
<head>
    <title>My App with Lemma Auth</title>
</head>
<body>
    <div id="auth-container">
        <button id="signin-btn" style="display:none">Sign in with Lemma</button>
        <div id="app" style="display:none">
            <p>Authenticated as: <code id="ppid"></code></p>
            <button id="signout-btn">Sign Out</button>
        </div>
    </div>

    <script src="https://lemma.id/static/js/lemma-wallet.js"></script>
    <script>
    (async function() {
        const wallet = new LemmaWallet();
        await wallet.init();
        
        // Handle redirect return
        await wallet.checkRedirectReturn();
        
        // Check auth state
        const auth = await wallet.getAuthenticatedPPID();
        
        const signinBtn = document.getElementById('signin-btn');
        const app = document.getElementById('app');
        
        if (auth.authenticated) {
            app.style.display = 'block';
            document.getElementById('ppid').textContent = auth.ppid;
        } else {
            signinBtn.style.display = 'block';
        }
        
        // Sign in handler
        signinBtn.addEventListener('click', () => {
            wallet.startRedirectFlow();
        });
        
        // Sign out handler
        document.getElementById('signout-btn').addEventListener('click', async () => {
            await wallet.lock();
            window.location.reload();
        });
    })();
    </script>
</body>
</html>
```

---

## How It Works

### First-Time User

```
1. User clicks "Sign in with Lemma"
   ↓
2. Redirected to lemma.id/wallet/unlock
   ↓
3. User creates wallet + passkey (biometric)
   ↓
4. Wallet secret encrypted client-side
   ↓
5. Redirected back with encrypted data
   ↓
6. SDK decrypts locally, user authenticated
```

### Returning User (Any Device with Linked Wallet)

```
1. User clicks "Sign in with Lemma"
   ↓
2. Redirected to lemma.id/wallet/unlock
   ↓
3. Passkey verified (if needed today)
   ↓
4. Wallet secret encrypted client-side
   ↓
5. Redirected back, authenticated
```

### Cross-Device Sync

```
1. User sets up wallet on PC
   ↓
2. On phone: lemma.id/wallet → "Link Device"
   ↓
3. Scan QR code from PC
   ↓
4. Phone now has same wallet
   ↓
5. Lock on PC → Signs out everywhere
```

---

## Privacy: Site-Specific Identifiers

```
Same user, different sites:

yoursite.com sees: did:lemma:ppid_abc123...
othersite.com sees: did:lemma:ppid_def456...

These identifiers CANNOT be correlated!
Derived via HMAC(wallet_secret, site_domain)
```

---

## Backend Integration

Verify the PPID on your backend:

```javascript
// Your backend (Node.js example)
app.post('/api/auth/lemma-verify', async (req, res) => {
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
    let user = await db.users.findOne({ lemma_ppid: ppid });
    if (!user) {
        user = await db.users.create({
            lemma_ppid: ppid,
            created_at: new Date()
        });
    }

    // Create your app's session
    req.session.userId = user.id;
    res.json({ success: true, user_id: user.id });
});
```

### Protected API auth order (runtime)

If you later protect backend routes with Lemma decorators, runtime evaluates:

1. Optional bearer compatibility token path (if enabled)
2. `X-Agent-Token`
3. Agent session cookie
4. `X-Lemma-Credential`
5. API key fallback

For new integrations, use `X-Lemma-Credential` directly.

---

## Security Features

### No Passwords = No Password Breaches

The wallet secret is generated client-side and protected by passkey (biometrics). Standard authentication flows are designed to keep it off platform servers.

### Passkey = Phishing Resistant

Passkeys are bound to domain. Browser refuses to use lemma.id passkey on evil-lemma.com.

### Cross-Device Lock

Lock wallet on any device → All devices sign out within seconds.

---

## Performance

| Operation | Time |
|-----------|------|
| Redirect flow | ~2-3s (includes passkey) |
| Auth check (cached) | <5ms |
| PPID derivation | <1ms |
| Cross-device lock | <5s |

---

## Troubleshooting

### "Passkey not supported"

```javascript
if (!window.PublicKeyCredential) {
    // WebAuthn not available
    // Show alternative auth method
}
```

### "Redirect not returning data"

Make sure you're calling `checkRedirectReturn()` on page load before checking auth state.

### "Session not persisting"

Private/incognito mode blocks IndexedDB in some browsers.

---

## SDK Reference

```javascript
const wallet = new LemmaWallet();

// Initialize (required first)
await wallet.init();

// Check redirect return
const result = await wallet.checkRedirectReturn();

// Get auth state
const auth = await wallet.getAuthenticatedPPID();
// Returns: { authenticated: bool, ppid: string, needsPasskey: bool }

// Start redirect flow
wallet.startRedirectFlow();

// Get wallet info
const info = await wallet.getWalletInfo();
// Returns: { hasPasskey: bool, hasWalletSecret: bool, isUnlocked: bool }

// Lock wallet (signs out everywhere)
await wallet.lock();

// Check if unlocked
wallet.isUnlocked();
```

---

## Support

- **Documentation**: https://lemma.id/docs
- **Live Demo**: https://lemma.id/wallet
- **Email**: support@lemma.id
