# Lemma Cross-Site Authentication Test Flows

**SDK Version:** 2.14.0  
**Purpose:** Verify "one passkey per day" works correctly across lemma.id and customer sites.

**Sites:**
- **Lemma Wallet (SDK-Only):** `https://lemma.id/wallet/simple`
- **Lemma Popup Unlock:** `https://lemma.id/wallet/popup`
- **Customer:** `https://surv-report-gen-d8f9f99b4dc3.herokuapp.com`

> **Important:** Passkeys are ONLY created on lemma.id. Customer sites use popup or redirect to unlock.

---

## Architecture Overview

```
Customer Site                    lemma.id
     |                              |
     |-- Opens popup -------------->|
     |                              | User enters passkey
     |                              | Session cookie set
     |<-- postMessage(SUCCESS) -----|
     |                              |
     | Bridge iframe checks cookie  |
     | Sign in proceeds             |
```

**Privacy Model:**
- Stateless JWT session (no database tracking)
- Referrer-Policy: no-referrer (can't see which site)
- No logging of user activity

---

## Pre-Test: Clear All State

Run before starting a new test cycle:

### On lemma.id/wallet/simple
- [ ] Go to `https://lemma.id/wallet/simple`
- [ ] Click "Clear All State" button
- [ ] Wait for "All state cleared" message
- [ ] Hard refresh (Ctrl+Shift+R)

### On Customer Site
```javascript
// Run in console
indexedDB.deleteDatabase('LemmaWallet');
location.reload();
```

---

## Flow 1: First-Time User (Create Passkey on lemma.id)

**Goal:** New user creates passkey on lemma.id, then uses it on customer sites.

### Steps

| # | Action | Expected Result | ✓ |
|---|--------|-----------------|---|
| 1 | Go to `lemma.id/wallet/simple` | Smart Sign In shows "Create Passkey" button | ☐ |
| 2 | Click "Create Passkey" (Smart Sign In) | Google/platform passkey prompt appears | ☐ |
| 3 | Complete passkey creation | Status shows "✅ WALLET UNLOCKED" | ☐ |
| 4 | Smart Sign In button | Shows "✓ Already Signed In" (disabled) | ☐ |
| 5 | Click "Check Cookie" | Shows "COOKIE SESSION ACTIVE" | ☐ |
| 6 | Open new tab → Customer site | Page loads | ☐ |
| 7 | Click sign-in button | **NO popup** - auto-authenticates via bridge | ☐ |
| 8 | Check console | `[Lemma] ✅ Auto-authenticated via bridge session` | ☐ |
| 9 | Verify signed in | Dashboard/app visible | ☐ |

### Pass Criteria
- [ ] Passkey created ONLY on lemma.id (not customer site)
- [ ] Customer site auto-signs-in via bridge
- [ ] Total passkey prompts: **1**

---

## Flow 2: Return User (Popup Unlock from Customer Site)

**Goal:** User with existing passkey signs in from customer site using popup.

### Prerequisites
- Passkey already created on lemma.id (Flow 1)
- Session expired or locked

### Steps

| # | Action | Expected Result | ✓ |
|---|--------|-----------------|---|
| 1 | Clear state on customer site | `indexedDB.deleteDatabase('LemmaWallet')` | ☐ |
| 2 | Lock wallet on lemma.id/wallet/simple | Click "Lock Wallet" | ☐ |
| 3 | Refresh customer site | Shows sign-in button | ☐ |
| 4 | Click sign-in button | **Popup opens** to lemma.id/wallet/popup | ☐ |
| 5 | Popup shows | "Enter your passkey to unlock" | ☐ |
| 6 | Click "Unlock with Passkey" in popup | Biometric prompt appears | ☐ |
| 7 | Complete biometric | Popup shows "✅ Wallet unlocked!" | ☐ |
| 8 | Popup closes automatically | Customer site continues | ☐ |
| 9 | Check console | `[Lemma] ✅ Popup unlock successful` | ☐ |
| 10 | Verify signed in | Dashboard/app visible | ☐ |

### Pass Criteria
- [ ] Popup opens without page navigation
- [ ] User never leaves customer site
- [ ] Passkey used is the ONE from lemma.id
- [ ] Total passkey prompts: **1**

---

## Flow 3: Lock Wallet → Customer Site Signs Out

**Goal:** Locking wallet on lemma.id triggers sign-out on customer site.

### Prerequisites
- Signed in on both sites (complete Flow 1 or 2)

### Steps

| # | Action | Expected Result | ✓ |
|---|--------|-----------------|---|
| 1 | Go to `lemma.id/wallet/simple` | Status shows "WALLET UNLOCKED" | ☐ |
| 2 | Click "Lock Wallet" | Console: `[Lemma] ✅ Server session cleared` | ☐ |
| 3 | Smart Sign In shows | "Unlock Wallet" button (not signed in) | ☐ |
| 4 | Go to customer site tab | Keep it open | ☐ |
| 5 | Wait 30 seconds | Heartbeat detects lock | ☐ |
| 6 | Check console | `[Lemma] ⚠️ Central wallet session expired` | ☐ |
| 7 | If onSessionExpired set | Callback fires, app signs out | ☐ |

### Customer Site Setup for Auto-Signout
```javascript
const wallet = new LemmaWallet();
wallet.onSessionExpired((event) => {
    console.log('Wallet locked - signing out');
    // Your sign-out logic
});
await wallet.init();
```

### Pass Criteria
- [ ] lemma.id shows locked
- [ ] Customer site detects lock within 30 seconds
- [ ] `onSessionExpired` callback fires (if set)

---

## Flow 4: Session Sync (Unlock on Customer → lemma.id Reflects)

**Goal:** Unlocking via customer site popup updates lemma.id wallet page.

### Steps

| # | Action | Expected Result | ✓ |
|---|--------|-----------------|---|
| 1 | Lock wallet everywhere | Both sites show locked | ☐ |
| 2 | Go to customer site | Shows sign-in button | ☐ |
| 3 | Click sign-in → Popup unlock | Complete passkey in popup | ☐ |
| 4 | Verify signed in on customer site | Dashboard visible | ☐ |
| 5 | Open new tab → `lemma.id/wallet/simple` | Page loads | ☐ |
| 6 | Check console | `📥 Server has session but local is locked - syncing...` | ☐ |
| 7 | Smart Sign In shows | "✓ Already Signed In" | ☐ |

### Pass Criteria
- [ ] lemma.id auto-syncs from server cookie
- [ ] No passkey prompt on lemma.id
- [ ] Session created on customer site via popup is recognized

---

## Flow 5: Session Validity Check

**Goal:** SDK correctly reports session state.

### Test Script (run on customer site)
```javascript
(async () => {
    const wallet = new LemmaWallet();
    await wallet.init();
    
    // Check auth state
    const state = await wallet.getAuthState();
    console.log('Auth State:', state);
    // Expected: { isUnlocked: true/false, suggestedAction: '...', suggestedButtonText: '...' }
    
    // Check if session valid
    const isValid = await wallet.isSessionValid();
    console.log('Session Valid:', isValid);
    
    // Try auto-authenticate
    const result = await wallet.autoAuthenticate();
    console.log('Auto-auth:', result);
})();
```

### Expected States

| Scenario | getAuthState() | autoAuthenticate() |
|----------|----------------|-------------------|
| Unlocked | `{isUnlocked: true, suggestedAction: 'auto_sign_in'}` | `{authenticated: true, walletSecret: '...'}` |
| Locked (3rd party) | `{isUnlocked: false, suggestedAction: 'redirect_to_lemma'}` | `{authenticated: false, needsPasskey: true}` |
| Locked (lemma.id) | `{isUnlocked: false, suggestedAction: 'unlock'}` | `{authenticated: false}` |

---

## Flow 6: Heartbeat & Real-Time Lock Detection

**Goal:** Verify heartbeat detects remote wallet lock.

### Steps

| # | Action | Expected Result | ✓ |
|---|--------|-----------------|---|
| 1 | Sign in on customer site | Authenticated | ☐ |
| 2 | Check console | `[Lemma] 🔄 Auto-starting session heartbeat (checks every 30s)` | ☐ |
| 3 | Open lemma.id/wallet/simple in another tab | Shows unlocked | ☐ |
| 4 | Click "Lock Wallet" | Wallet locks | ☐ |
| 5 | Return to customer site | Wait... | ☐ |
| 6 | Within 30 seconds, check console | `⚠️ Server session invalid - wallet locked remotely!` | ☐ |
| 7 | If callback set | `onSessionExpired` fires | ☐ |

### Pass Criteria
- [ ] Heartbeat runs automatically (no manual setup)
- [ ] Lock detected within 30 seconds
- [ ] Customer app can react to lock event

---

## Quick Test URLs

| Page | URL | Purpose |
|------|-----|---------|
| SDK-Only Wallet | `https://lemma.id/wallet/simple` | Clean testing with Smart Sign In |
| Popup Unlock | `https://lemma.id/wallet/popup` | Popup that opens from customer sites |
| Customer Site | `https://surv-report-gen-d8f9f99b4dc3.herokuapp.com` | Third-party test site |

---

## Quick Debug Commands

### Check Auth State (customer site)
```javascript
(async () => {
    const wallet = new LemmaWallet();
    await wallet.init();
    console.log('Auth state:', await wallet.getAuthState());
    console.log('Session valid:', await wallet.isSessionValid());
})();
```

### Force Bridge Check (customer site)
```javascript
(async () => {
    const wallet = new LemmaWallet();
    await wallet.init();
    const session = await wallet.checkBridgeSession();
    console.log('Bridge session:', session);
})();
```

### Check SDK Version
```javascript
console.log('SDK Version:', LemmaWallet.VERSION);
// Should be 2.14.0 or higher
```

### Manual Popup Test (customer site)
```javascript
(async () => {
    const wallet = new LemmaWallet();
    await wallet.init();
    const result = await wallet.unlockWithPopup();
    console.log('Popup result:', result);
})();
```

### Clear All State (lemma.id)
```javascript
(async () => {
    indexedDB.deleteDatabase('LemmaWallet');
    document.cookie = 'lemma_wallet_session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    document.cookie = 'lemma_wallet_csrf=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    const regs = await navigator.serviceWorker.getRegistrations();
    for (const reg of regs) await reg.unregister();
    console.log('✅ All state cleared - refresh page');
    location.reload();
})();
```

---

## SDK Methods Reference

| Method | Purpose | Returns |
|--------|---------|---------|
| `autoAuthenticate()` | Auto sign-in if bridge session valid | `{authenticated, walletSecret, needsPasskey}` |
| `getAuthState()` | Get current state for UI | `{isUnlocked, suggestedAction, suggestedButtonText}` |
| `registerPasskey()` | Create passkey (lemma.id) or use popup (3rd party) | `{success, walletSecret}` |
| `unlockWithPopup()` | Open popup for unlock | `{success, walletId}` |
| `isSessionValid()` | Verify session with bridge | `boolean` |
| `onSessionExpired(cb)` | Set callback for remote lock | N/A |
| `checkBridgeSession()` | Raw bridge session check | `{valid, expiresAt, ...}` |
| `lock()` | Lock wallet & clear server cookie | N/A |

---

## Common Issues & Fixes

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Popup blocked | Browser popup blocker | Allow popups for customer site |
| `needsUnlock: true` returned | No bridge session | Open popup or redirect to lemma.id |
| Bridge says `session: none` | Cookie cleared or expired | Re-unlock on lemma.id |
| Multiple passkey prompts | Old SDK creating local passkeys | Update to SDK 2.14.0+ |
| Heartbeat not detecting lock | Not using autoAuthenticate | Call `autoAuthenticate()` to start heartbeat |
| lemma.id shows locked after popup | Server sync not running | Hard refresh lemma.id/wallet/simple |

---

## Test Results Log

| Date | Flow | Result | Notes |
|------|------|--------|-------|
| | Flow 1 (First-Time) | ☐ Pass ☐ Fail | |
| | Flow 2 (Popup Unlock) | ☐ Pass ☐ Fail | |
| | Flow 3 (Lock → Sign Out) | ☐ Pass ☐ Fail | |
| | Flow 4 (Session Sync) | ☐ Pass ☐ Fail | |
| | Flow 5 (Validity Check) | ☐ Pass ☐ Fail | |
| | Flow 6 (Heartbeat) | ☐ Pass ☐ Fail | |

---

## Customer Site Integration Checklist

```javascript
// Minimal integration
const wallet = new LemmaWallet();

// Optional: Handle remote lock
wallet.onSessionExpired(() => {
    signOutUser();
});

// Sign in flow
async function signIn() {
    await wallet.init();
    
    const result = await wallet.autoAuthenticate();
    
    if (result.authenticated) {
        // Already authenticated via bridge
        await signInWithWalletSecret(result.walletSecret);
    } else {
        // Will open popup automatically
        const regResult = await wallet.registerPasskey();
        if (regResult.success) {
            await signInWithWalletSecret(regResult.walletSecret);
        }
    }
}
```
