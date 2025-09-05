# 🔐 Lemma Trust Bundle & Revocation Architecture

## 🎯 **Recommended Architecture: SDK-Embedded Approach**

### **Core Principle**: 
Sites using Lemma IAM should **never need to manage trust bundles directly**. Your SDK/API handles all cryptographic complexity internally.

## 🏗️ **Architecture Overview**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Customer      │    │   Lemma IAM     │    │   Federated     │
│   Site          │    │   Platform      │    │   Identity      │
│   (ecommerce.com)│    │   (lemma.id)    │    │   Network       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │ 1. Verify User        │                       │
         │ ─────────────────────>│                       │
         │                       │ 2. Check Trust Bundle │
         │                       │ ─────────────────────>│
         │                       │ 3. Return Verification│
         │                       │<──────────────────────│
         │ 4. Allow/Deny Access  │                       │
         │<──────────────────────│                       │
```

## 🔧 **Implementation Strategy**

### **1. For Federated Identity Network (PoH Lemmas)**
**Current**: ✅ **Perfect** - Keep centralized trust bundle distribution
```javascript
// Federated wallet syncs with central registry
networkConfig: {
    registryUrl: 'https://lemma.id/api/network/sync',
    authKey: 'lemma_network_federated_sync_2024',
    syncInterval: 5 * 60 * 1000 // 5 minutes
}
```

**Why this works**: 
- ✅ Network effects require central coordination
- ✅ Users benefit from cross-site verification
- ✅ Trust needs to be established between sites

### **2. For Site-Specific Permission Lemmas** 
**Recommended**: 🎯 **SDK-Embedded Approach**

#### **Customer Site Integration (Ultra-Simple)**
```javascript
// Site just calls your API - no trust bundle management
const lemmaIAM = new LemmaIAM({
    apiKey: 'site_customer_api_key_123',
    siteId: 'ecommerce_site_456'
});

// Verify user permission (2.38µs)
const result = await lemmaIAM.verifyPermission({
    userCredential: userLemma,
    resource: '/admin/users',
    action: 'read'
});

// Site doesn't need to know about:
// - Trust bundles
// - Revocation lists  
// - DID resolution
// - OPRF evaluations
// - Bloom filters
```

#### **Your API Handles Everything Internally**
```python
# api/iam_verification_endpoint.py
@app.route('/api/v1/sites/<site_id>/verify-permission', methods=['POST'])
def verify_site_permission(site_id):
    """
    Verify user permission for site (handles all trust bundle complexity)
    """
    # 1. Get user credential from request
    user_credential = request.json.get('user_credential')
    
    # 2. Load trust bundle for this site (cached internally)
    trust_bundle = get_cached_trust_bundle(site_id)
    
    # 3. Check revocation lists (your responsibility)
    if is_revoked(user_credential, trust_bundle):
        return {'verified': False, 'reason': 'revoked'}
    
    # 4. Verify permission (your crypto engine)
    verification = verify_lemma_credential(user_credential, trust_bundle)
    
    # 5. Return simple result to site
    return {
        'verified': verification.success,
        'permission_level': verification.permission_level,
        'verification_time_us': 2.38,
        'expires_at': verification.expires_at
    }
```

## 🚀 **Implementation Plan**

### **Phase 1: Create Site SDK/API (1-2 weeks)**

#### **1. Unified Verification Endpoint**
```python
# api/site_verification_api.py
@app.route('/api/v1/sites/<site_id>/verify', methods=['POST'])
def unified_site_verification(site_id):
    """
    Single endpoint for all site verification needs
    - Permission lemmas
    - Identity verification  
    - Bot detection
    - Trust bundle management (internal)
    """
    
    # Get site configuration (cached)
    site_config = get_site_config(site_id)
    
    # Load trust bundles (cached internally)
    trust_bundles = {
        'permission': get_permission_trust_bundle(site_id),
        'identity': get_federated_identity_trust_bundle(),
        'revocation': get_revocation_bloom_filter()
    }
    
    # Verify using your engine (2.38µs)
    result = lemma_engine.verify_all(
        user_credentials=request.json.get('credentials'),
        trust_bundles=trust_bundles,
        site_config=site_config
    )
    
    return {
        'verified': result.success,
        'permissions': result.permissions,
        'identity_verified': result.identity_verified,
        'bot_score': result.bot_score,
        'verification_time_us': result.timing
    }
```

#### **2. Smart Trust Bundle Caching**
```python
# Internal caching system (sites never see this)
class TrustBundleManager:
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    def get_site_trust_bundle(self, site_id):
        """Get trust bundle for site (cached internally)"""
        cache_key = f"trust_bundle_{site_id}"
        
        if cache_key in self.cache:
            bundle, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return bundle
        
        # Rebuild trust bundle
        bundle = self.build_trust_bundle(site_id)
        self.cache[cache_key] = (bundle, time.time())
        return bundle
    
    def build_trust_bundle(self, site_id):
        """Build complete trust bundle for site"""
        return {
            'site_permissions': self.get_site_permissions(site_id),
            'federated_identity_keys': self.get_federated_keys(),
            'revocation_bloom_filter': self.get_revocation_filter(),
            'oprf_evaluations': self.get_oprf_cache()
        }
```

#### **3. Ultra-Simple Site SDK**
```javascript
// Customer sites use this simple SDK
class LemmaIAMSDK {
    constructor(apiKey, siteId) {
        this.apiKey = apiKey;
        this.siteId = siteId;
        this.baseUrl = 'https://lemma.id/api/v1';
    }
    
    async verifyUser(userCredentials) {
        const response = await fetch(`${this.baseUrl}/sites/${this.siteId}/verify`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.apiKey}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                credentials: userCredentials,
                timestamp: Date.now()
            })
        });
        
        return await response.json();
        // Returns: { verified: true, permissions: [...], verification_time_us: 2.38 }
    }
    
    async checkPermission(userCredentials, resource, action) {
        const result = await this.verifyUser(userCredentials);
        
        if (!result.verified) return false;
        
        // Check if user has permission for this resource/action
        return result.permissions.some(perm => 
            perm.resource === resource && perm.actions.includes(action)
        );
    }
}

// One-line usage for sites
const lemma = new LemmaIAMSDK('site_api_key', 'site_123');
const canAccess = await lemma.checkPermission(userLemma, '/admin', 'read');
```

## 🎯 **Benefits of This Approach**

### **For Customer Sites:**
- ✅ **Ultra-simple integration**: Just call your API
- ✅ **No cryptographic knowledge needed**: You handle everything
- ✅ **No trust bundle management**: Completely transparent
- ✅ **Better performance**: Your caching and optimization
- ✅ **Automatic updates**: Sites get improvements automatically

### **For Your Platform:**
- ✅ **Better control**: You manage all cryptographic complexity
- ✅ **Easier support**: Fewer integration points to debug
- ✅ **Better caching**: Central optimization benefits all sites
- ✅ **Revenue protection**: Sites can't bypass your infrastructure
- ✅ **Easier scaling**: Central bottleneck is easier to optimize

### **For Users:**
- ✅ **Consistent experience**: Same wallet works everywhere
- ✅ **Better performance**: Optimized verification paths
- ✅ **Enhanced privacy**: Centralized privacy controls
- ✅ **Cross-site benefits**: Federated identity + site permissions

## 📋 **Current Status & Next Steps**

### **✅ What's Already Working:**
1. **Email automation** for both test and production systems
2. **Trust bundle sync** for federated identity network
3. **Wallet storage** with cross-browser synchronization
4. **Permission email flow** with reliable Mailgun delivery

### **🔧 What Needs Implementation:**
1. **Unified site verification API** (`/api/v1/sites/<site_id>/verify`)
2. **Trust bundle caching system** (internal to your platform)
3. **Simple site SDK** that calls your API instead of managing bundles
4. **Documentation update** to reflect the simplified approach

### **🎯 Recommended Next Steps:**
1. **Implement unified verification endpoint** (handles all trust bundle complexity)
2. **Create simple site SDK** that just calls your API
3. **Update integration documentation** to show the simplified approach
4. **Migrate existing sites** to use the new simplified SDK

This approach makes your service **much easier to integrate** while giving you **better control** over the cryptographic infrastructure. Sites get the benefits without the complexity!

Would you like me to implement the unified verification endpoint and simplified SDK?
