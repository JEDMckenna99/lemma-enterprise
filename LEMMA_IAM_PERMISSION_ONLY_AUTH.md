# Lemma IAM Permission-Only Authentication

**Version**: v890  
**Date**: October 19, 2025  
**Status**: Production Ready

---

## Overview

Lemma.id now uses **permission-only authentication** for the IAM system. Users do NOT need a Proof of Humanity (PoH) lemma to access the site - only a valid permission lemma for `lemma.id`.

This allows you to focus on the **Lemma IAM** system before rolling out the Federated Identity Network with Bot Shield later.

---

## Authentication Architecture

### **Current Flow (Permission-Only)**

```
1. User visits lemma.id/dashboard
2. Client checks wallet for permission lemma (siteId: 'lemma.id')
3. If valid permission found → Access granted
4. If no permission → Redirect to /login
5. After login → Issue permission lemma → Access granted
```

### **What's NOT Required**
- ❌ Proof of Humanity (PoH) lemma
- ❌ Stripe Identity verification
- ❌ Federated network credentials
- ❌ Bot Shield protection

### **What IS Required**
- ✅ Valid permission lemma for `lemma.id`
- ✅ Permission ID: `customer_access` OR `admin_access`
- ✅ Valid signature from IAM issuer
- ✅ Not expired
- ✅ Not revoked

---

## Permission Types

### **Customer Access**
- **Permission ID**: `customer_access`
- **Scope**: `['profile:read', 'profile:write', 'billing:read', 'usage:read']`
- **Pages**: `/dashboard`, customer pages
- **Granted**: During customer registration/login

### **Admin Access**
- **Permission ID**: `admin_access`
- **Scope**: `['users:*', 'sites:*', 'permissions:*', 'billing:*', 'analytics:*']`
- **Pages**: `/admin`, `/admin/bootstrap`, admin tools
- **Granted**: Via admin bootstrap or admin login

---

## Client-Side Permission Checks

### **Dashboard Example** (`templates/modern/dashboard.html`)

```javascript
// Check for any valid permission lemma for lemma.id
const permissionLemmas = await walletInstance.getCredentials('permission');

const hasLemmaAccess = permissionLemmas.some(lemma => {
    const isLemmaId = lemma.claims?.siteId === 'lemma.id';
    const hasValidPermission = lemma.claims?.permissionId === 'customer_access' || 
                             lemma.claims?.permissionId === 'admin_access';
    
    return isLemmaId && hasValidPermission;
});

if (hasLemmaAccess) {
    // Grant access
    loadDashboard();
} else {
    // Deny access → redirect to login
    showAccessDenied();
}
```

---

## Server-Side Components

### **New Decorator** (`auth/decorators.py`)

```python
@require_permission_lemma('lemma.id', ['customer_access', 'admin_access'])
def protected_route():
    return render_template('protected.html')
```

**Checks**:
- `session['permission_verified']` = True
- `session['permission_site']` = 'lemma.id'
- `session['permission_id']` in required_permissions

### **Login Endpoint** (`api/lemma_auth_endpoint.py`)

Sets permission session variables:
```python
session['permission_verified'] = True
session['permission_site'] = 'lemma.id'
session['permission_id'] = f'{user_role}_access'
session['permission_email'] = user_email
```

---

## Credential Revocation

### **Complete Revocation Flow** (v886-v890)

When a permission lemma is revoked:

1. **Client-Side Deletion**:
   - ✅ Removed from memory cache
   - ✅ Removed from encrypted wallet (single global instance)
   - ✅ Removed from IndexedDB
   - ✅ Removed from localStorage (plaintext)
   - ✅ Direct localStorage manipulation as failsafe

2. **Server-Side Registry Update**:
   - ✅ Added to `RevocationList` table in PostgreSQL
   - ✅ Stored with credential ID, site domain, timestamp, reason
   - ✅ API returns confirmation of both wallet deletion and registry update

3. **Verification**:
   ```
   Console output on revocation:
   🗑️ Starting revocation of cred_xxx...
     Removal result: SUCCESS
     Found credential in encrypted storage, removing...
     ✅ Directly removed from encrypted localStorage
     ✅ Removed from plaintext localStorage
     Verification: Still in encrypted localStorage: false
     Encrypted storage now has 8 credentials
   ```

---

## Key Differences from Federated Network

| Feature | IAM (Current) | Fed Network (Future) |
|---------|---------------|----------------------|
| **Authentication** | Permission lemma only | PoH + Bot Shield |
| **Credential Type** | Site-specific | Cross-site portable |
| **Bot Protection** | Not required | Required (Shield) |
| **Scope** | lemma.id only | All network sites |
| **Verification** | Ed25519 signature | Ed25519 + OPRF + Bloom |
| **Storage** | Encrypted wallet | Encrypted wallet |

---

## API Endpoints

### **Sign In with Lemma**
```
POST /api/auth/lemma-signin
{
  "user_email": "user@example.com",
  "user_role": "admin",
  "permission_credentials": [...],
  "auth_method": "lemma_wallet"
}
```

### **Revoke Permission Lemma**
```
POST /api/wallet/revoke
{
  "credential_id": "cred_xxx",
  "credential_type": "permission",
  "site_domain": "lemma.id",
  "reason": "user_requested_removal"
}
```

---

## Testing the System

### **1. Issue Admin Permission** 
```
https://lemma.id/admin/bootstrap
API Key: e663a17fe6a8b1501c768ad88c9ceb072d2ef6eecaa51d84b38a89edfe07d5db
```

### **2. View Wallet**
```
https://lemma.id/wallet
Should show: 9 permission lemmas for lemma.id
```

### **3. Access Dashboard**
```
https://lemma.id/dashboard
Should work with permission lemma only (no PoH required)
```

### **4. Revoke Credential**
```
1. Go to /wallet
2. Click "Revoke" on a permission lemma
3. Verify in console: credential removed from all storage
4. Refresh page
5. Verify: credential does NOT reappear
```

---

## Deployment History

- **v886**: Database revocation registry integration
- **v887**: Fixed encrypted wallet instance reference
- **v888**: Added diagnostic logging for revocation
- **v889**: Global singleton encrypted wallet + direct localStorage cleanup
- **v890**: Permission-only authentication (no PoH required)

---

## Next Steps

When ready to roll out Federated Identity Network:

1. **Add Bot Shield** protection to pages
2. **Require PoH lemmas** for network-wide identity
3. **Enable Stripe Identity** verification flow
4. **Activate cross-site** credential portability
5. **Integrate with** other sites in federation

For now: **IAM system is fully functional with permission-only access control.**

---

## Technical Notes

### **Single Wallet Instance**
- Main wallet: `window.lemmaWallet` (singleton)
- Encrypted wallet: `window.encryptedWallet` (singleton)
- Both stored globally to prevent multiple instances

### **Storage Keys**
- Encrypted: `localStorage['lemma_credentials_encrypted']`
- Plaintext: `localStorage['lemma_credentials']`
- Session: `session['permission_verified']`

### **Database Tables**
- Permissions: `SitePermissionGrant`
- Revocations: `RevocationList`
- Customers: `Customer`

---

**Status**: Production ready for IAM-only authentication at lemma.id



