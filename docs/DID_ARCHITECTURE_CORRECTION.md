# 🆔 Lemma DID Architecture - Correct Implementation

## 🎯 **Current Issue: Mixed DID Structure**

You're absolutely right! The current implementation has mixed up the DID structure. We need to properly separate:

1. **Federated Identity Network DID** - ONE shared DID registry for all sites
2. **Site-Specific IAM DIDs** - SEPARATE DID registry for each site using Lemma IAM

## 🏗️ **Correct DID Architecture**

### **1. Federated Identity Network (Global)**
```
DID Registry: did:lemma:federated:network
Purpose: Cross-site bot protection
Distribution: TO ALL SITES
Revocation Registry: GLOBAL (shared across all sites)

Example DIDs:
- did:lemma:federated:user:alice_verified_human
- did:lemma:federated:user:bob_verified_human
- did:lemma:federated:user:charlie_verified_human

Revocation Registry:
- Global bloom filter with all revoked federated identities
- Shared OPRF evaluations for privacy-preserving revocation
- Distributed to ALL sites for bot protection
```

### **2. Site-Specific IAM (Per Site)**
```
DID Registry: did:lemma:site:{site_id}
Purpose: Site access control and permissions  
Distribution: ONLY to that specific site
Revocation Registry: SITE-SPECIFIC (isolated per site)

Example DIDs for site "ecommerce_123":
- did:lemma:site:ecommerce_123:user:alice_customer
- did:lemma:site:ecommerce_123:user:bob_admin
- did:lemma:site:ecommerce_123:user:charlie_moderator

Revocation Registry for "ecommerce_123":
- Site-specific bloom filter with only ecommerce_123 revocations
- Site-specific OPRF evaluations
- NOT shared with other sites
```

## 🔧 **Implementation Corrections Needed**

### **Current Problems:**
1. **Mixed DID namespaces**: Using `did:lemma:user:` for both federated and site-specific
2. **Shared revocation registry**: Site permissions using global revocation lists
3. **Cross-contamination**: Site-specific data leaking into federated network

### **Correct Implementation:**

#### **1. Federated Identity DIDs**
```python
# For users verified through verification card or bot shield
def create_federated_identity_did(user_email):
    """Create federated identity DID for cross-site bot protection"""
    user_id = user_email.replace('@', '_at_').replace('.', '_')
    return f"did:lemma:federated:user:{user_id}"

# Example: alice@example.com → did:lemma:federated:user:alice_at_example_com
```

#### **2. Site-Specific Permission DIDs**
```python
# For users with site-specific permissions
def create_site_permission_did(user_email, site_id):
    """Create site-specific DID for site access control"""
    user_id = user_email.replace('@', '_at_').replace('.', '_')
    return f"did:lemma:site:{site_id}:user:{user_id}"

# Example: alice@example.com on ecommerce_123 
# → did:lemma:site:ecommerce_123:user:alice_at_example_com
```

#### **3. Separate Revocation Registries**
```python
# Federated identity revocations (global)
federated_revocation_registry = {
    'registry_type': 'federated_identity',
    'scope': 'global_network',
    'revoked_dids': {
        'did:lemma:federated:user:bad_actor': {
            'revoked_at': timestamp,
            'reason': 'bot_detected',
            'network_wide': True
        }
    }
}

# Site-specific revocations (isolated)
site_revocation_registry = {
    'registry_type': 'site_specific_iam',
    'site_id': 'ecommerce_123',
    'scope': 'site_only',
    'revoked_dids': {
        'did:lemma:site:ecommerce_123:user:banned_user': {
            'revoked_at': timestamp,
            'reason': 'terms_violation',
            'site_only': True
        }
    }
}
```

## 🚀 **Implementation Plan**

### **Phase 1: Fix DID Namespace Separation**

#### **1. Update Federated Identity Creation**
```python
# api/federated_identity_manager.py
def create_federated_identity_lemma(user_email, verification_source):
    """Create federated identity lemma with correct DID namespace"""
    
    federated_did = f"did:lemma:federated:user:{user_email.replace('@', '_at_').replace('.', '_')}"
    
    lemma = {
        'id': f"fed_identity_{secrets.token_hex(16)}",
        'issuer': f'did:lemma:federated:network',
        'subject': federated_did,
        'packageType': 'identity',
        'claims': {
            'packageType': 'identity',
            'isHuman': True,
            'verificationSource': verification_source,
            'networkScope': 'federated',
            'crossSiteValid': True,
            'siteSpecific': False
        }
    }
    
    return lemma
```

#### **2. Update Site-Specific Permission Creation**
```python
# api/site_permission_manager.py  
def create_site_permission_lemma(user_email, site_id, permission_type):
    """Create site-specific permission lemma with correct DID namespace"""
    
    site_did = f"did:lemma:site:{site_id}:user:{user_email.replace('@', '_at_').replace('.', '_')}"
    
    lemma = {
        'id': f"site_perm_{site_id}_{secrets.token_hex(16)}",
        'issuer': f'did:lemma:site:{site_id}:authority',
        'subject': site_did,
        'packageType': 'permission',
        'claims': {
            'packageType': 'permission',
            'siteId': site_id,
            'permissionId': permission_type,
            'networkScope': 'site_specific',
            'crossSiteValid': False,
            'siteSpecific': True
        }
    }
    
    return lemma
```

#### **3. Separate Trust Bundle Distribution**
```python
# Federated identity trust bundle (to ALL sites)
@app.route('/api/network/federated-trust-bundle')
def get_federated_trust_bundle():
    """Get federated identity DIDs for bot protection (all sites)"""
    return {
        'bundle_type': 'federated_identity',
        'did_registry': get_all_verified_humans_dids(),
        'revocation_registry': get_global_revocation_registry(),
        'distribution_scope': 'all_network_sites'
    }

# Site-specific trust bundle (to specific site only)  
@app.route('/api/sites/<site_id>/iam-trust-bundle')
def get_site_iam_trust_bundle(site_id):
    """Get site-specific permission DIDs (this site only)"""
    return {
        'bundle_type': 'site_specific_iam',
        'site_id': site_id,
        'did_registry': get_site_permission_dids(site_id),
        'revocation_registry': get_site_revocation_registry(site_id),
        'distribution_scope': 'site_only'
    }
```

## 📋 **Migration Steps**

### **Step 1: Identify Current DID Conflicts**
```sql
-- Find mixed DIDs that need separation
SELECT 
    lemma_type,
    user_did,
    site_id,
    lemma_data->>'networkScope' as network_scope
FROM user_lemmas 
WHERE 
    (lemma_type = 'identity' AND site_id IS NOT NULL) OR  -- Identity shouldn't have site_id
    (lemma_type = 'permission' AND user_did LIKE 'did:lemma:federated:%')  -- Permission shouldn't use federated DID
```

### **Step 2: Create Correct DID Managers**
```python
class FederatedIdentityDIDManager:
    """Manages federated identity DIDs (global network)"""
    
    def create_did(self, user_email):
        return f"did:lemma:federated:user:{self._normalize_email(user_email)}"
    
    def get_revocation_registry(self):
        """Get global revocation registry for all sites"""
        return self.global_revocation_registry

class SiteSpecificDIDManager:
    """Manages site-specific permission DIDs (isolated per site)"""
    
    def create_did(self, user_email, site_id):
        return f"did:lemma:site:{site_id}:user:{self._normalize_email(user_email)}"
    
    def get_site_revocation_registry(self, site_id):
        """Get site-specific revocation registry (not shared)"""
        return self.site_revocation_registries.get(site_id, {})
```

### **Step 3: Update Trust Bundle Distribution**
```python
# Separate the trust bundle endpoints
@app.route('/api/network/global-trust-bundle')  # For federated identity
@app.route('/api/sites/<site_id>/site-trust-bundle')  # For site permissions
```

## ✅ **Benefits of Correct Architecture**

### **For Federated Identity:**
- ✅ **Clear namespace**: `did:lemma:federated:*` 
- ✅ **Global scope**: Available to all sites for bot protection
- ✅ **Single revocation registry**: Consistent across network
- ✅ **Network effects**: Cross-site human verification

### **For Site Permissions:**
- ✅ **Clear namespace**: `did:lemma:site:{site_id}:*`
- ✅ **Site isolation**: Each site has its own DID space
- ✅ **Private revocation**: Site manages its own revocations
- ✅ **No data leakage**: Site permissions don't leak to other sites

This separation ensures **proper privacy isolation** while maintaining **network effects** for bot protection! 🎯
