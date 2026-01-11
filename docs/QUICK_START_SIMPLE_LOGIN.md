# Quick Start: Add Login in 5 Minutes

Lemma provides passkey-protected wallet authentication. **No passwords. No sessions. Users stay signed in.**

---

## 🎯 **What Makes Lemma Different**

| Traditional Auth | Lemma |
|------------------|-------|
| ❌ Passwords to remember | ✅ Passkey (biometric) |
| ❌ Session expires every 30 min | ✅ Credential persists 90 days |
| ❌ Server tracks all sessions | ✅ Zero server state |
| ❌ Re-login on every device | ✅ Wallet syncs across devices |
| ❌ Add reCAPTCHA for bots | ✅ Cryptographic bot resistance built-in |

**Your credential is like a physical ID card stored in YOUR browser.**

---

## 🚀 **Step 1: Add Lemma Scripts**

```html
<!-- Add before </body> -->
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
```

---

## 🚀 **Step 2: Initialize Wallet**

```javascript
// Initialize once per page
const wallet = new LemmaWallet({ debug: true });
await wallet.init();
```

---

## 🚀 **Step 3: Check Authentication**

```javascript
// Check if user has unlocked wallet today
if (wallet.isAuthenticated()) {
    // User is "signed in"
    const credential = await wallet.getCredential('permission', 'yoursite.com');
    
    if (credential) {
        const claims = credential.claims || credential.credentialSubject;
        console.log('Welcome back!', claims.email || 'User');
        showApp();
    } else {
        // Has wallet, needs permission for this site
        await requestSitePermission();
    }
} else {
    // Not authenticated - show sign-in button
    showSignInButton();
}
```

---

## 🚀 **Step 4: Handle Sign-In**

```javascript
async function handleSignIn() {
    const wallet = new LemmaWallet({ debug: true });
    await wallet.init();
    
    // Check if returning user (has passkey)
    const info = await wallet.getWalletInfo();
    
    if (info.hasPasskey) {
        // Returning user - unlock existing wallet
        await wallet.unlock();
    } else {
        // New user - register passkey
        await wallet.registerPasskey();
    }
    
    // Request permission for this site
    await requestSitePermission();
    
    // Reload to show authenticated state
    window.location.reload();
}

async function requestSitePermission() {
    const walletSecret = await wallet.getWalletSecret();
    
    const response = await fetch('https://lemma.id/api/wallet-auth/issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            site_id: window.location.hostname,
            wallet_secret: walletSecret
        })
    });
    
    const result = await response.json();
    
    if (result.success) {
        await wallet.storeCredential(result.permission_lemma);
        console.log('Permission granted!');
    }
}
```

---

## 🚀 **Step 5: Add UI**

```html
<!-- Sign-in button (hidden when authenticated) -->
<button id="signin-btn" onclick="handleSignIn()" style="display: none;">
    Sign in with Lemma
</button>

<!-- App content (hidden until authenticated) -->
<div id="app" style="display: none;">
    <p>Welcome, <span id="user-email"></span>!</p>
    <!-- Your app content -->
</div>

<script>
async function initAuth() {
    const wallet = new LemmaWallet({ debug: true });
    await wallet.init();
    
    if (wallet.isAuthenticated()) {
        const cred = await wallet.getCredential('permission', window.location.hostname);
        if (cred) {
            const claims = cred.claims || cred.credentialSubject;
            document.getElementById('user-email').textContent = claims.email || 'User';
            document.getElementById('app').style.display = 'block';
        } else {
            document.getElementById('signin-btn').style.display = 'block';
        }
    } else {
        document.getElementById('signin-btn').style.display = 'block';
    }
}

initAuth();
</script>
```

---

## ✅ **That's It! Your Site Now Has:**

- ✅ Passkey authentication (Touch ID, Face ID, Windows Hello)
- ✅ No passwords to manage
- ✅ No server sessions to maintain
- ✅ Built-in bot resistance
- ✅ Works offline after first auth
- ✅ 90-day credential persistence
- ✅ Instant revocation when needed (<100ms)

---

## 🔄 **Authentication Flow**

### First-Time User

```
1. User clicks "Sign in with Lemma"
   ↓
2. Browser prompts for passkey creation (biometric)
   ↓
3. Wallet created, passkey registered
   ↓
4. Site requests permission from Lemma API
   ↓
5. Credential stored in user's wallet
   ↓
6. User is authenticated ✅
```

### Returning User (Same Device)

```
1. Page loads
   ↓
2. wallet.isAuthenticated() checks if unlocked today
   ↓
3. If YES → Instant access (no prompt!) ✅
4. If NO → Browser prompts passkey (biometric)
   ↓
5. Wallet unlocked → User authenticated ✅
```

### Returning User (Different Device)

```
1. User sets up new device
   ↓
2. Registers NEW passkey on new device
   ↓
3. OR uses QR code sync from existing device
   ↓
4. Wallet synced → All credentials available ✅
```

---

## 🔐 **Privacy: Different Sites Can't Track You**

```
Same user, different sites:

yoursite.com sees: did:lemma:ppid_abc123...
othersite.com sees: did:lemma:ppid_def456...

These identifiers CANNOT be correlated!
User privacy preserved across the network.
```

---

## 🛡️ **Security Features**

### No Sessions = No Session Hijacking

```
Traditional:
  Attacker steals session cookie → Full access

Lemma:
  No session cookies exist
  Credential is in user's wallet, protected by passkey
  Attacker needs physical device + biometrics
```

### Passkey = Phishing Resistant

```
Phishing site: evil-site.com pretending to be yoursite.com

Traditional:
  User enters password → Attacker has credentials

Lemma:
  Passkey is bound to yoursite.com domain
  Browser REFUSES to use it on evil-site.com
  Attack fails automatically
```

---

## 🎯 **Common Patterns**

### Check Specific Permission

```javascript
async function requireAdmin() {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    const cred = await wallet.getCredential('permission', 'yoursite.com');
    const claims = cred?.claims || cred?.credentialSubject || {};
    
    if (claims.permissionId === 'admin' || claims.permissions?.includes('admin')) {
        return true;
    }
    
    window.location.href = '/unauthorized';
    return false;
}
```

### Handle Sign-Out

```javascript
async function handleSignOut() {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    // Remove credential for this site
    const credentials = await wallet.getCredentials('permission');
    for (const cred of credentials) {
        const claims = cred.claims || cred.credentialSubject || {};
        if (claims.siteId === window.location.hostname) {
            await wallet.removeCredential(cred.id);
        }
    }
    
    window.location.reload();
}
```

**Note:** "Sign out" removes the credential, but the wallet still exists. The user can get a new credential anytime by unlocking their wallet again.

### Check Credential Expiration

```javascript
async function checkCredentialStatus() {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    const cred = await wallet.getCredential('permission', 'yoursite.com');
    
    if (!cred) {
        return { valid: false, reason: 'no_credential' };
    }
    
    const expiresAt = cred.expirationDate || cred.claims?.expiresAt;
    if (expiresAt && Date.now() > expiresAt) {
        return { valid: false, reason: 'expired' };
    }
    
    return { valid: true, credential: cred };
}
```

---

## 📱 **Mobile Support**

Lemma works great on mobile:

- **iOS**: Face ID, Touch ID
- **Android**: Fingerprint, Face Unlock

Same code works on all platforms - the browser handles passkey UI.

---

## ⚡ **Performance**

| Operation | Time |
|-----------|------|
| Passkey prompt | ~300ms (biometric) |
| Credential check | <1ms (local) |
| Permission request | ~100ms (network) |
| Signature verification | 32µs (local) |

**After first auth, everything is local and instant.**

---

## 🐛 **Troubleshooting**

### "Passkey not supported"

```javascript
// Check WebAuthn support
if (!window.PublicKeyCredential) {
    // Show email fallback
    showEmailLogin();
}
```

### "Wallet not persisting"

This usually means private/incognito mode. IndexedDB is blocked in some browsers' private mode.

### "Permission request failed"

```javascript
// Check the response
const response = await fetch('https://lemma.id/api/wallet-auth/issue', ...);
const result = await response.json();

if (!result.success) {
    console.error('Error:', result.error);
    // Common: site_id format invalid, wallet_secret missing
}
```

---

## 📖 **Next Steps**

- [SDK Documentation](../sdk/README.md) - Full API reference
- [IAM API Reference](./IAM_API_REFERENCE.md) - Server-side endpoints
- [Architecture](./ARCHITECTURE_WALLET_FIRST.md) - How it works

---

## 🆘 **Support**

- **Documentation**: https://lemma.id/docs
- **Live Demo**: https://lemma.id
- **Email**: support@lemma.id

---

## 🎉 **Welcome to Passwordless Authentication**

**Traditional thinking:** Users must remember passwords and re-login constantly
**Lemma thinking:** Passkey unlocks wallet, credentials persist until revoked

**Your users will thank you for not asking for passwords.**
