# 🏗️ Lemma Onboarding Architecture - Correct Implementation

## 🎯 **Two Distinct Systems with Different Onboarding Paths**

### **1. Federated Identity Network (PoH Lemmas)**
**Purpose**: Cross-site bot protection with network effects  
**Onboarding**: **VERIFICATION CARD ONLY** (accurate proof of humanness)  
**Trust Bundle Distribution**: **TO ALL SITES** (for network-wide bot protection)

### **2. Site-Specific Permission Lemmas (IAM)**  
**Purpose**: Site access control and permissions  
**Onboarding**: **EMAIL CONFIRMATION** after site signup  
**Trust Bundle Scope**: **SITE-SPECIFIC ONLY** (between site and their users)

---

## 🔐 **Federated Identity Network Architecture**

### **Onboarding Flow (Verification Card Only)**
```
User Journey:
1. Visit https://lemma.id/verify
2. Complete verification card process
   - Stripe Identity verification
   - Cryptographic proof creation
   - Accurate proof of humanness
3. PoH lemma stored in federated wallet
4. Available for bot protection across ALL network sites

Technical Implementation:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Verification    │    │ Lemma Platform  │    │ All Network     │
│ Card            │ ──>│ (lemma.id)      │ ──>│ Sites           │
│ (ONLY source)   │    │ Creates PoH     │    │ Get trust       │
│                 │    │ Lemma           │    │ bundles         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### **Trust Bundle Distribution to Sites**
```javascript
// Sites receive federated identity trust bundles for bot protection
GET /api/sites/{site_id}/trust-bundle

Response:
{
  "trust_bundle": {
    "bundle_type": "federated_identity_bot_protection",
    "verified_human_dids": {
      "did:lemma:user:alice": { "verified_human": true, "trust_score": 1.0 },
      "did:lemma:user:bob": { "verified_human": true, "trust_score": 1.0 }
    },
    "revocation_lists": { /* Network-wide revocations */ },
    "network_scope": true,
    "usage": "bot_protection_across_network"
  }
}
```

### **Site Bot Protection Usage**
```javascript
// Sites use federated trust bundle for bot protection
const response = await fetch('/api/sites/mysite/verify-human', {
    method: 'POST',
    body: JSON.stringify({
        user_did: 'did:lemma:user:alice'
    })
});

// Result: { verified_human: true, network_verified: true }
```

---

## 🔑 **Site-Specific Permission Lemmas (IAM) Architecture**

### **Onboarding Flow (Email Confirmation After Site Signup)**
```
User Journey:
1. User signs up for specific site (e.g., ecommerce.com)
2. Site calls: POST /api/sites/{site_id}/signup
3. Lemma sends email confirmation to user
4. User confirms email
5. Permission lemma created for THAT SITE ONLY
6. Stored in user's wallet as site-specific permission

Technical Implementation:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Site Signup     │    │ Email           │    │ Site-Specific   │
│ (ecommerce.com) │ ──>│ Confirmation    │ ──>│ Permission      │
│                 │    │                 │    │ (NOT network)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### **Site-Specific Trust Bundle (Internal Only)**
```javascript
// Sites verify their own users' permissions
POST /api/sites/{site_id}/iam/verify-permission

Request:
{
  "credential": { /* User's site-specific permission lemma */ },
  "resource": "/admin/users",
  "action": "read"
}

Response:
{
  "verified": true,
  "permission_id": "admin_access", 
  "site_specific": true,
  "network_shared": false,
  "verification_time_us": 2.38
}
```

---

## ✅ **Current Implementation Status**

### **✅ What's Correctly Implemented:**

#### **1. Email Automation**
- ✅ **Site signup triggers email**: `/api/sites/<site_id>/signup`
- ✅ **Email confirmation creates permission**: Site-specific only
- ✅ **Reliable email delivery**: Mailgun HTTP API
- ✅ **Server restart recovery**: Tokens survive deployments

#### **2. Wallet Storage**
- ✅ **Federated identity lemmas**: Stored with network sync
- ✅ **Permission lemmas**: Stored as site-specific
- ✅ **Cross-browser sync**: Unified wallet management
- ✅ **Proper isolation**: Different storage for different types

### **🔧 What Needs Verification/Enhancement:**

#### **1. Federated Identity Onboarding Enforcement**
```javascript
// Ensure ONLY verification card creates federated identity
const validation = await fetch('/api/federated/validate-identity-source', {
    method: 'POST',
    body: JSON.stringify({ credential: userIdentityLemma })
});

// Should reject if not from verification card
```

#### **2. Trust Bundle Distribution to Sites**
```javascript
// All sites should get federated identity trust bundles
const trustBundle = await fetch('/api/sites/mysite/trust-bundle');

// Contains verified humans for bot protection
// Does NOT contain other sites' permission data
```

#### **3. Permission Lemma Isolation**
```javascript
// Permission verification stays between site and user
const permissionCheck = await fetch('/api/sites/mysite/iam/verify-permission', {
    method: 'POST',
    body: JSON.stringify({
        credential: userSitePermission,
        resource: '/admin',
        action: 'read'
    })
});

// Does NOT share permission data with other sites
```

## 🚀 **API Endpoints Summary**

### **Federated Identity Network (Cross-Site Bot Protection)**
- `GET /api/sites/{site_id}/trust-bundle` - Get federated identity trust bundle
- `POST /api/sites/{site_id}/verify-human` - Check if user is verified human
- `POST /api/federated/validate-identity-source` - Validate verification card origin
- `GET /api/federated/onboarding-stats` - Monitor onboarding compliance

### **Site-Specific IAM (Isolated Permissions)**
- `POST /api/sites/{site_id}/signup` - User signup (triggers email)
- `POST /api/sites/{site_id}/iam/verify-permission` - Verify site permission
- `GET /api/sites/{site_id}/iam/user-permissions` - Get site's user permissions
- `POST /api/permissions/request-via-email` - Direct permission request

## 🎯 **Architecture Benefits**

### **For Federated Identity (PoH):**
- ✅ **Accurate verification**: Verification card ensures real proof of humanness
- ✅ **Network effects**: Verified humans protect all sites from bots
- ✅ **Cross-site benefits**: Verify once, protected everywhere
- ✅ **Centralized trust**: Single source of truth for humanity verification

### **For Site Permissions (IAM):**
- ✅ **Privacy isolation**: Site permissions don't leak to other sites
- ✅ **Simple onboarding**: Email confirmation (no complex verification needed)
- ✅ **Site control**: Sites manage their own user permissions
- ✅ **Scalable**: Each site handles only their own permission data

This architecture provides **both network effects AND privacy isolation** - the best of both worlds! 🎉
