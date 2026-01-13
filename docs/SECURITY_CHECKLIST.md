# Lemma Security Checklist

> Security audit checklist for Lemma integration

## Overview

This checklist helps developers verify their Lemma integration follows security best practices.

---

## ✅ Transport Security

| Check | Status | Notes |
|-------|--------|-------|
| HTTPS enforced for all production traffic | ⬜ | Required for WebAuthn |
| TLS 1.2+ only | ⬜ | Disable TLS 1.0/1.1 |
| HSTS header enabled | ⬜ | `Strict-Transport-Security` |
| Certificate pinning (mobile) | ⬜ | Optional but recommended |

### Verification:
```bash
# Check HTTPS headers
curl -I https://yoursite.com

# Verify TLS version
openssl s_client -connect yoursite.com:443 -tls1_2
```

---

## ✅ Cross-Origin Security

| Check | Status | Notes |
|-------|--------|-------|
| Bridge iframe only from `lemma.id` | ⬜ | Verify iframe src |
| postMessage origin validation | ⬜ | Always check `event.origin` |
| CSP `frame-ancestors` set | ⬜ | For your pages embedding bridge |
| No sensitive data in URL params | ⬜ | Use postMessage instead |

### Verification:
```javascript
// Correct origin checking
window.addEventListener('message', (event) => {
    if (!event.origin.includes('lemma.id')) {
        console.warn('Rejected message from:', event.origin);
        return;
    }
    // Process message...
});
```

---

## ✅ Credential Storage

| Check | Status | Notes |
|-------|--------|-------|
| Credentials stored in IndexedDB | ⬜ | Not localStorage |
| Wallet secret never exposed to server | ⬜ | Stays client-side |
| Session expiry enforced | ⬜ | Default 24h, max 7 extensions |
| Passkey required for unlock | ⬜ | No bypass allowed |

### Verification:
```javascript
// Check storage location
const dbRequest = indexedDB.open('LemmaWallet');
dbRequest.onsuccess = () => {
    console.log('✅ Using IndexedDB for storage');
};

// Verify session check
const state = await lemmaWallet.getSessionState();
if (state.expiresAt < Date.now()) {
    console.log('✅ Session expiry enforced');
}
```

---

## ✅ Passkey Security

| Check | Status | Notes |
|-------|--------|-------|
| `userVerification: 'required'` for unlock | ⬜ | Full biometric |
| `userVerification: 'discouraged'` for extend | ⬜ | Tap-only for extensions |
| Credential bound to RP ID | ⬜ | Passkeys are RP-specific |
| No passkey export capability | ⬜ | Platform authenticator preferred |

### Verification:
```javascript
// Check unlock requires full verification
const credential = await navigator.credentials.get({
    publicKey: {
        // ...
        userVerification: 'required'  // Must be 'required' for unlock
    }
});
```

---

## ✅ Signature Verification

| Check | Status | Notes |
|-------|--------|-------|
| Ed25519 verification enabled | ⬜ | WebCrypto API |
| Issuer public key validated | ⬜ | From DID or stored issuer |
| Signature checked before trust | ⬜ | Always verify, never assume |
| Expired credentials rejected | ⬜ | Check `expiresAt` field |

### Verification:
```javascript
// Always verify before trusting
const result = await lemmaWallet.verifyLemma(credential);
if (!result.valid) {
    throw new Error(`Invalid credential: ${result.reason}`);
}
```

---

## ✅ Revocation Checking

| Check | Status | Notes |
|-------|--------|-------|
| Revocation list synced periodically | ⬜ | Auto-sync on init |
| Credentials checked against revocation | ⬜ | Part of verifyLemma() |
| Stale revocation data flagged | ⬜ | `unchecked: true` in result |
| Network failure doesn't block auth | ⬜ | Graceful degradation |

### Verification:
```javascript
const revInfo = await lemmaWallet.getRevocationInfo();
console.log('Revocation list:', {
    synced: revInfo.synced,
    count: revInfo.count,
    age: revInfo.age / 1000 + ' seconds old'
});
```

---

## ✅ Session Management

| Check | Status | Notes |
|-------|--------|-------|
| Session stored in IndexedDB | ⬜ | Not cookies or localStorage |
| Session bound to wallet | ⬜ | Requires passkey to create |
| Max extension limit (7) | ⬜ | Force re-auth after 7 days |
| Extension requires user presence | ⬜ | Tap-only, not silent |

### Verification:
```javascript
const state = await lemmaWallet.getSessionState();
console.log('Session security:', {
    extensionCount: state.extensionCount,
    maxReached: state.extensionCount >= 7,
    canExtend: state.canExtend
});
```

---

## ✅ Privacy Protection

| Check | Status | Notes |
|-------|--------|-------|
| PPID used for user identification | ⬜ | Site-specific IDs |
| No cross-site tracking possible | ⬜ | Different PPID per site |
| Wallet secret never sent to server | ⬜ | PPID derived client-side |
| Credentials filtered by site | ⬜ | Per-origin isolation |

### Verification:
```javascript
// PPID is different for each site
const ppid1 = await derivePPID(walletSecret, 'site1.com');
const ppid2 = await derivePPID(walletSecret, 'site2.com');
console.log('PPIDs are different:', ppid1 !== ppid2);
```

---

## ✅ Content Security Policy

Recommended CSP headers:

```
Content-Security-Policy:
    default-src 'self';
    script-src 'self' https://lemma.id;
    frame-src https://lemma.id;
    connect-src 'self' https://lemma.id;
```

### For bridge page (`/wallet/bridge`):
```
Content-Security-Policy:
    frame-ancestors https: http://localhost:* http://127.0.0.1:*;
```

---

## ✅ Service Worker Security

| Check | Status | Notes |
|-------|--------|-------|
| SW only registered on lemma.id | ⬜ | Or explicit opt-in |
| Cache-first for static assets | ⬜ | Bridge, SDK JS |
| Network-first for sensitive data | ⬜ | If any |
| SW scope properly restricted | ⬜ | Use `Service-Worker-Allowed` |

---

## ✅ Error Handling

| Check | Status | Notes |
|-------|--------|-------|
| No sensitive data in error messages | ⬜ | Sanitize before display |
| Auth failures don't reveal user existence | ⬜ | Generic messages |
| Console logs disabled in production | ⬜ | Set `debug: false` |
| Error boundaries in React | ⬜ | Catch verification errors |

---

## ✅ Input Validation

| Check | Status | Notes |
|-------|--------|-------|
| Credential data validated before use | ⬜ | Check structure |
| Origin always validated | ⬜ | postMessage origin check |
| No eval() or innerHTML with data | ⬜ | Prevent XSS |
| Claims sanitized before display | ⬜ | Escape HTML |

---

## Security Contact

Report security vulnerabilities to: **security@lemma.id**

We follow responsible disclosure and will work with you to resolve issues.

---

## Audit History

| Date | Auditor | Scope | Result |
|------|---------|-------|--------|
| TBD | TBD | Full SDK audit | TBD |

---

## Compliance Notes

- **GDPR**: No personal data stored on Lemma servers. All data client-side.
- **CCPA**: Same as GDPR - no server-side data collection.
- **SOC 2**: In progress (server infrastructure only).
- **PCI DSS**: Not applicable - no payment data handling.
