# Edge Case Fixes - Implementation Tracker

**Created**: 2026-01-01
**Status**: In Progress

---

## Progress Summary

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1.1 | Create credential utils | ✅ Done | `static/js/lemma-credential-utils.js` |
| 1.2 | Update layout.html | ✅ Done | Uses utils, handles multiple formats |
| 2.1 | Fix admin permission security | ✅ Done | Removed .includes('admin') |
| 3.1 | Handle multiple credentials | ✅ Done | selectBestCredentials() |
| 4.1 | Replace silent failures | ✅ Done | console.warn + debug mode |
| 4.2 | Add debug mode | ✅ Done | localStorage lemma_debug_auth |
| 5.1 | API validation middleware | ⏳ Pending | |
| 5.2 | Apply to endpoints | ⏳ Pending | |
| 6.1 | Offline resilience | ⏳ Pending | |
| 7.1 | Test credentials | ⏳ Pending | |

---

## Phase 1: Credential Format Normalization (Critical)

### 1.1 Create a unified credential helper function
**File**: `static/js/lemma-credential-utils.js` (new)
**Status**: ⏳ Pending

```javascript
// Standardize claim extraction across all credential formats
function normalizeCredentialClaims(credential) {
    const claims = credential.claims || credential.credentialSubject || {};
    return {
        siteId: claims.siteId || claims.site || claims.site_id || claims.siteDomain || '',
        permissionId: claims.permissionId || claims.permission_level || claims.type || '',
        permissions: claims.permissions || '',
        email: claims.email || '',
        accountType: claims.accountType || claims.account_type || 'customer',
        expiresAt: getExpirationTimestamp(credential),
        isExpired: isCredentialExpired(credential),
        isAdmin: checkAdminPermission(claims)
    };
}

function getExpirationTimestamp(credential) {
    const raw = credential.expiresAt || credential.expirationDate || 
                credential.expires_at || credential.claims?.expiresAt;
    if (!raw) return null;
    if (typeof raw === 'string') return new Date(raw).getTime();
    // Handle seconds vs milliseconds (if < year 2100 in seconds, convert)
    return raw < 4102444800 ? raw * 1000 : raw;
}

function isCredentialExpired(credential) {
    const expiry = getExpirationTimestamp(credential);
    return expiry ? expiry < Date.now() : false;
}

function checkAdminPermission(claims) {
    const permId = (claims.permissionId || claims.permission_level || '').toLowerCase();
    const ADMIN_PERMISSIONS = ['admin_access', 'super_admin', 'admin', 'superadmin', 'site_admin'];
    return ADMIN_PERMISSIONS.includes(permId) || claims.accountType === 'admin';
}
```

### 1.2 Update layout.html to use normalized claims
**File**: `templates/modern/layout.html`
**Status**: ⏳ Pending

**Problem**: Currently checks `claims.permissionId` but user's credential has `claims.permissions` and `claims.type` instead.

---

## Phase 2: Fix Admin Permission Security

### 2.1 Remove loose `.includes('admin')` check
**Status**: ⏳ Pending

**Files to update**:
- `templates/modern/layout.html` (line ~385)
- `templates/developer/platform.html` (line ~1248)
- `templates/admin/admin_dashboard.html`
- `templates/admin/permissions.html`
- `templates/admin/permission_configuration.html`

**Security Risk**: A credential with `permissionId: "not-admin-really"` passes `.includes('admin')` check!

**Change**:
```javascript
// REMOVE THIS (vulnerable):
(claims.permissionId && claims.permissionId.toLowerCase().includes('admin'))

// KEEP ONLY EXPLICIT CHECKS:
const ADMIN_PERMISSIONS = ['admin_access', 'super_admin', 'admin', 'superadmin', 'site_admin'];
const isAdmin = ADMIN_PERMISSIONS.includes(permissionId) || claims.accountType === 'admin';
```

---

## Phase 3: Handle Multiple Credentials Properly

### 3.1 Select best valid credential
**File**: `templates/modern/layout.html`
**Status**: ⏳ Pending

**Problem**: Currently takes first credential which might be expired while second is valid.

```javascript
// AFTER (select best valid credential):
const validCreds = lemmaPermissions
    .filter(c => !isCredentialExpired(c))
    .sort((a, b) => {
        const aExp = getExpirationTimestamp(a) || Infinity;
        const bExp = getExpirationTimestamp(b) || Infinity;
        return bExp - aExp;
    });

if (validCreds.length === 0) {
    console.log('⚠️ All credentials expired');
    return;
}
const cred = validCreds[0];
```

---

## Phase 4: Improve Error Handling

### 4.1 Replace silent failures with logging
**Status**: ⏳ Pending

**Files to update**:
- `templates/modern/layout.html` (line ~405)
- `static/js/lemma-wallet.js` (various catch blocks)

### 4.2 Add debug mode for auth issues
**Status**: ⏳ Pending

```javascript
// Enable with: localStorage.setItem('lemma_debug_auth', 'true')
const DEBUG_AUTH = localStorage.getItem('lemma_debug_auth') === 'true';
```

---

## Phase 5: API Input Validation

### 5.1 Create validation middleware
**File**: `api/validation.py` (new)
**Status**: ⏳ Pending

### 5.2 Apply to critical endpoints
**Status**: ⏳ Pending

**Problem**: Many endpoints default `site_id` to `'lemma.id'` which can cause permission confusion.

---

## Phase 6: Offline Resilience

### 6.1 Add offline verification fallback
**Status**: ⏳ Pending

**Problem**: If network fails during `verifyCredential()`, user is locked out even with valid local credential.

---

## Phase 7: Testing & Validation

### 7.1 Create test credentials for edge cases
**Status**: ⏳ Pending

---

## Test Results Log

| Date | Test | Result | Notes |
|------|------|--------|-------|
| 2026-01-01 | Deploy credential utils | ✅ | Deployed to Heroku |
| 2026-01-01 | LemmaCredentialUtils loaded | ✅ | Verified via browser eval |
| 2026-01-01 | layout.html uses utils | ✅ | Falls back if utils not ready |
| 2026-01-01 | Debug mode works | ✅ | localStorage lemma_debug_auth |
| 2026-01-01 | End-user test | ⏳ | User needs to test with their wallet |

**To test in your browser:**
1. Open browser console
2. Run: `localStorage.setItem('lemma_debug_auth', 'true')`
3. Refresh the page
4. Check console for `🔐 Auth:` logs

---

## Deployment Log

| Date | Changes Deployed | Verified |
|------|------------------|----------|
| 2026-01-01 | Phase 1-4 fixes | ✅ Utils deployed |
