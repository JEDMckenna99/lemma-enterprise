# OPRF WebAssembly Deployment Guide

**Zero-Knowledge Revocation Checking with Client-Side OPRF**

---

## 🎯 **WHAT THIS ENABLES:**

**Complete privacy-preserving revocation system:**

1. **Client blinds** credential ID locally (WebAssembly)
2. **Server evaluates** blinded point (can't see credential ID)
3. **Client unblinds** response locally (WebAssembly)
4. **Client checks** OPRF output against Bloom filter (local)

**Result:** Server learns nothing about which credential is being checked!

---

## 📦 **COMPONENTS:**

### **Rust WASM Module** (`lemma-crypto/src/wasm_bindings.rs`)
- `WasmOPRFClient` - Client-side blinding/unblinding
- `WasmBloomFilter` - Cascaded Bloom filter for revocation checking
- `WasmRevocationChecker` - Complete integrated flow

### **JavaScript Wrapper** (`static/js/lemma-oprf-wasm.js`)
- `LemmaOPRF` class - High-level API for developers
- Async initialization
- Automatic Bloom filter caching

### **Python Server API** (`api/oprf_evaluation.py`)
- `/api/oprf/evaluate` - Evaluate single blinded point
- `/api/oprf/batch-evaluate` - Batch evaluation
- `/api/oprf/server-info` - Server status

### **Bloom Filter API** (`api/revocation_api.py`)
- `/api/revocation/bloom-filter` - Returns serialized Bloom filter bytes
- Built with `PyCascadedBloomFilter` from Rust

---

## 🔨 **BUILD INSTRUCTIONS:**

### **Step 1: Install wasm-pack**

```bash
# Install wasm-pack (if not already installed)
cargo install wasm-pack
```

### **Step 2: Build WASM Module**

```bash
# From lemma-crypto directory
cd lemma-crypto
chmod +x build-wasm.sh
./build-wasm.sh
```

**Output:**
- `static/wasm/lemma-oprf.js` - JavaScript bindings (~50KB)
- `static/wasm/lemma-oprf_bg.wasm` - WASM binary (~200KB, ~60KB gzipped)

### **Step 3: Rebuild Python Module (with OPRF + Bloom Filter)**

```bash
# From project root
pip install -e ./lemma-crypto

# Verify OPRF server works
python -c "from lemma_crypto import PyOPRFServer, PyCascadedBloomFilter; print('✅ OPRF modules loaded')"
```

### **Step 4: Deploy to Heroku**

```bash
git add lemma-crypto/src/minimal_python.rs
git add lemma-crypto/src/wasm_bindings.rs
git add api/oprf_evaluation.py
git add api/revocation_api.py
git add static/js/lemma-oprf-wasm.js
git add static/wasm/lemma-oprf.js
git add static/wasm/lemma-oprf_bg.wasm

git commit -m "Add OPRF WebAssembly for client-side zero-knowledge revocation checking"
git push heroku heroku-deploy:main
```

---

## 🧪 **TESTING:**

### **Test 1: OPRF Server Endpoint**

```bash
# Test server-side OPRF evaluation
curl -X POST https://lemma.id/api/oprf/evaluate \
  -H "Content-Type: application/json" \
  -d '{"blinded": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}'

# Expected response:
# {
#   "success": true,
#   "evaluated": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
# }
```

### **Test 2: Client-Side WASM OPRF**

```javascript
// In browser console on https://lemma.id
import { LemmaOPRF } from '/static/js/lemma-oprf-wasm.js';

// Initialize OPRF module
const oprf = await LemmaOPRF.init();

// Load Bloom filter
await oprf.loadBloomFilter();

// Check if credential is revoked (zero-knowledge!)
const isRevoked = await oprf.checkRevocation('cred_test_12345');
console.log('Credential revoked?', isRevoked);
```

### **Test 3: Bloom Filter API**

```bash
# Get Bloom filter with serialized bytes
curl https://lemma.id/api/revocation/bloom-filter

# Expected response:
# {
#   "success": true,
#   "filter_type": "global_cascaded",
#   "count": 5,
#   "filter_bytes": "base64-encoded cascaded Bloom filter",
#   "filter_size_bytes": 1234
# }
```

---

## 🔄 **INTEGRATION INTO WALLET:**

Update `static/js/lemma-wallet.js` to use WASM OPRF:

```javascript
// In LemmaWallet class

async init() {
    // ... existing initialization ...
    
    // Initialize OPRF module for revocation checking
    try {
        this.oprf = await LemmaOPRF.init();
        await this.oprf.loadBloomFilter();
        console.log('✅ OPRF-based revocation checking enabled');
    } catch (error) {
        console.warn('⚠️ OPRF not available, using legacy revocation check');
        this.oprf = null;
    }
}

async checkRevocation(credentialId) {
    // Use OPRF if available (zero-knowledge)
    if (this.oprf) {
        return await this.oprf.checkRevocation(credentialId);
    }
    
    // Fallback to simple Bloom filter check (no privacy)
    return this.revocationBloomFilter.has(credentialId);
}
```

---

## 📊 **PERFORMANCE TARGETS:**

### **OPRF Operations (Client-Side WASM):**
- **Blind:** <500µs
- **Unblind:** <500µs
- **Total OPRF flow:** <2ms (including network round-trip)

### **Bloom Filter Checks (Client-Side WASM):**
- **Single check:** <10µs
- **Batch check (100 items):** <500µs

### **Complete Revocation Check:**
- **OPRF blind:** 500µs
- **Server evaluation:** 200µs (network)
- **OPRF unblind:** 500µs
- **Bloom filter check:** 10µs
- **Total:** ~1.2ms (acceptable for occasional revocation checks)

---

## 🔐 **PRIVACY GUARANTEES:**

### **What Server Sees:**
- ❌ **Cannot see:** Original credential ID
- ❌ **Cannot see:** Which credential user is checking
- ❌ **Cannot see:** How many credentials user has
- ✅ **Can see only:** A blinded point (random-looking 32 bytes)

### **What Server Can Do:**
- ✅ Evaluate OPRF on blinded point
- ✅ Return evaluated point to client
- ❌ **Cannot reverse-engineer** the credential ID
- ❌ **Cannot correlate** multiple requests from same user

### **Client Privacy:**
- ✅ Blinding happens locally (WASM)
- ✅ Unblinding happens locally (WASM)
- ✅ Bloom filter check happens locally (WASM)
- ✅ **Zero network calls reveal credential information**

---

## 🚀 **DEPLOYMENT CHECKLIST:**

### **Pre-Deployment:**
- [ ] Install `wasm-pack`: `cargo install wasm-pack`
- [ ] Build WASM module: `cd lemma-crypto && ./build-wasm.sh`
- [ ] Rebuild Python module: `pip install -e ./lemma-crypto`
- [ ] Test OPRF server: `python -c "from lemma_crypto import PyOPRFServer; s = PyOPRFServer(); print('OK')"`
- [ ] Test Bloom filter: `python -c "from lemma_crypto import PyCascadedBloomFilter; f = PyCascadedBloomFilter(3, 100, 0.01); print('OK')"`

### **Deploy to Heroku:**
- [ ] Commit all changes
- [ ] Push to Heroku: `git push heroku heroku-deploy:main`
- [ ] Verify OPRF endpoint: `curl -X POST https://lemma.id/api/oprf/evaluate -d '{"blinded":"00..."}'`
- [ ] Verify Bloom filter: `curl https://lemma.id/api/revocation/bloom-filter`
- [ ] Test client-side WASM in browser console

### **Post-Deployment:**
- [ ] Monitor OPRF evaluation performance
- [ ] Monitor Bloom filter size growth
- [ ] Set up Redis caching for Bloom filter bytes
- [ ] Add Bloom filter rebuild on revocation events

---

## 🎯 **MIGRATION PATH:**

### **Phase 1: Legacy Revocation (Current)**
```javascript
// Simple Bloom filter check (no privacy)
isRevoked = bloomFilter.has(credentialId);
```

### **Phase 2: Server-Side OPRF (Transition)**
```javascript
// Server-side OPRF blinding (privacy but server sees IDs during transition)
const response = await fetch('/api/oprf/blind-and-check', {
    body: JSON.stringify({ credential_id: credentialId })
});
```

### **Phase 3: Client-Side OPRF via WASM (Ultimate Goal)**
```javascript
// Full zero-knowledge revocation checking
const oprf = await LemmaOPRF.init();
const isRevoked = await oprf.checkRevocation(credentialId);
// Server learns NOTHING about credential ID!
```

---

## 📝 **USAGE EXAMPLE (Complete Flow):**

```javascript
// Import OPRF module
import { LemmaOPRF } from '/static/js/lemma-oprf-wasm.js';

// Initialize (one-time setup)
const oprf = await LemmaOPRF.init();
await oprf.loadBloomFilter(); // Downloads ~60KB gzipped

// Check revocation for any credential (zero-knowledge)
const credentials = [
    'cred_abc123',
    'cred_def456',
    'cred_ghi789'
];

for (const credId of credentials) {
    const isRevoked = await oprf.checkRevocation(credId);
    console.log(`${credId}: ${isRevoked ? 'REVOKED ❌' : 'VALID ✅'}`);
}

// Bloom filter stats
const stats = oprf.getBloomFilterStats();
console.log('Bloom filter:', stats);
// Output: { levels: 3, memory_bytes: 12345, simd_optimized: true }
```

---

## 🔧 **TROUBLESHOOTING:**

### **Issue: WASM fails to load**
```
Error: Failed to fetch WASM module
```
**Solution:** Check that `static/wasm/lemma-oprf_bg.wasm` exists and MIME type is `application/wasm`

### **Issue: OPRF evaluation fails**
```
Error: Server OPRF evaluation failed
```
**Solution:** Check that Python module has `PyOPRFServer` class:
```bash
python -c "from lemma_crypto import PyOPRFServer; print(PyOPRFServer)"
```

### **Issue: Bloom filter not loading**
```
Error: No Bloom filter available
```
**Solution:** Check API response includes `filter_bytes`:
```bash
curl https://lemma.id/api/revocation/bloom-filter | jq '.filter_bytes'
```

---

## 🎉 **SUCCESS CRITERIA:**

When fully deployed, you should see:

**Browser Console:**
```
✅ Lemma OPRF WASM initialized
📦 Loading global Bloom filter...
✅ Bloom filter loaded: 5 revocations, 1234 bytes
🔐 Blinded credential ID: a1b2c3...
📡 OPRF evaluated: d4e5f6...
🔓 OPRF output length: 32
✅ Revocation check complete: NOT REVOKED
```

**Server Logs:**
```
✅ OPRF server initialized
📡 OPRF evaluated: a1b2c3... -> d4e5f6...
✅ Built Bloom filter: 1234 bytes
```

**Zero Server Knowledge:**
- Server never sees `credentialId`
- Server only evaluates random-looking blinded points
- Full privacy guarantee achieved!

---

## 📚 **ADDITIONAL RESOURCES:**

- `lemma-crypto/src/wasm_bindings.rs` - Rust WASM implementation
- `lemma-crypto/src/oprf.rs` - Core OPRF algorithms
- `lemma-crypto/src/bloom.rs` - Cascaded Bloom filter
- `static/js/lemma-oprf-wasm.js` - JavaScript wrapper
- `api/oprf_evaluation.py` - Server-side evaluation API

---

## 🚀 **NEXT STEPS AFTER DEPLOYMENT:**

1. **Monitor performance** - Track OPRF evaluation latency
2. **Optimize Bloom filter** - Tune parameters based on revocation count
3. **Add caching** - Cache Bloom filter in Redis with TTL
4. **Add monitoring** - Track OPRF usage, Bloom filter size
5. **Add metrics** - Dashboard for OPRF performance


