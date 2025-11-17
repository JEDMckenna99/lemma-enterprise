# Lemma IAM API Reference

Complete API reference for Lemma Identity & Access Management. **Sign in once, stay signed in. Built-in bot resistance.**

---

## 🌐 Base URL

```
Production: https://lemma.id
```

---

## 🔑 Authentication

All API requests require authentication via API key:

```http
Authorization: Bearer YOUR_API_KEY
```

Get your API key from: https://lemma.id/dashboard

---

## 📋 Core Endpoints

### 1. Request Access (Issue Credential)

Send authentication email to user and issue credential upon confirmation.

**Endpoint:** `POST /api/v1/iam/request-access`

**Headers:**
```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
    "site_id": "your_site_id",
    "site_domain": "yoursite.com",
    "user_email": "user@example.com",
    "permission_level": "user",
    "redirect_url": "https://yoursite.com/dashboard"
}
```

**Parameters:**
- `site_id` (required): Your site identifier
- `site_domain` (required): Your domain name
- `user_email` (required): User's email address
- `permission_level` (optional): Role to grant - `user`, `admin`, `editor`, `viewer` (default: `user`)
- `redirect_url` (optional): Where to redirect after confirmation

**Response:**
```json
{
    "success": true,
    "message": "Confirmation email sent to user@example.com",
    "token": "conf_abc123...",
    "expires_in": 86400
}
```

**Features:**
- ✅ Built-in bot resistance (nonce verification on confirmation)
- ✅ Credential persists in user's browser (encrypted)
- ✅ User stays signed in until expiration or revocation

---

### 2. Verify Credential (With Bot Resistance)

Verify a credential with fresh nonce for bot defense.

**Endpoint:** `POST /api/sdk/verify-permission-lemma`

**Headers:**
```http
Content-Type: application/json
```

**Request Body:**
```json
{
    "credential": { 
        "id": "cred_abc123",
        "issuer": "did:lemma:...",
        "subject": "did:lemma:user_...",
        "claims": { /* credential claims */ },
        "proof": { /* Ed25519 signature */ }
    },
    "nonce": "32-byte-hex-string",
    "site_domain": "yoursite.com",
    "timestamp": 1700000000000
}
```

**Response (Success):**
```json
{
    "success": true,
    "verified": true,
    "claims": {
        "email": "user@example.com",
        "permissionId": "admin",
        "siteDomain": "yoursite.com"
    },
    "verification_time_us": 182.5
}
```

**Response (Failure - Nonce Reused):**
```json
{
    "success": false,
    "verified": false,
    "error": "Nonce already used (possible replay attack)",
    "security_alert": true
}
```

**Security Features:**
- ✅ Nonce must be fresh (never used before, Redis-cached)
- ✅ Timestamp must be within 5 minutes
- ✅ Site domain must match credential
- ✅ Ed25519 signature verification
- ✅ Revocation check (<100ms via Bloom filter)

**Bot Resistance:** Prevents credential replay by requiring fresh nonce on each verification.

---

### 3. Admin Self-Issue

Bootstrap admin credential using API key (for site owner).

**Endpoint:** `POST /api/v1/iam/admin/self-issue`

**Headers:**
```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
    "site_id": "your_site_id",
    "site_domain": "yoursite.com",
    "user_email": "admin@yoursite.com",
    "permission_level": "super_admin"
}
```

**Response:**
```json
{
    "success": true,
    "credential": { 
        /* Signed Ed25519 credential */
        "id": "cred_admin_...",
        "issuer": "did:lemma:...",
        "subject": "did:lemma:user_...",
        "claims": {
            "email": "admin@yoursite.com",
            "permissionId": "super_admin",
            "siteDomain": "yoursite.com"
        },
        "proof": { /* Ed25519 signature */ }
    },
    "user_did": "did:lemma:user_abc123...",
    "issuer_did": "did:lemma:issuer_xyz...",
    "issue_time_us": 148.23
}
```

**Note:** Credential automatically stored in your browser wallet. **Stays valid for 90 days.**

---

### 4. List Users

Get all users with permissions for your site.

**Endpoint:** `GET /api/platform/users`

**Query Parameters:**
- `site_id` (optional): Filter by site ID (default: lemma_platform)

**Response:**
```json
{
    "users": [
        {
            "email": "user@example.com",
            "permission": "admin",
            "granted_at": "2025-11-17T10:00:00Z",
            "expires_at": "2026-02-17T10:00:00Z",
            "status": "active"
        },
        {
            "email": "user2@example.com",
            "permission": "editor",
            "granted_at": "2025-11-15T14:30:00Z",
            "expires_at": "2026-02-15T14:30:00Z",
            "status": "active"
        }
    ],
    "total": 2
}
```

---

### 5. Revoke Permission

Revoke user's credential (propagates in <100ms via event-driven sync).

**Endpoint:** `POST /api/platform/revoke-permission`

**Headers:**
```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

**Request Body:**
```json
{
    "email": "user@example.com",
    "site_id": "your_site_id",
    "reason": "access_violation"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Permission revoked for user@example.com",
    "propagation_time_ms": 87,
    "affected_credentials": 1
}
```

**Revocation Speed:**
- Traditional systems: 30-60s (session timeout)
- Lemma: <100ms (Redis pub/sub event-driven sync)

---

### 6. Get Revocation List (Bloom Filter)

Download Bloom filter for client-side revocation checking.

**Endpoint:** `GET /api/revocation/bloom-filter`

**Response:**
```json
{
    "success": true,
    "filter_type": "global_sha256",
    "privacy_mechanism": "sha256_web_crypto",
    "count": 15,
    "filter_bytes": "base64-encoded-bloom-filter",
    "filter_size_bytes": 2048,
    "last_updated": "2025-11-17T10:30:00Z"
}
```

**Features:**
- ✅ Privacy-preserving (SHA-256 hashed credential IDs)
- ✅ Cached for 7 days client-side
- ✅ Enables offline verification
- ✅ <1µs lookup time

---

## 🛠️ Client-Side SDK

### JavaScript Integration

```javascript
// Initialize once
const lemma = new LemmaAuth({
    apiKey: 'YOUR_API_KEY',
    siteId: 'your_site_id'
});

// Check authentication (includes bot resistance)
const isAuth = await lemma.isAuthenticated();

// Get user info
const user = await lemma.getUser();
// Returns: { email, role, authenticated }

// Check specific permission
const isAdmin = await lemma.hasPermission('admin');

// Request access for new user
await lemma.sendLoginEmail('newuser@example.com');
```

---

## 🔐 Security Features

### 1. Built-In Bot Resistance (Nonce-Based)

Every verification requires a fresh cryptographic nonce:

```javascript
// Client generates 256-bit nonce
const nonce = crypto.getRandomValues(new Uint8Array(32));

// Server checks:
// - Nonce never used before (Redis cache, 5-minute expiry)
// - Timestamp within 5-minute window
// - Ed25519 signature valid
// - Credential not revoked (Bloom filter)

// Result: Replay attacks prevented automatically
```

**Traditional systems require separate bot protection:**
- reCAPTCHA (annoying for users)
- hCaptcha (privacy concerns)
- Cloudflare Turnstile (another dependency)

**Lemma: Bot resistance built into authentication.**

---

### 2. Session-Free Architecture (Zero Tracking)

**Traditional:**
```
Server session database:
{
    session_abc: { user: 'alice@example.com', ip: '1.2.3.4', login_time: '10:30am' },
    session_xyz: { user: 'bob@example.com', ip: '5.6.7.8', login_time: '11:45am' }
}

// Server KNOWS who's logged in, when, from where
```

**Lemma:**
```
Server state: {}  // Empty! Zero sessions!

// Verification happens on user's device
// Server has NO IDEA who's "logged in"
// Complete privacy
```

**Benefits:**
- ✅ Infinite scalability (stateless)
- ✅ No session database
- ✅ No sticky sessions (load balancer friendly)
- ✅ Multi-region ready
- ✅ CDN compatible

---

### 3. Persistent Credentials (Stay Signed In)

```javascript
// Monday: User signs in
await auth.sendLoginEmail('user@example.com');
// Credential stored in encrypted browser wallet

// Tuesday-Sunday: Still authenticated
await auth.isAuthenticated(); // ✅ true (no re-login needed)

// Week 2-12: Still authenticated
await auth.isAuthenticated(); // ✅ true

// Day 90: Credential expires
await auth.isAuthenticated(); // ❌ false (re-confirm email)

// OR: Admin revokes immediately
// Revocation propagates in <100ms via Redis pub/sub
```

**No annoying session timeouts. No forced logouts.**

---

### 4. Event-Driven Revocation

```javascript
// Traditional: Wait for session timeout (30-60s)
// Lemma: Instant revocation via Redis pub/sub (<100ms)

// When admin revokes:
POST /api/platform/revoke-permission

// What happens:
// 1. Server adds to revocation list
// 2. Redis pub/sub event published
// 3. All clients receive event in <100ms
// 4. Clients invalidate cached credential
// 5. Next verification fails

// User experience:
// - 10:00:00 - User is authenticated
// - 10:00:01 - Admin revokes
// - 10:00:02 - User tries to access
// - 10:00:02.1 - Access denied (revocation propagated)
```

---

## ⚡ Performance Characteristics

### Verification Speed

| Operation | Time | Cost |
|-----------|------|------|
| Client-side signature check | 18µs | $0.00 |
| Revocation check (Bloom filter) | <1µs | $0.00 |
| Nonce generation | <1ms | $0.00 |
| **Total verification** | **<20ms** | **$0.00** |

Compare to Auth0:
- Server round-trip: 200-500ms
- Cost per verification: $0.05
- **Lemma is 10,000x faster and free**

### Revocation Propagation

| System | Propagation Time |
|--------|------------------|
| Traditional (session timeout) | 30-60 seconds |
| JWT (token expiry) | Minutes to hours |
| **Lemma (event-driven)** | **<100ms** |

---

## ❌ Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| `nonce_reused` | Nonce already used | Possible replay attack detected |
| `timestamp_old` | Timestamp >5 min | Credential request too old |
| `domain_mismatch` | Wrong domain | Credential for different site |
| `signature_invalid` | Bad signature | Credential tampered or forged |
| `credential_revoked` | Admin revoked | User access removed by admin |
| `credential_expired` | Past expiration | Need to re-confirm email |
| `invalid_api_key` | Wrong API key | Check your dashboard |

---

## 🎯 Best Practices

### 1. Cache Authentication Checks

```javascript
// ✅ Good: Cache quick checks, verify with nonce periodically
let lastVerified = null;
let CACHE_TTL = 60000; // 1 minute

async function checkAuth() {
    const now = Date.now();
    
    // Use cached result if fresh
    if (lastVerified && (now - lastVerified.time) < CACHE_TTL) {
        return lastVerified.result;
    }
    
    // Quick check without nonce
    const isAuth = await auth.isAuthenticated(true);
    lastVerified = { result: isAuth, time: now };
    
    return isAuth;
}
```

### 2. Force Fresh Nonce for Sensitive Operations

```javascript
// ✅ Good: Use nonce verification for payments, data changes
async function handlePayment() {
    // Force fresh nonce verification
    const verified = await auth.isAuthenticated(false);
    
    if (verified) {
        processPayment();
    } else {
        alert('Authentication required');
    }
}
```

### 3. Handle Expired Credentials Gracefully

```javascript
// ✅ Good: Detect expiration and request re-authentication
async function checkAuth() {
    const isAuth = await auth.isAuthenticated(true);
    
    if (!isAuth) {
        const user = await auth.getUser();
        
        if (!user) {
            // No credential - show login
            showLoginForm();
        } else if (isExpired(user.credential)) {
            // Credential expired - request renewal
            showRenewalPrompt(user.email);
        } else {
            // Revoked or invalid - show login
            showLoginForm();
        }
    }
}
```

---

## 🎯 Integration Patterns

### Pattern 1: Simple Login

```javascript
// Just authentication, no permissions
const auth = new LemmaAuth({
    apiKey: 'YOUR_API_KEY',
    siteId: 'my_app'
});

// All users get same access
if (await auth.isAuthenticated()) {
    showApp();
}
```

### Pattern 2: Role-Based Access Control (RBAC)

```javascript
// Different permissions for different users
const auth = new LemmaAuth({
    apiKey: 'YOUR_API_KEY',
    siteId: 'my_app'
});

const user = await auth.getUser();

if (user.role === 'admin') {
    showAdminPanel();
} else if (user.role === 'editor') {
    showEditorTools();
} else {
    showViewerMode();
}
```

### Pattern 3: Resource-Level Permissions

```javascript
// Check specific permissions for specific resources
const auth = new LemmaAuth({
    apiKey: 'YOUR_API_KEY',
    siteId: 'my_app'
});

// Check permission before action
if (await auth.hasPermission('admin')) {
    allowUserDeletion();
}

if (await auth.hasPermission('editor')) {
    allowContentEdit();
}
```

---

## 🔄 Credential Workflow

### Initial Authentication

```
1. User visits your site
2. Your site calls: auth.sendLoginEmail('user@example.com')
3. User receives email with confirmation link
4. User clicks link → Credential issued
5. Credential stored in encrypted browser wallet
6. User redirected to your site
7. auth.isAuthenticated() returns true
8. User is authenticated!
```

### Subsequent Visits (Same Device)

```
1. User visits your site (Day 2, 3, 4... 90)
2. auth.isAuthenticated() returns true (credential in wallet)
3. User is authenticated automatically
4. No email, no login form, no re-authentication
```

**This is the key difference: Users stay signed in naturally.**

---

## 🛡️ Security Model

### Threat Model

**What Lemma Prevents:**
- ✅ Credential forgery (Ed25519 signature, 2^128 security)
- ✅ Replay attacks (fresh nonce required)
- ✅ Session hijacking (no sessions to hijack)
- ✅ Bot automation (nonce prevents reuse)
- ✅ Man-in-the-middle (signature binds identity to claims)

**What Admins Control:**
- ✅ Instant revocation (<100ms propagation)
- ✅ Permission assignment (RBAC)
- ✅ Credential expiration (default 90 days)

**What Users Control:**
- ✅ Their credential (stored in THEIR browser)
- ✅ Which devices have credentials
- ✅ Manual removal (optional)

### Security Properties

```
Credential Security:
- Ed25519 signature (quantum-resistant alternative: future)
- Nonce-based replay prevention
- 5-minute timestamp window
- Domain binding

Privacy:
- Zero server sessions (no tracking)
- Verification happens on user's device
- Revocation checks via Bloom filter (privacy-preserving)

Resilience:
- Works offline (7-day cache)
- Instant revocation when online
- Client-side verification (edge computing)
```

---

## 📊 Monitoring & Analytics

### Get Platform Stats

**Endpoint:** `GET /api/platform/stats`

**Response:**
```json
{
    "active_sites": 5,
    "total_permissions": 123,
    "monthly_active_users": 456,
    "active_credentials": 789,
    "revocations_today": 2
}
```

### Track Usage

Lemma tracks minimal data for billing:
- Monthly Active Users (MAU) only
- No login times
- No IP addresses
- No session data

**Privacy-first billing model.**

---

## 🌐 Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| Email confirmations | 5 per email | 1 hour |
| API calls | 1000 requests | 1 minute |
| Verification | Unlimited | - |

**Note:** Client-side verification has no rate limits (happens on user's device).

---

## 🆘 Error Handling

### Example: Comprehensive Error Handling

```javascript
async function authenticate() {
    try {
        const isAuth = await auth.isAuthenticated(true);
        
        if (isAuth) {
            return true;
        }
        
        // Not authenticated - check why
        const user = await auth.getUser();
        
        if (!user) {
            // No credential at all
            console.log('No credential found - showing login');
            showLoginForm();
            return false;
        }
        
        // Has credential but invalid - could be revoked or expired
        console.log('Credential invalid - likely revoked or expired');
        showLoginForm();
        return false;
        
    } catch (error) {
        if (error.message.includes('offline')) {
            // Offline mode - use cached verification
            console.log('Offline - using cached result');
            return handleOfflineMode();
        }
        
        console.error('Authentication error:', error);
        return false;
    }
}
```

---

## 🎯 Migration from Traditional Auth

### From Session-Based Auth

**Before (Traditional):**
```javascript
// Server-side session
app.get('/dashboard', (req, res) => {
    if (req.session.user) {
        res.render('dashboard');
    } else {
        res.redirect('/login');
    }
});
```

**After (Lemma):**
```javascript
// Client-side verification
// No server session needed!

<script>
const auth = new LemmaAuth({ apiKey: 'KEY', siteId: 'ID' });

if (await auth.isAuthenticated()) {
    showDashboard();
} else {
    showLogin();
}
</script>
```

**Benefits:**
- Remove session database
- Remove session middleware
- Infinite scalability
- Better privacy

---

## 📖 Additional Resources

- [Quick Start Guide](./QUICK_START_SIMPLE_LOGIN.md) - Get started in 5 minutes
- [Live Demo](https://lemma.id/examples/simple-auth-demo.html) - Test it yourself
- [Integration Examples](../examples/) - Complete code examples

---

## 🆘 Support

- **Documentation:** https://lemma.id/docs
- **Email:** support@lemma.id
- **Status:** https://status.lemma.id

---

## 🎉 Welcome to Persistent Authentication

**Stop forcing users to re-login every 30 minutes.**  
**Start with authentication that works like a physical ID card.**

Sign in once. Stay signed in. That's it.

