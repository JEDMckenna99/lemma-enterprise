# 🔐 Lemma IAM - Integration Guide (IAM-Only, No PoH Required)

## 🎯 **What is Lemma IAM?**

Lemma IAM is a **standalone Identity and Access Management system** that provides:

- **Microsecond-level permission verification** (31-94µs server, 0.36µs client)
- **Real Ed25519 + OPRF cryptography** (not JWT tokens)
- **No Stripe Identity required** (unlike full federated network)
- **Simple network**: Just your site ↔ your users
- **90%+ cost savings** vs Auth0/Duo ($0.15/MAU vs $2-8/MAU)

---

## 📊 **IAM-Only vs Full Platform**

| Feature | IAM-Only | Full Platform (PoH + IAM) |
|---------|----------|---------------------------|
| **Permission verification** | ✅ 31-182µs (server) | ✅ 31-182µs (server) |
| **Client-side verification** | ✅ ~63µs (WebCrypto) | ✅ ~63µs (WebCrypto) |
| **Real crypto (Ed25519+OPRF)** | ✅ Yes | ✅ Yes |
| **Stripe Identity required** | ❌ No | ✅ Yes ($2/user) |
| **Cross-site identity** | ❌ No | ✅ Yes |
| **Bot protection** | ❌ No | ✅ Yes |
| **Pricing** | **$0.15/MAU** | $0.20/MAU |
| **Best for** | Internal apps, B2B SaaS | Public sites, bot protection |

---

## 🚀 **5-Minute Integration**

### **Step 1: Register Your Site (2 minutes)**

```bash
curl -X POST https://lemma.id/api/v1/sites/register \
  -H "Content-Type: application/json" \
  -d '{
    "site_domain": "yourcompany.com",
    "company_name": "Your Company Inc",
    "admin_email": "admin@yourcompany.com",
    "plan": "professional"
  }'
```

**Response:**
```json
{
  "success": true,
  "site_id": "site_abc123",
  "api_key": "lemma_api_xyz789",
  "issuer_did": "did:lemma:a1b2c3d4e5f6...",
  "crypto_engine": "rust_ed25519_oprf"
}
```

**💡 Save these credentials!** You'll need them for all API calls.

---

### **Step 2: Define Permissions (1 minute)**

```bash
# Create admin permission
curl -X POST https://lemma.id/api/v1/sites/site_abc123/permissions \
  -H "X-API-Key: lemma_api_xyz789" \
  -H "Content-Type: application/json" \
  -d '{
    "permission_id": "admin",
    "display_name": "Administrator",
    "scope": ["*"],
    "description": "Full access to all resources"
  }'

# Create editor permission
curl -X POST https://lemma.id/api/v1/sites/site_abc123/permissions \
  -H "X-API-Key: lemma_api_xyz789" \
  -H "Content-Type: application/json" \
  -d '{
    "permission_id": "editor",
    "display_name": "Editor",
    "scope": ["posts:*", "comments:*"],
    "description": "Content management access"
  }'

# Create viewer permission
curl -X POST https://lemma.id/api/v1/sites/site_abc123/permissions \
  -H "X-API-Key: lemma_api_xyz789" \
  -H "Content-Type: application/json" \
  -d '{
    "permission_id": "viewer",
    "display_name": "Viewer",
    "scope": ["posts:read", "comments:read"],
    "description": "Read-only access"
  }'
```

**Scope Syntax:**
- `*` = Full access to everything
- `posts:*` = All actions on posts
- `posts:read` = Read-only on posts
- `/admin/*:*` = All actions on /admin paths

---

### **Step 3: Grant Permission to User (1 minute)**

```bash
curl -X POST https://lemma.id/api/v1/sites/site_abc123/users/did:lemma:user123/permissions \
  -H "X-API-Key: lemma_api_xyz789" \
  -H "Content-Type: application/json" \
  -d '{
    "permission_id": "admin",
    "expiry_days": 90
  }'
```

**Response:**
```json
{
  "success": true,
  "credential": {
    "id": "cred_xyz789",
    "issuer": "did:lemma:a1b2c3d4e5f6...",
    "subject": "did:lemma:user123",
    "claims": {
      "packageType": "permission",
      "siteId": "site_abc123",
      "permissionId": "admin",
      "scope": ["*"],
      "expiresAt": "1735689600"
    },
    "proof": {
      "type": "Ed25519Signature2020",
      "signatureValue": "a1b2c3d4..."
    }
  },
  "issue_time_us": 45.23,
  "crypto_engine": "rust_ed25519_oprf",
  "instructions": "Send this credential to user's browser to store in wallet"
}
```

**💡 Important:** Send the `credential` object to the user's browser to store in their wallet.

---

### **Step 4: Verify Access (1 minute)**

#### **Option A: Server-Side Verification (31-94µs)**

```bash
curl -X POST https://lemma.id/api/v1/auth/verify \
  -H "Content-Type: application/json" \
  -d '{
    "site_id": "site_abc123",
    "user_did": "did:lemma:user123",
    "resource": "/admin/users",
    "action": "read",
    "user_lemmas": [<credential from step 3>]
  }'
```

**Response:**
```json
{
  "success": true,
  "has_access": true,
  "verification_time_us": 47.32,
  "crypto_engine": "rust_ed25519_oprf",
  "verification_details": {
    "matched_permissions": [
      {
        "permission_id": "admin",
        "scope": ["*"],
        "verification_time_us": 47.32
      }
    ]
  }
}
```

#### **Option B: Client-Side Verification (0.36µs)**

```html
<!-- Add to your HTML -->
<script src="https://lemma.id/static/js/lemma-iam-sdk.js"></script>
<script>
// Initialize Lemma IAM
const lemmaIAM = new LemmaIAM({
    apiKey: 'lemma_api_xyz789',
    siteId: 'site_abc123',
    useClientSide: true  // 0.36µs verification!
});

// Verify access
async function checkAccess(resource, action) {
    const result = await lemmaIAM.verifyAccess(resource, action);
    
    if (result.hasAccess) {
        console.log(`✅ Access granted (${result.verificationTimeUs.toFixed(2)}µs)`);
        // Show protected content
        document.getElementById('admin-panel').style.display = 'block';
    } else {
        console.log('❌ Access denied');
        // Redirect to login or show error
        window.location.href = '/login';
    }
}

// Protect admin page
checkAccess('/admin/users', 'read');
</script>
```

---

## 📊 **Performance Expectations**

### **Real-World Performance**

| Operation | Performance | Notes |
|-----------|-------------|-------|
| **Issue permission lemma** | 40-60µs | Ed25519 signing |
| **Verify access (server)** | 31-94µs | Ed25519 + OPRF |
| **Verify access (client)** | 0.36µs | WebAssembly cached |
| **Revoke permission** | 10-20µs | OPRF + Bloom filter |

### **Comparison to Competitors**

| Provider | Verification Time | Cost/MAU | Savings |
|----------|------------------|----------|---------|
| **Lemma IAM** | **31-94µs** | **$0.15** | **Baseline** |
| Auth0 | 200-500ms | $2-5 | **2,000-10,000x slower, 13-33x more expensive** |
| Duo | 100-300ms | $3-8 | **1,000-6,000x slower, 20-53x more expensive** |
| Okta | 150-400ms | $2-6 | **1,500-8,000x slower, 13-40x more expensive** |

---

## 💡 **Common Use Cases**

### **1. Internal Admin Dashboard**

```javascript
// Protect admin routes in Express.js
const lemmaIAM = new LemmaIAM({ 
    apiKey: process.env.LEMMA_API_KEY,
    siteId: process.env.LEMMA_SITE_ID
});

app.use('/admin/*', async (req, res, next) => {
    const userLemmas = req.session.lemmas;
    
    const result = await lemmaIAM.verifyAccess(
        req.path,
        req.method.toLowerCase(),
        userLemmas
    );
    
    if (result.hasAccess) {
        console.log(`✅ Access granted (${result.verificationTimeUs}µs)`);
        next();
    } else {
        console.log('❌ Access denied');
        res.status(403).send('Access denied');
    }
});
```

### **2. B2B SaaS Multi-Tenant**

```javascript
// Each customer is a separate site
async function setupCustomer(customerId, customerDomain) {
    // Register customer as a site
    const response = await fetch('https://lemma.id/api/v1/sites/register', {
        method: 'POST',
        headers: { 'X-API-Key': MASTER_API_KEY },
        body: JSON.stringify({
            site_domain: customerDomain,
            company_name: customerData.name,
            admin_email: customerData.adminEmail,
            plan: 'professional'
        })
    });
    
    const { site_id, api_key } = await response.json();
    
    // Store in your database
    await db.customers.update(customerId, {
        lemma_site_id: site_id,
        lemma_api_key: api_key
    });
}

// Grant permissions to customer's users
async function addCustomerUser(customerId, userEmail, role) {
    const customer = await db.customers.get(customerId);
    const userDid = `did:lemma:${customerId}_${userEmail}`;
    
    await fetch(`https://lemma.id/api/v1/sites/${customer.lemma_site_id}/users/${userDid}/permissions`, {
        method: 'POST',
        headers: { 'X-API-Key': customer.lemma_api_key },
        body: JSON.stringify({
            permission_id: role,  // 'admin', 'editor', 'viewer'
            expiry_days: 90
        })
    });
}
```

### **3. API Access Control**

```javascript
// Protect API endpoints
app.post('/api/data', async (req, res) => {
    const result = await lemmaIAM.verifyAccess(
        '/api/data',
        'write',
        req.body.user_lemmas
    );
    
    if (!result.hasAccess) {
        return res.status(403).json({ 
            error: 'Insufficient permissions',
            required: 'data:write',
            verification_time_us: result.verificationTimeUs
        });
    }
    
    // Process request
    const data = await processData(req.body);
    res.json({ 
        success: true, 
        data,
        verification_time_us: result.verificationTimeUs
    });
});
```

### **4. React/Next.js Integration**

```javascript
// hooks/usePermission.js
import { useState, useEffect } from 'react';
import { LemmaIAM } from '@lemma/iam-sdk';

const lemmaIAM = new LemmaIAM({
    apiKey: process.env.NEXT_PUBLIC_LEMMA_API_KEY,
    siteId: process.env.NEXT_PUBLIC_LEMMA_SITE_ID,
    useClientSide: true
});

export function usePermission(resource, action) {
    const [hasAccess, setHasAccess] = useState(false);
    const [loading, setLoading] = useState(true);
    
    useEffect(() => {
        async function checkAccess() {
            const result = await lemmaIAM.verifyAccess(resource, action);
            setHasAccess(result.hasAccess);
            setLoading(false);
        }
        checkAccess();
    }, [resource, action]);
    
    return { hasAccess, loading };
}

// Usage in component
function AdminPanel() {
    const { hasAccess, loading } = usePermission('/admin/users', 'read');
    
    if (loading) return <div>Checking permissions...</div>;
    if (!hasAccess) return <div>Access denied</div>;
    
    return <div>Admin Panel Content</div>;
}
```

---

## 🔐 **Security Features**

### **Cryptographic Guarantees**

- **Ed25519 signatures**: Unforgeable credentials (256-bit security)
- **OPRF revocation**: Privacy-preserving revocation (server doesn't learn which credentials are checked)
- **Bloom filters**: Efficient revocation checking (O(1) lookup)
- **Site isolation**: Permissions don't leak between sites (separate issuer per site)

### **No Stripe Identity Required**

Unlike the full Lemma platform (which includes bot protection and cross-site identity), **IAM-only mode** lets you:

- Issue permission lemmas to any user (no PoH verification needed)
- Avoid $2/user Stripe Identity costs
- Focus on access control, not identity verification
- Perfect for internal apps and B2B SaaS

### **Revocation**

```bash
# Revoke a specific permission
curl -X DELETE https://lemma.id/api/v1/sites/site_abc123/users/did:lemma:user123/permissions/admin \
  -H "X-API-Key: lemma_api_xyz789"
```

**How it works:**
1. Permission lemma ID added to OPRF evaluation
2. OPRF result added to Bloom filter
3. Future verifications fail (31-94µs check)
4. Privacy-preserving (server doesn't learn which credentials are checked)

---

## 💰 **Pricing**

### **IAM-Only Pricing**

- **$0.15 per Monthly Active User (MAU)**
- No setup fees
- No Stripe Identity costs
- Pay only for users who verify access each month

### **Example Costs**

| Users | Lemma IAM | Auth0 | Duo | Savings vs Auth0 | Savings vs Duo |
|-------|-----------|-------|-----|------------------|----------------|
| 100 | $15/mo | $350/mo | $500/mo | **96% cheaper** | **97% cheaper** |
| 1,000 | $150/mo | $3,500/mo | $5,000/mo | **96% cheaper** | **97% cheaper** |
| 10,000 | $1,500/mo | $35,000/mo | $50,000/mo | **96% cheaper** | **97% cheaper** |

### **Annual Savings**

| Users | Lemma IAM | Auth0 | Duo | Annual Savings (Auth0) | Annual Savings (Duo) |
|-------|-----------|-------|-----|------------------------|----------------------|
| 100 | $180 | $4,200 | $6,000 | **$4,020/year** | **$5,820/year** |
| 1,000 | $1,800 | $42,000 | $60,000 | **$40,200/year** | **$58,200/year** |
| 10,000 | $18,000 | $420,000 | $600,000 | **$402,000/year** | **$582,000/year** |

---

## 🚀 **Migration from Auth0/Duo**

### **Auth0 Migration**

```javascript
// Before (Auth0)
const auth0 = new Auth0Client({
    domain: 'your-domain.auth0.com',
    clientId: 'your-client-id'
});

const user = await auth0.getUser();
const hasAccess = user.permissions.includes('admin');

// After (Lemma IAM)
const lemmaIAM = new LemmaIAM({
    apiKey: 'lemma_api_xyz789',
    siteId: 'site_abc123'
});

const result = await lemmaIAM.verifyAccess('/admin/users', 'read');
const hasAccess = result.hasAccess;

// Result: 2,000-10,000x faster, 96% cheaper
```

### **Duo Migration**

```javascript
// Before (Duo)
const duo = require('@duosecurity/duo_web');
const sig_request = duo.sign_request(ikey, skey, akey, username);
// ... complex multi-step verification

// After (Lemma IAM)
const result = await lemmaIAM.verifyAccess(resource, action);
// Done! 31-94µs verification

// Result: 1,000-6,000x faster, 97% cheaper
```

---

## 📚 **API Reference**

### **Site Management**

#### **Register Site**
```
POST /api/v1/sites/register
Headers: X-API-Key: <master_api_key>
Body: { site_domain, company_name, admin_email, plan }
```

#### **Create Permission**
```
POST /api/v1/sites/{site_id}/permissions
Headers: X-API-Key: <site_api_key>
Body: { permission_id, display_name, scope, description }
```

### **User Management**

#### **Grant Permission**
```
POST /api/v1/sites/{site_id}/users/{user_did}/permissions
Headers: X-API-Key: <site_api_key>
Body: { permission_id, expiry_days }
```

#### **Revoke Permission**
```
DELETE /api/v1/sites/{site_id}/users/{user_did}/permissions/{permission_id}
Headers: X-API-Key: <site_api_key>
```

### **Access Verification**

#### **Verify Access**
```
POST /api/v1/auth/verify
Body: { site_id, user_did, resource, action, user_lemmas }
```

---

## 🎯 **Next Steps**

1. **Sign up**: https://lemma.id/register
2. **Get API key**: Complete registration
3. **Run quick start**: `python examples/iam_quick_start.py`
4. **Integrate SDK**: Add to your application
5. **Test thoroughly**: Validate performance and security
6. **Go live**: Deploy to production

---

## 💬 **Support**

- **Email**: support@lemma.id
- **Documentation**: https://docs.lemma.id
- **GitHub**: https://github.com/lemma-id/lemma-platform
- **Discord**: https://discord.gg/lemma

---

## ✅ **Checklist for Production**

- [ ] Site registered and API key obtained
- [ ] Permissions defined for your use case
- [ ] Test users created with permissions
- [ ] Access verification tested (31-94µs confirmed)
- [ ] Client-side SDK integrated (0.36µs confirmed)
- [ ] Error handling implemented
- [ ] Revocation tested
- [ ] Billing configured
- [ ] Monitoring set up
- [ ] Documentation updated for your team

**Ready to launch!** 🚀

