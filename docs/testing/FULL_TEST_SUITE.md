# Lemma Full Test Suite

Complete test coverage for all API and SDK flows.

## Test Environment

```
Production: https://lemma.id
Test Site: Any third-party site with SDK integrated
Browser: Chrome/Firefox with DevTools open (Console tab)
```

---

## Part 1: API Tests (curl/Postman)

### 1.1 Bloom Filter API

```bash
# Test: Get bloom filter
GET https://lemma.id/api/revocation/bloom-filter

# Expected:
{
  "success": true,
  "filter_type": "global_sha256",
  "count": <number>,
  "bloom_filter": {
    "capacity": 100000,
    "false_positive_rate": 1e-6,
    "k_hashes": 20,
    "m_bits": 2875518
  }
}
```

**Pass Criteria:** `success: true`, bloom_filter metadata present

---

### 1.2 Credential Issuance API

```bash
# Test: Issue credential with new security fields
POST https://lemma.id/api/wallet-auth/issue
Content-Type: application/json

{
  "site_id": "test.example.com",
  "wallet_secret": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}

# Expected in response:
{
  "success": true,
  "permission_lemma": {
    "credentialScope": "site_specific",    # NEW
    "deviceBound": true,                    # NEW
    "credentialSubject": {
      "siteId": "test.example.com",
      "credentialScope": "site_specific",  # NEW
      "deviceBound": "true"                # NEW
    }
  }
}
```

**Pass Criteria:** 
- [ ] `credentialScope: "site_specific"` in credential
- [ ] `deviceBound: true` in credential
- [ ] `siteId` matches requested site

---

### 1.3 Revocation API - Site-Specific

```bash
# Test: Revoke site-specific credential (targeted sync)
POST https://lemma.id/api/wallet/revoke
Content-Type: application/json

{
  "credential_id": "test_site_specific_001",
  "credential_type": "permission",
  "credential_scope": "site_specific",
  "site_domain": "example.com",
  "reason": "user_requested"
}

# Expected:
{
  "success": true,
  "revocation_type": "site_specific",
  "scope": "Only this site's permissions affected",
  "sync_method": "event_driven_redis_pubsub"
}
```

**Pass Criteria:**
- [ ] `revocation_type: "site_specific"`
- [ ] `scope` mentions "Only this site"

---

### 1.4 Revocation API - Cross-Site

```bash
# Test: Revoke cross-site credential (global sync)
POST https://lemma.id/api/wallet/revoke
Content-Type: application/json

{
  "credential_id": "test_cross_site_001",
  "credential_type": "permission",
  "credential_scope": "cross_site",
  "site_domain": "example.com",
  "reason": "user_requested"
}

# Expected:
{
  "success": true,
  "revocation_type": "cross_site",
  "credential_scope": "cross_site",
  "scope": "All sites using this credential will be updated"
}
```

**Pass Criteria:**
- [ ] `revocation_type: "cross_site"`
- [ ] `scope` mentions "All sites"

---

### 1.5 Session Sync API

```bash
# Test: Session sync (requires valid session cookie)
POST https://lemma.id/api/wallet/session-sync
Content-Type: application/json
Cookie: lemma_wallet_session=<valid_token>

# Expected if no session:
{
  "success": false,
  "error": "no_session"
}

# Expected if valid session:
{
  "success": true,
  "session": {
    "valid": true,
    "wallet_id": "...",
    "time_remaining": <seconds>
  }
}
```

**Pass Criteria:**
- [ ] Returns session info when cookie present
- [ ] Returns error when no cookie

---

### 1.6 Revocation List API

```bash
# Test: Get plain revocation list
GET https://lemma.id/api/v1/revocation/list

# Expected:
{
  "success": true,
  "revocations": ["cred_id_1", "cred_id_2", ...],
  "count": <number>,
  "ttl_ms": 3600000
}
```

**Pass Criteria:** `success: true`, `revocations` array present

---

## Part 2: SDK Tests (Browser Console)

### Setup: Load SDK on Test Page

```javascript
// On any page, load SDK
const script = document.createElement('script');
script.src = 'https://lemma.id/static/js/lemma-wallet.js?v=' + Date.now();
document.head.appendChild(script);

// Wait for load, then:
const wallet = new LemmaWallet();
await wallet.init();
console.log('SDK Version:', LemmaWallet.VERSION);
```

---

### 2.1 Wallet Info

```javascript
// Test: Get wallet info
const info = await wallet.getWalletInfo();
console.log('Wallet Info:', info);

// Expected:
{
  hasPasskey: true/false,
  isUnlocked: true/false,
  walletId: "..." or null,
  sessionExpiry: <timestamp> or null
}
```

**Pass Criteria:**
- [ ] Returns object with expected fields
- [ ] `hasPasskey` reflects actual state

---

### 2.2 Register Passkey (lemma.id only)

```javascript
// Test: Register passkey (run on lemma.id)
const result = await wallet.registerPasskey();
console.log('Register result:', result);

// Expected:
{
  success: true,
  walletId: "...",
  message: "Passkey registered successfully"
}
```

**Pass Criteria:**
- [ ] `success: true`
- [ ] Browser prompts for passkey creation
- [ ] Session cookie set (check Application > Cookies)

---

### 2.3 Unlock Wallet

```javascript
// Test: Unlock with existing passkey
const result = await wallet.unlock();
console.log('Unlock result:', result);

// Expected:
{
  success: true,
  walletId: "...",
  expiresAt: <timestamp>
}
```

**Pass Criteria:**
- [ ] `success: true`
- [ ] Browser prompts for passkey
- [ ] Session stored in IndexedDB (check Application > IndexedDB > LemmaWallet)

---

### 2.4 Lock Wallet

```javascript
// Test: Lock wallet
const result = await wallet.lock();
console.log('Lock result:', result);

// Expected:
{
  success: true
}
```

**Pass Criteria:**
- [ ] `success: true`
- [ ] Session cleared from IndexedDB
- [ ] Session cookie cleared (check cookies)

---

### 2.5 Auto Authenticate (Third-Party Site)

```javascript
// Test: Auto-authenticate on third-party site
const result = await wallet.autoAuthenticate();
console.log('Auto-auth result:', result);

// Expected if unlocked on lemma.id:
{
  authenticated: true,
  walletId: "...",
  walletSecret: "...",
  needsPasskey: false
}

// Expected if not unlocked:
{
  authenticated: false,
  needsPasskey: true,
  message: "..."
}
```

**Pass Criteria:**
- [ ] Detects bridge session correctly
- [ ] Returns wallet secret when authenticated

---

### 2.6 Popup Unlock (Third-Party Site)

```javascript
// Test: Popup unlock flow
const result = await wallet.unlockWithPopup();
console.log('Popup result:', result);

// Expected:
{
  success: true,
  walletId: "..."
}
```

**Pass Criteria:**
- [ ] Popup opens centered
- [ ] Popup shows unlock/register UI
- [ ] Parent window receives success message
- [ ] Session synced to third-party site

---

### 2.7 Get Auth State

```javascript
// Test: Get authentication state for UI
const state = await wallet.getAuthState();
console.log('Auth state:', state);

// Expected:
{
  hasWallet: true/false,
  isUnlocked: true/false,
  walletSecret: "..." or null,
  suggestedAction: "none" | "unlock" | "register" | "redirect_to_lemma",
  suggestedButtonText: "...",
  unlockUrl: "https://lemma.id/wallet/simple"
}
```

**Pass Criteria:**
- [ ] `suggestedAction` reflects correct state
- [ ] `suggestedButtonText` is appropriate

---

### 2.8 Store Credential

```javascript
// Test: Store a credential (requires unlock)
const credential = {
  id: 'test_cred_' + Date.now(),
  issuer: 'did:lemma:test',
  claims: {
    siteId: window.location.hostname,
    permissions: 'read,write',
    expiresAt: new Date(Date.now() + 86400000).toISOString()
  }
};

const result = await wallet.storeCredential(credential);
console.log('Store result:', result);

// Expected:
{
  success: true,
  id: "test_cred_..."
}
```

**Pass Criteria:**
- [ ] `success: true`
- [ ] Credential appears in IndexedDB

---

### 2.9 Get Credentials

```javascript
// Test: Get credentials (filtered by site on third-party)
const creds = await wallet.getCredentials();
console.log('Credentials:', creds);

// Expected: Array of credentials for this site only (on third-party)
// Or all credentials (on lemma.id)
```

**Pass Criteria:**
- [ ] Returns array
- [ ] On third-party: only returns credentials matching current site's siteId
- [ ] On lemma.id: returns all credentials

---

### 2.10 Verify Credential

```javascript
// Test: Verify a credential locally
const creds = await wallet.getCredentials();
if (creds.length > 0) {
  const result = await wallet.verifyLemma(creds[0]);
  console.log('Verify result:', result);
}

// Expected:
{
  valid: true/false,
  reason: "..." (if invalid),
  issuer: "...",
  claims: {...},
  verifiedLocally: true,
  networkCalls: 0
}
```

**Pass Criteria:**
- [ ] `verifiedLocally: true`
- [ ] `networkCalls: 0`
- [ ] Valid credentials return `valid: true`

---

### 2.11 Revoke Credential

```javascript
// Test: Revoke a credential
const creds = await wallet.getCredentials();
if (creds.length > 0) {
  const result = await wallet.revokeCredential(creds[0].id, 'test_revocation');
  console.log('Revoke result:', result);
}

// Expected:
{
  success: true,
  revoked: true,
  serverRevoked: true,
  addedToBloomFilter: true,
  locallyDeleted: true,
  sitesShouldSync: true
}
```

**Pass Criteria:**
- [ ] `revoked: true`
- [ ] `serverRevoked: true`
- [ ] `addedToBloomFilter: true`
- [ ] Credential no longer in `getCredentials()`

---

### 2.12 Sync Revocations

```javascript
// Test: Sync revocation list
const result = await wallet.syncRevocations();
console.log('Sync result:', result);

// Expected:
{
  success: true,
  count: <number>
}
```

**Pass Criteria:**
- [ ] `success: true`
- [ ] `count` reflects server revocation count

---

### 2.13 Check Revocation Status

```javascript
// Test: Check if credential is revoked
const status = await wallet.isRevoked('some_credential_id');
console.log('Revocation status:', status);

// Expected:
{
  revoked: true/false,
  unchecked: false,
  lastSynced: <timestamp>
}
```

**Pass Criteria:**
- [ ] Returns correct revocation status
- [ ] `unchecked: false` after sync

---

### 2.14 Session Heartbeat

```javascript
// Test: Verify heartbeat is running
// After autoAuthenticate() on third-party site:
wallet.startSessionHeartbeat(5000); // 5 second interval for testing

// Lock wallet on lemma.id, then wait...
// Expected: onSessionExpired callback fires within interval
wallet.onSessionExpired = () => {
  console.log('SESSION EXPIRED DETECTED!');
};
```

**Pass Criteria:**
- [ ] Heartbeat detects remote lock
- [ ] `onSessionExpired` callback fires

---

## Part 3: Bridge Tests (Third-Party Site)

### 3.1 Bridge Initialization

```javascript
// Test: Bridge iframe loads
// Check Network tab for: https://lemma.id/wallet/bridge
// Check Console for: "WALLET_BRIDGE_READY"
```

**Pass Criteria:**
- [ ] Bridge iframe created
- [ ] `WALLET_BRIDGE_READY` message received

---

### 3.2 Bridge Session Check

```javascript
// Test: Check session via bridge
const session = await wallet.checkBridgeSession();
console.log('Bridge session:', session);

// Expected:
{
  valid: true/false,
  walletId: "...",
  expiresAt: <timestamp>,
  timeRemaining: <ms>
}
```

**Pass Criteria:**
- [ ] Returns session state from lemma.id
- [ ] Matches actual session state

---

### 3.3 Site Isolation - Store (Security Test)

```javascript
// Test: Try to store credential for different site (should fail)
const maliciousCred = {
  id: 'evil_cred_' + Date.now(),
  issuer: 'did:lemma:attacker',
  claims: {
    siteId: 'different-site.com',  // NOT current site
    permissions: 'admin'
  }
};

const result = await wallet.storeCredential(maliciousCred);
console.log('Malicious store result:', result);

// Expected:
{
  success: false,
  error: "Cannot store credentials for other sites"
}
```

**Pass Criteria:**
- [ ] `success: false`
- [ ] Error mentions "other sites"

---

### 3.4 Site Isolation - Verify (Security Test)

```javascript
// Test: Bridge should reject verifying credentials for other sites
// This requires sending a message directly to bridge

// The bridge VERIFY_CREDENTIAL handler should return error
// if credential.claims.siteId doesn't match requesting origin
```

**Pass Criteria:**
- [ ] Verification blocked for mismatched siteId
- [ ] Console shows: "Blocked verify: ... tried to verify credential for ..."

---

## Part 4: Cross-Site Flow Tests

### 4.1 Flow A: Create Account on lemma.id, Use on Third-Party

```
1. Go to https://lemma.id/wallet/simple
2. Click "Create Passkey" → Creates wallet
3. Note: Session cookie set, IndexedDB populated
4. Go to third-party test site
5. Run: await wallet.autoAuthenticate()
6. Expected: { authenticated: true, walletId: "..." }
```

**Pass Criteria:**
- [ ] Third-party site can authenticate via bridge
- [ ] No passkey prompt on third-party site

---

### 4.2 Flow B: Lock on lemma.id, Detect on Third-Party

```
1. Unlock wallet on lemma.id
2. Go to third-party site, run autoAuthenticate()
3. Verify authenticated
4. Start heartbeat: wallet.startSessionHeartbeat(5000)
5. Go back to lemma.id, click "Lock Wallet"
6. Wait on third-party site
7. Expected: onSessionExpired callback fires
```

**Pass Criteria:**
- [ ] Heartbeat detects lock within interval
- [ ] `onSessionExpired` fires

---

### 4.3 Flow C: Revoke Credential, Verify Rejection

```
1. Issue credential for site A
2. Store credential in wallet
3. Verify credential works: wallet.verifyLemma(cred)
4. Revoke credential: wallet.revokeCredential(cred.id)
5. Sync revocations: wallet.syncRevocations()
6. Verify credential again
7. Expected: { valid: false, reason: "Revoked" }
```

**Pass Criteria:**
- [ ] Credential valid before revocation
- [ ] Credential invalid after revocation + sync

---

### 4.4 Flow D: Popup Unlock on Third-Party

```
1. Ensure wallet is locked (or new browser)
2. Go to third-party test site
3. Run: await wallet.unlockWithPopup()
4. Popup opens to lemma.id/wallet/popup
5. Click "Unlock with Passkey" (or "Create Passkey" if new)
6. Popup closes
7. Expected: { success: true, walletId: "..." }
```

**Pass Criteria:**
- [ ] Popup opens and shows correct UI
- [ ] Parent window receives success
- [ ] Session available on third-party site

---

## Part 5: Error Handling Tests

### 5.1 Network Offline

```javascript
// Test: Operations when offline
// Disable network in DevTools
const result = await wallet.syncRevocations();
console.log('Offline sync:', result);

// Expected:
{
  success: false,
  offline: true,
  cached: true/false
}
```

**Pass Criteria:**
- [ ] Graceful degradation
- [ ] Uses cached data if available

---

### 5.2 Session Expired

```javascript
// Test: Operations with expired session
// Wait for session to expire (or manually clear cookie)
const result = await wallet.storeCredential({...});

// Expected:
{
  success: false,
  error: "Session required..."
}
```

**Pass Criteria:**
- [ ] Clear error message
- [ ] No crash

---

### 5.3 Invalid Credential Format

```javascript
// Test: Verify malformed credential
const result = await wallet.verifyLemma({});
console.log('Invalid cred:', result);

// Expected:
{
  valid: false,
  reason: "..."
}
```

**Pass Criteria:**
- [ ] Returns invalid, doesn't throw

---

## Test Execution Checklist

### API Tests
- [ ] 1.1 Bloom Filter API
- [ ] 1.2 Credential Issuance API
- [ ] 1.3 Revocation API - Site-Specific
- [ ] 1.4 Revocation API - Cross-Site
- [ ] 1.5 Session Sync API
- [ ] 1.6 Revocation List API

### SDK Tests
- [ ] 2.1 Wallet Info
- [ ] 2.2 Register Passkey
- [ ] 2.3 Unlock Wallet
- [ ] 2.4 Lock Wallet
- [ ] 2.5 Auto Authenticate
- [ ] 2.6 Popup Unlock
- [ ] 2.7 Get Auth State
- [ ] 2.8 Store Credential
- [ ] 2.9 Get Credentials
- [ ] 2.10 Verify Credential
- [ ] 2.11 Revoke Credential
- [ ] 2.12 Sync Revocations
- [ ] 2.13 Check Revocation Status
- [ ] 2.14 Session Heartbeat

### Bridge Tests
- [ ] 3.1 Bridge Initialization
- [ ] 3.2 Bridge Session Check
- [ ] 3.3 Site Isolation - Store
- [ ] 3.4 Site Isolation - Verify

### Cross-Site Flow Tests
- [ ] 4.1 Create on lemma.id, Use on Third-Party
- [ ] 4.2 Lock Detection via Heartbeat
- [ ] 4.3 Revocation Propagation
- [ ] 4.4 Popup Unlock Flow

### Error Handling Tests
- [ ] 5.1 Network Offline
- [ ] 5.2 Session Expired
- [ ] 5.3 Invalid Credential Format

---

## Quick Smoke Test (5 minutes)

Run these in order to verify core functionality:

```javascript
// 1. Init
const wallet = new LemmaWallet();
await wallet.init();
console.log('1. Init:', LemmaWallet.VERSION);

// 2. Check state
const info = await wallet.getWalletInfo();
console.log('2. Info:', info);

// 3. Sync revocations
const sync = await wallet.syncRevocations();
console.log('3. Sync:', sync);

// 4. Get credentials
const creds = await wallet.getCredentials();
console.log('4. Creds:', creds.length);

// 5. Auth state
const state = await wallet.getAuthState();
console.log('5. State:', state.suggestedAction);

console.log('✅ Smoke test complete');
```

**All 5 should complete without errors.**
