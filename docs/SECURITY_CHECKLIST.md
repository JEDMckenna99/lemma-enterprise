# Lemma Security Checklist

> Security audit checklist for Lemma integration

## Overview

This checklist helps developers verify their Lemma integration follows security best practices.

## Status Legend

- `PASS`: verified with current production evidence.
- `IN_PROGRESS`: partially verified (code and/or smoke checks), full validation pending.
- `UNKNOWN`: not yet validated with sufficient evidence.
- `FAIL`: validated and not meeting control requirement.

## Current Verification Snapshot (2026-02-11)

- Environment: production `https://lemma.id` (Heroku)
- Evidence:
  - `docs/launch-evidence/2026-02-11-heroku-smoke.md`
  - `docs/launch-evidence/2026-02-11-heroku-extended-smoke.md`
  - `docs/launch-evidence/2026-02-11-transport-tls-checks.md`
  - `docs/launch-evidence/2026-02-11-origin-and-dom-safety-checks.md`
  - `docs/launch-evidence/2026-02-11-code-remediation.md`
  - `docs/launch-evidence/2026-02-11-post-remediation-scan.md`
  - `docs/launch-evidence/2026-02-11-130201-post-deploy-summary.md`
  - `docs/launch-evidence/2026-02-11-132844-post-deploy-summary.md`
  - `docs/launch-evidence/2026-02-11-ci-gate-setup.md`
- Note: this snapshot does not replace full manual/browser E2E validation.

---

## ✅ Transport Security

| Check | Status | Notes |
|-------|--------|-------|
| HTTPS enforced for all production traffic | PASS | `http://lemma.id` returns `301` redirect to HTTPS in production test |
| TLS 1.2+ only | PASS | TLS 1.1 handshake failed while TLS 1.2 request succeeded in production test |
| HSTS header enabled | PASS | `Strict-Transport-Security` observed on production root |
| Certificate pinning (mobile) | UNKNOWN | Optional control; mobile app policy evidence not recorded |

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
| Bridge iframe only from `lemma.id` | IN_PROGRESS | Bridge endpoint validated; third-party embed policy still needs E2E confirmation |
| postMessage origin validation | IN_PROGRESS | Implemented in code patterns; runtime cross-site abuse tests still pending |
| CSP `frame-ancestors` set | PASS | Present on `/wallet/bridge` in production headers |
| No sensitive data in URL params | UNKNOWN | Needs targeted flow inspection and capture |

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
| Credentials stored in IndexedDB | IN_PROGRESS | Architecture and SDK indicate IndexedDB; production browser artifact capture pending |
| Wallet secret never exposed to server | UNKNOWN | Requires request-level tracing proof across all auth flows |
| Session expiry enforced | IN_PROGRESS | Session guardrails validated on API; full client lifecycle validation pending |
| Passkey required for unlock | IN_PROGRESS | Passkey auth endpoints and challenge flows validated; full UI/E2E still pending |

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
| `userVerification: 'required'` for unlock | IN_PROGRESS | Enforced in registration/auth verification code; cross-browser runtime matrix pending |
| `userVerification: 'discouraged'` for extend | IN_PROGRESS | Documented in implemented session model; direct runtime proof capture pending |
| Credential bound to RP ID | IN_PROGRESS | `rpId: lemma.id` observed in passkey challenge response |
| No passkey export capability | UNKNOWN | Depends on authenticator/platform behavior; policy evidence not captured |

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
| Ed25519 verification enabled | IN_PROGRESS | Verification components present in code and docs; full black-box proof still pending |
| Issuer public key validated | UNKNOWN | Needs explicit test artifacts for issuer key trust-chain validation |
| Signature checked before trust | IN_PROGRESS | Verification-first flow implemented; end-to-end negative tests pending |
| Expired credentials rejected | UNKNOWN | Requires dedicated expiry test evidence |

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
| Revocation list synced periodically | IN_PROGRESS | Revocation endpoints healthy and cache metadata present |
| Credentials checked against revocation | FAIL | Post-deploy test found site-specific revoke did not appear in list/bloom (`site_updated=false`) |
| Stale revocation data flagged | UNKNOWN | Needs explicit stale-cache scenario test output |
| Network failure doesn't block auth | UNKNOWN | Offline/failure-mode validation not yet recorded |

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
| Session stored in IndexedDB | IN_PROGRESS | SDK design indicates IndexedDB; production browser artifact still needed |
| Session bound to wallet | IN_PROGRESS | Session APIs require authenticated context; full proof path pending |
| Max extension limit (7) | IN_PROGRESS | Documented in implementation progress; runtime validation pending |
| Extension requires user presence | IN_PROGRESS | Design enforces user presence; capture with passkey prompt evidence pending |

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
| PPID used for user identification | IN_PROGRESS | Architecture/docs define PPID model; live proof capture pending |
| No cross-site tracking possible | UNKNOWN | Requires adversarial correlation test evidence |
| Wallet secret never sent to server | UNKNOWN | Needs network trace evidence across all flows |
| Credentials filtered by site | IN_PROGRESS | Site-scoped controls documented; cross-site denial tests pending |

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
| SW only registered on lemma.id | IN_PROGRESS | Documented behavior; explicit production registration artifact pending |
| Cache-first for static assets | IN_PROGRESS | Bridge cache headers validated; full SW mode test still pending |
| Network-first for sensitive data | UNKNOWN | Needs explicit request policy verification |
| SW scope properly restricted | UNKNOWN | Requires header/scope validation artifact |

---

## ✅ Error Handling

| Check | Status | Notes |
|-------|--------|-------|
| No sensitive data in error messages | IN_PROGRESS | Basic unauthenticated responses reviewed; full error corpus audit pending |
| Auth failures don't reveal user existence | IN_PROGRESS | Unauthenticated register/session paths return generic denial statuses |
| Console logs disabled in production | UNKNOWN | Needs built artifact and runtime console audit |
| Error boundaries in React | UNKNOWN | Requires frontend app audit evidence |

---

## ✅ Input Validation

| Check | Status | Notes |
|-------|--------|-------|
| Credential data validated before use | IN_PROGRESS | Request validation present in key API paths; comprehensive coverage pending |
| Origin always validated | IN_PROGRESS | Runtime checks show disallowed origin POST has no ACAO; preflight strictness still needs review |
| No eval() or innerHTML with data | IN_PROGRESS | Production templates refactored to safer DOM/text patterns; remaining dynamic interpolation exists in non-production test/build files |
| Claims sanitized before display | UNKNOWN | Requires UI rendering audit evidence |

---

## Security Contact

Report security vulnerabilities to: **security@lemma.id**

We follow responsible disclosure and will work with you to resolve issues.

---

## Audit History

| Date | Auditor | Scope | Result |
|------|---------|-------|--------|
| TBD | TBD | Full SDK audit | TBD |
| 2026-02-11 | Internal (launch gate) | Production smoke + header + guardrail checks | Partial verification complete; full audit pending |
| 2026-02-11 | Internal (post-deploy) | Heroku `v1676` automated launch gate run | Smoke/transport/origin checks passed; full E2E audit still pending |

---

## Compliance Notes

- **GDPR**: No personal data stored on Lemma servers. All data client-side.
- **CCPA**: Same as GDPR - no server-side data collection.
- **SOC 2**: In progress (server infrastructure only).
- **PCI DSS**: Not applicable - no payment data handling.
