# Quick Start: Add Login in 5 Minutes

Lemma provides email-based authentication with built-in bot resistance. **Sign in once per device, stay signed in.**

---

## 🎯 **What Makes Lemma Different**

### **Traditional Login Systems:**
- ❌ Session expires every 30 minutes
- ❌ Must logout to "secure" your account
- ❌ Server tracks all your sessions
- ❌ Re-login on every device frequently

### **Lemma:**
- ✅ **Sign in once per device, stay signed in**
- ✅ No session timeouts (credentials persist until expiration)
- ✅ Zero server tracking (session-free architecture)
- ✅ Built-in bot resistance (cryptographic nonces)
- ✅ Works offline (7-day cache)
- ✅ Instant revocation when needed (<100ms)

**Your credential is like a physical ID card - YOU control it in YOUR browser.**

---

## 🚀 **Step 1: Get Your API Key**

1. Sign up at [lemma.id/register](https://lemma.id/register)
2. Copy your API key from the dashboard

---

## 🚀 **Step 2: Add Lemma to Your Site**

```html
<!-- Add before </body> -->
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
<script src="https://lemma.id/static/js/lemma-auth-simple.js"></script>
```

---

## 🚀 **Step 3: Initialize Authentication**

```javascript
const auth = new LemmaAuth({
    apiKey: 'your_api_key_here',
    siteId: 'your_site_id',
    debug: true  // Shows console logs
});
```

---

## 🚀 **Step 4: Check Authentication**

```javascript
// Check if user has valid credential
const isAuthenticated = await auth.isAuthenticated();

if (isAuthenticated) {
    // User has valid credential - show your app
    const user = await auth.getUser();
    console.log('Authenticated as:', user.email);
    showDashboard();
} else {
    // No credential - show email input
    showLoginForm();
}
```

---

## 🚀 **Step 5: Request Access**

```javascript
// Send authentication email
async function requestAccess(email) {
    const result = await auth.sendLoginEmail(email);
    
    if (result.success) {
        alert('Check your email to complete authentication!');
    } else {
        alert('Error: ' + result.error);
    }
}
```

---

## ✅ **That's It! Your Site Now Has:**

- ✅ Email-based authentication
- ✅ **Built-in bot resistance** (cryptographic nonces)
- ✅ **Sign in once per device** (credentials persist)
- ✅ No password management
- ✅ No session tracking
- ✅ Sub-100ms verification
- ✅ Works offline (7-day cache)
- ✅ Instant revocation (<100ms when admin revokes)

---

## 🎯 **Key Concept: User-Controlled Credentials**

### **Traditional Session-Based Auth:**
```
User logs in
  ↓
Server creates session (stored in Redis/database)
  ↓
Server tracks user (knows you're logged in)
  ↓
Session expires (must re-login)
  ↓
User must logout (to clear server session)
```

### **Lemma Credential-Based Auth:**
```
User confirms email (one time)
  ↓
Credential issued to user's browser wallet (encrypted)
  ↓
Server has ZERO state (doesn't track you)
  ↓
Credential verified locally on each request
  ↓
Credential stays valid until admin revokes or it expires
  ↓
No logout needed! (credential is in YOUR browser, not server session)
```

**Think of it like a physical ID card:**
- You don't "logout" of having a driver's license
- You carry it in your wallet
- You show it when needed
- It stays valid until it expires or gets revoked
- **You control when you have it**

---

## 🔐 **Built-In Bot Resistance**

### **Traditional Login Systems:**
```javascript
// No bot defense built-in
// Must add reCAPTCHA separately:
if (user.login(email, password)) {
    // Anyone with credentials can replay this!
    grantAccess();
}
```

### **Lemma:**
```javascript
// Bot resistance BUILT-IN
// Every verification requires fresh nonce:
const nonce = crypto.getRandomValues(new Uint8Array(32));
const verified = await auth.isAuthenticated(); // Uses nonce internally

// Server checks:
// 1. Nonce never used before (Redis cache)
// 2. Timestamp within 5 minutes
// 3. Site domain matches credential
// 4. Ed25519 signature valid
// 5. Not revoked (Bloom filter)

// Result: Bots CANNOT reuse stolen credentials!
```

**No CAPTCHAs. No friction. Just cryptographic proof.**

---

## 📚 **Complete API Reference**

### **LemmaAuth Class**

#### **Constructor**
```javascript
const auth = new LemmaAuth({
    apiKey: 'your_api_key',      // Required: Get from lemma.id/dashboard
    siteId: 'your_site_id',      // Required: Your site identifier
    siteDomain: 'yoursite.com',  // Optional: defaults to window.location.hostname
    debug: false                 // Optional: enable debug logging
});
```

#### **Methods**

##### `sendLoginEmail(email, options)`
Request access via email confirmation.

```javascript
const result = await auth.sendLoginEmail('user@example.com', {
    role: 'user',                           // Optional: 'user', 'admin', 'editor'
    redirectUrl: 'https://yoursite.com/app' // Optional: where to redirect after
});

// Returns: { success: boolean, message: string }
```

##### `isAuthenticated(skipNonce)`
Check if user has valid credential. Includes bot resistance.

```javascript
// With nonce verification (bot resistance)
const isAuth = await auth.isAuthenticated(false);

// Quick check (skip nonce for performance)
const isAuth = await auth.isAuthenticated(true);

// Returns: boolean
```

##### `getUser()`
Get current authenticated user information.

```javascript
const user = await auth.getUser();

// Returns:
// {
//     email: 'user@example.com',
//     role: 'user',
//     authenticated: true,
//     credential: { /* full credential object */ }
// }
// or null if not authenticated
```

##### `hasPermission(permission)`
Check if user has specific permission.

```javascript
const isAdmin = await auth.hasPermission('admin');
const isEditor = await auth.hasPermission('editor');

// Returns: boolean
```

---

## 🎯 **Common Use Cases**

### **Use Case 1: Simple App Authentication**

```javascript
// Initialize
const auth = new LemmaAuth({
    apiKey: 'your_api_key',
    siteId: 'my_app'
});

// Check on page load
window.addEventListener('DOMContentLoaded', async () => {
    const isAuth = await auth.isAuthenticated(true); // Quick check
    
    if (isAuth) {
        const user = await auth.getUser();
        showApp(user);
    } else {
        showLoginForm();
    }
});

// Login form handler
async function handleLogin(email) {
    const result = await auth.sendLoginEmail(email);
    alert('Check your email!');
}
```

**User Experience:**
- First visit: Enter email, confirm link
- Every future visit: Automatically authenticated
- **No repeated logins for 90 days**

---

### **Use Case 2: Admin Panel Protection**

```javascript
const auth = new LemmaAuth({
    apiKey: 'your_api_key',
    siteId: 'my_app'
});

// Protect admin routes
async function checkAdminAccess() {
    const isAdmin = await auth.hasPermission('admin');
    
    if (!isAdmin) {
        window.location.href = '/unauthorized';
    }
}

// Call on admin page load
checkAdminAccess();
```

---

## 🔄 **Credential Lifecycle**

```
Day 0: User confirms email
  ↓
  Credential issued (Ed25519 signed)
  ↓
  Stored in encrypted browser wallet
  ↓
Days 1-89: User stays authenticated
  ↓
  - No re-logins needed
  - Works offline
  - Verification happens locally
  - Admin can revoke anytime (<100ms)
  ↓
Day 90: Credential expires
  ↓
  User re-confirms email (seamless)
  ↓
  New credential issued
```

---

## 🎯 **What You Get vs Competitors**

| Feature | Auth0/Clerk | Lemma |
|---------|-------------|-------|
| **Re-login Frequency** | Often (session timeouts) | **Once per 90 days** |
| **Session Timeouts** | Yes (30-60 min) | **No (credentials persist)** |
| **Bot Resistance** | Extra (reCAPTCHA) | **Built-in (nonces)** |
| **Server Tracking** | Full tracking | **Zero tracking** |
| **Offline Capability** | No | **Yes (7 days)** |
| **Revocation Speed** | 30-60s | **<100ms** |
| **Verification Speed** | 200-500ms | **18µs (10,000x faster)** |
| **Cost per Verification** | $0.05 | **$0.00** |

---

## 📖 **Next Steps**

- [Live Demo](https://lemma.id/examples/simple-auth-demo.html) - Test it yourself
- [API Reference](./IAM_API_REFERENCE.md) - Complete API documentation
- [Integration Examples](../examples/) - More complex examples

---

## 🆘 **Support**

- **Documentation:** https://lemma.id/docs
- **Live Demo:** https://lemma.id/examples/simple-auth-demo.html
- **Email:** support@lemma.id

---

## 🎉 **Welcome to Persistent Authentication**

**Traditional thinking:** Users must logout for security  
**Lemma thinking:** Credentials persist until admin revokes or they expire

**Your users will thank you for not forcing them to re-login every 30 minutes.**

