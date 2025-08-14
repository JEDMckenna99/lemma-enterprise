# 🔐⚡ Verification vs Authentication - Clear Process Distinction

## 📋 **Overview**

Lemma uses **two distinct processes** to provide secure, high-performance identity management:

1. **🔐 VERIFICATION** - One-time identity creation via API calls
2. **⚡ AUTHENTICATION** - Ongoing access validation via offline SDK

This separation enables **verify once, authenticate everywhere** with microsecond performance.

---

## 🔐 **VERIFICATION PROCESS**
*Identity Creation & Credential Issuance*

### **Purpose**
Create new cryptographically-signed identity credentials through third-party verification (Stripe KYC).

### **When Used**
- First-time users who need identity credentials
- Expired credentials requiring renewal
- Revoked credentials requiring re-verification
- Users switching to new devices (optional re-verification)

### **How It Works**
1. **API Call**: `POST /api/sdk/start-identity-verification`
2. **User Action**: Complete Stripe Identity KYC (document + liveness)
3. **API Call**: `POST /api/sdk/complete-identity-verification`
4. **Result**: Receive cryptographically-signed identity lemma

### **Performance**
- **Time**: ~500ms - 2 seconds (includes Stripe KYC validation)
- **Network**: Required (API calls to Stripe and Lemma backend)
- **Frequency**: Once per user (or when credentials need renewal)

### **Technical Details**
- **Location**: Server-side API endpoints
- **Dependencies**: Stripe Identity, network connectivity
- **Output**: Identity lemma with essential claims:
  - `packageType: 'identity'` (credential routing)
  - `isHuman: true` (bot protection claim)
  - `verificationMethod: 'stripe_identity'` (proof method)

### **Code Example**
```javascript
// Start verification process
const session = await fetch('/api/sdk/start-identity-verification', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer your-api-key' },
  body: JSON.stringify({ returnUrl: 'https://yoursite.com/verified' })
});

// User completes Stripe KYC...

// Complete verification and get credential
const credential = await fetch('/api/sdk/complete-identity-verification', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer your-api-key' },
  body: JSON.stringify({ sessionId: 'vs_...' })
});

console.log('New identity credential:', credential);
```

---

## ⚡ **AUTHENTICATION PROCESS**
*Offline Credential Validation & Access Control*

### **Purpose**
Validate existing credentials for instant access decisions without network calls.

### **When Used**
- Every page load (automatic background checks)
- Cross-site access (federated authentication)
- Periodic security validation (1-30 minute intervals)
- Real-time access control decisions

### **How It Works**
1. **SDK Check**: Load credentials from local storage (federated wallet)
2. **Cryptographic Validation**: Rust/WASM engine validates signatures (~5µs)
3. **Access Decision**: Instant allow/deny based on validation result
4. **Background Sync**: Periodic updates from federated network

### **Performance**
- **Time**: ~1-50 microseconds (offline cryptographic validation)
- **Network**: Zero calls for cached credentials
- **Frequency**: Every page load + background intervals

### **Technical Details**
- **Location**: Client-side Rust/WASM SDK
- **Dependencies**: None (fully offline after initial credential storage)
- **Storage**: Multi-layer (IndexedDB + localStorage + sessionStorage + memory)
- **Cross-site**: Federated wallet enables cross-site authentication

### **Code Example**
```javascript
// Initialize SDK (happens automatically with 3-line integration)
const lemma = new Lemma({ apiKey: 'your-key' });

// Authenticate user (microsecond performance)
const result = await lemma.authenticate(credentialData);
console.log('Authenticated:', result.verified); // ~5µs response

// Check existing credentials
const status = await lemma.checkCredentials();
if (status.hasValidCredentials) {
  console.log('User has valid authentication');
}

// Background authentication (automatic)
lemma.on('authentication-update', (result) => {
  console.log('Background auth result:', result.verified);
});
```

---

## 🔄 **Process Interaction**

### **Typical User Journey**

1. **First Visit** (VERIFICATION):
   ```
   User visits site → No credentials → Redirect to verification →
   Complete Stripe KYC → Receive identity lemma → Store in wallet
   ```

2. **Subsequent Visits** (AUTHENTICATION):
   ```
   User visits site → SDK checks wallet → Validate credential (~5µs) →
   Instant access granted → Background sync updates
   ```

3. **Cross-Site Access** (AUTHENTICATION):
   ```
   User visits partner site → SDK checks wallet → 
   If cached: validate locally (~5µs) →
   If not cached: fetch from network + cache → validate (~5µs) →
   Instant access granted
   ```

### **Performance Comparison**

| Process | Location | Time | Network | Frequency |
|---------|----------|------|---------|-----------|
| **🔐 Verification** | Server API | ~500ms | Required | Once per user |
| **⚡ Authentication** | Client SDK | ~5µs | Optional | Every access |

---

## 🛡️ **Security Model**

### **Verification Security**
- **Stripe KYC**: Document verification + liveness detection
- **Ed25519 Signatures**: Cryptographic proof of credential authenticity
- **Network Authority**: Federated trust model with shared keys
- **PPID Generation**: Privacy-preserving user identifiers per origin

### **Authentication Security**
- **Offline Validation**: No network calls = no network attacks
- **Cryptographic Proofs**: Ed25519 signature validation
- **Revocation Checking**: OPRF+Bloom filter for instant revocation detection
- **Cross-Tab Sync**: Real-time credential updates across browser tabs

---

## 🎯 **Developer Benefits**

### **Clear Separation of Concerns**
- **Backend APIs**: Handle verification and credential issuance
- **Frontend SDK**: Handle authentication and access control
- **No Confusion**: Distinct methods for distinct purposes

### **Optimal Performance**
- **Verification**: Acceptable latency for one-time setup
- **Authentication**: Microsecond performance for ongoing access
- **Scalability**: Authentication scales infinitely (offline)

### **Easy Integration**
- **3-Line Setup**: Automatic handling of both processes
- **Manual Control**: Separate APIs for custom implementations
- **Clear Documentation**: No ambiguity about when to use what

---

## 📚 **Quick Reference**

### **Use VERIFICATION when:**
- ✅ User needs new identity credentials
- ✅ First-time user onboarding
- ✅ Credential renewal/re-verification
- ✅ Security incident requires re-verification

### **Use AUTHENTICATION when:**
- ✅ Checking if user has access
- ✅ Validating existing credentials
- ✅ Cross-site access control
- ✅ Background security checks
- ✅ Real-time access decisions

### **API Endpoints**

**Verification (Server-side)**:
- `POST /api/sdk/start-identity-verification`
- `POST /api/sdk/complete-identity-verification`

**Authentication (Client-side)**:
- `lemma.authenticate(credential)`
- `lemma.checkCredentials()`
- `lemma.on('authentication-update', callback)`

This clear distinction ensures developers understand exactly when and how to use each process for optimal security and performance.
