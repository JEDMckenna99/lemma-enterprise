# 🧪 Advanced Wallet Manual Testing Guide

## 🎯 **Testing Overview**
Manual testing guide for the advanced wallet recovery system deployed on Heroku. Tests all enterprise-grade features including Sybil prevention, wallet recovery, multi-device sync, and security monitoring.

**Production URL**: https://lemma-enterprise-0f6ba17076c1.herokuapp.com

## 📋 **Manual Testing Checklist**

### **🔐 Test 1: Pairwise Tagging (Sybil Prevention)**

#### **What This Tests:**
- HMAC-based uniqueness enforcement
- One-human-one-account per RP
- Server-side tag generation

#### **Steps:**
1. **Open Terminal/Command Prompt**
2. **Test Basic Tag Generation:**
   ```bash
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/issuer/pairwise-tag \
     -H "Content-Type: application/json" \
     -d '{
       "rp_id": "your-test-site.com",
       "wallet_type": "integrated_advanced"
     }'
   ```

3. **Expected Result:**
   ```json
   {
     "success": true,
     "pairwise_tag": "8bbd2601c1d72975...",
     "rp_id": "your-test-site.com",
     "tag_method": "hmac_sha256",
     "uniqueness_enforced": true
   }
   ```

4. **Test Tag Consistency:**
   - Run the same command again
   - Should get the **same tag** (proves deterministic generation)

5. **Test Different RP:**
   ```bash
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/issuer/pairwise-tag \
     -H "Content-Type: application/json" \
     -d '{
       "rp_id": "different-site.com",
       "wallet_type": "integrated_advanced"
     }'
   ```
   - Should get **different tag** (proves RP isolation)

#### **✅ Success Criteria:**
- ✅ Tags generate successfully
- ✅ Same RP = same tag (deterministic)
- ✅ Different RP = different tag (isolated)

---

### **🔐 Test 2: Recovery Vault Service**

#### **What This Tests:**
- Encrypted envelope storage
- VID-based privacy lookup
- Counter rollback protection
- Rate limiting

#### **Steps:**

1. **Test Vault Health:**
   ```bash
   curl https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/health
   ```
   
   **Expected Result:**
   ```json
   {
     "status": "healthy",
     "service": "recovery_vault",
     "version": "1.0.0"
   }
   ```

2. **Test Envelope Storage:**
   ```bash
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/put \
     -H "Content-Type: application/json" \
     -d '{
       "vid": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
       "ciphertext": "48656c6c6f20576f726c64",
       "counter": 1,
       "aad": "746573745f616164"
     }'
   ```

3. **Test Envelope Retrieval:**
   ```bash
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/get \
     -H "Content-Type: application/json" \
     -d '{
       "vid": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
     }'
   ```

4. **Test Rollback Protection:**
   ```bash
   # Try to store with same counter (should fail)
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/put \
     -H "Content-Type: application/json" \
     -d '{
       "vid": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
       "ciphertext": "48656c6c6f20576f726c64",
       "counter": 1,
       "aad": "746573745f616164"
     }'
   ```
   **Expected**: Error about rollback detection

#### **✅ Success Criteria:**
- ✅ Vault health shows "healthy"
- ✅ Envelope stores successfully
- ✅ Envelope retrieves with same data
- ✅ Rollback protection rejects duplicate counters

---

### **🔄 Test 3: Device Transfer System**

#### **What This Tests:**
- Device-assisted wallet transfer
- HPKE rewrapping
- Transfer token security

#### **Steps:**

1. **Initialize Transfer:**
   ```bash
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/transfer/init \
     -H "Content-Type: application/json" \
     -d '{
       "device_auth": "test_device_signature_12345",
       "vid": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
     }'
   ```

2. **Expected Result:**
   ```json
   {
     "success": true,
     "transfer_token": "random_token_here",
     "expires_in_seconds": 300,
     "next_step": "Use transfer_token in /vault/transfer/complete"
   }
   ```

3. **Complete Transfer (use token from step 1):**
   ```bash
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/transfer/complete \
     -H "Content-Type: application/json" \
     -d '{
       "transfer_token": "TOKEN_FROM_STEP_1",
       "new_device_pubkey": "fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321"
     }'
   ```

#### **✅ Success Criteria:**
- ✅ Transfer init returns valid token
- ✅ Token expires in 5 minutes (300 seconds)
- ✅ Transfer complete succeeds with rewrapping

---

### **📱 Test 4: Advanced Wallet UI**

#### **What This Tests:**
- Advanced wallet user interface
- Real-time feature monitoring
- Integrated wallet functionality

#### **Steps:**

1. **Open Advanced Wallet Page:**
   - Navigate to: https://lemma-enterprise-0f6ba17076c1.herokuapp.com/advanced-wallet

2. **Check Page Elements:**
   - ✅ Page loads without errors
   - ✅ "Advanced Lemma Wallet" header visible
   - ✅ Wallet status section shows initialization
   - ✅ Performance metrics section present
   - ✅ Advanced features section with 4 features
   - ✅ RP integration demo section
   - ✅ Device transfer demo section

3. **Test RP Integration Demo:**
   - Enter "test-manual.com" in RP ID field
   - Click "Test RP Signup" button
   - Check browser console for wallet operations

4. **Test Device Transfer Demo:**
   - Click "Initialize Transfer" button
   - Check for transfer session creation
   - Click "Test Vault Backup" button

#### **✅ Success Criteria:**
- ✅ Page loads completely
- ✅ All sections visible and functional
- ✅ Interactive demos work
- ✅ Console shows wallet operations

---

### **🛡️ Test 5: Security Monitoring**

#### **What This Tests:**
- Real-time security monitoring
- Failed attempt tracking
- Rate limiting

#### **Steps:**

1. **Check Security Status:**
   ```bash
   curl https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/security
   ```

2. **Test Rate Limiting:**
   ```bash
   # Send multiple rapid requests (should trigger rate limiting)
   for i in {1..15}; do
     curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/get \
       -H "Content-Type: application/json" \
       -d '{"vid": "test_vid_for_rate_limiting"}' &
   done
   wait
   ```

3. **Check Vault Statistics:**
   ```bash
   curl https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/stats
   ```

#### **✅ Success Criteria:**
- ✅ Security monitoring shows "healthy"
- ✅ Rate limiting triggers after 10 requests
- ✅ Statistics show failed attempts
- ✅ Monitoring remains active

---

### **⚡ Test 6: Performance Validation**

#### **What This Tests:**
- Verification speed preservation
- Wallet operation overhead
- Overall system performance

#### **Steps:**

1. **Test Baseline Verification:**
   ```bash
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/sdk/complete-identity-verification \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer demo-performance-test" \
     -d '{
       "user_id": "manual_test_user",
       "session_id": "manual_test_session",
       "enable_rust_engine": true
     }'
   ```

2. **Check Response Time:**
   - Look for `verification_time_us` in response
   - Should be <500μs on cloud infrastructure

3. **Test Wallet Operations:**
   - Use browser developer tools
   - Navigate to `/advanced-wallet`
   - Monitor console for timing information

#### **✅ Success Criteria:**
- ✅ Verification time <500μs
- ✅ Wallet operations <20μs
- ✅ Total overhead <20%

---

### **🌐 Test 7: Browser Integration**

#### **What This Tests:**
- Client-side wallet functionality
- JavaScript integration
- Local crypto operations

#### **Steps:**

1. **Open Browser Developer Tools:**
   - Navigate to: https://lemma-enterprise-0f6ba17076c1.herokuapp.com/advanced-wallet
   - Open DevTools (F12)
   - Go to Console tab

2. **Test Wallet Initialization:**
   ```javascript
   // In browser console:
   const wallet = new LemmaIntegratedWallet({
     debug: true,
     enableAdvancedFeatures: true
   });
   
   wallet.initialize().then(result => {
     console.log('Wallet init result:', result);
   });
   ```

3. **Test RP Key Derivation:**
   ```javascript
   // In browser console:
   wallet.deriveRPKey('manual-test.com').then(key => {
     console.log('RP key derived:', key.length, 'bytes');
   });
   ```

4. **Test DID Generation:**
   ```javascript
   // In browser console:
   wallet.generateRPDID('manual-test.com').then(did => {
     console.log('RP DID:', did);
   });
   ```

#### **✅ Success Criteria:**
- ✅ Wallet initializes without errors
- ✅ RP keys derive successfully
- ✅ DIDs generate properly
- ✅ Console shows timing information

---

### **📊 Test 8: End-to-End Flow**

#### **What This Tests:**
- Complete user signup flow
- Uniqueness enforcement
- Recovery capability

#### **Steps:**

1. **Simulate User Signup:**
   ```bash
   # Step 1: Get pairwise tag
   TAG_RESPONSE=$(curl -s -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/issuer/pairwise-tag \
     -H "Content-Type: application/json" \
     -d '{"rp_id": "manual-test-rp.com", "wallet_type": "integrated_advanced"}')
   
   echo "Tag response: $TAG_RESPONSE"
   ```

2. **Extract and Validate Tag:**
   ```bash
   # Step 2: Validate uniqueness
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/issuer/validate-uniqueness \
     -H "Content-Type: application/json" \
     -d '{
       "pairwise_tag": "PASTE_TAG_FROM_STEP_1",
       "rp_id": "manual-test-rp.com"
     }'
   ```

3. **Test Wallet Backup:**
   ```bash
   # Step 3: Backup wallet envelope
   curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/put \
     -H "Content-Type: application/json" \
     -d '{
       "vid": "manual_test_vid_1234567890abcdef1234567890abcdef1234567890abcdef",
       "ciphertext": "7b2276657273696f6e223a312c22636f756e746572223a312c226d61737465725f73656564223a22746573745f73656564227d",
       "counter": 1,
       "aad": "6d616e75616c5f746573745f616164"
     }'
   ```

#### **✅ Success Criteria:**
- ✅ Pairwise tag generates successfully
- ✅ Tag validation confirms uniqueness
- ✅ Wallet backup stores successfully
- ✅ All operations complete without errors

---

## 🎯 **Quick Testing Commands**

### **One-Line Health Check:**
```bash
curl https://lemma-enterprise-0f6ba17076c1.herokuapp.com/vault/health && echo
```

### **One-Line Feature Test:**
```bash
curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/issuer/pairwise-tag \
  -H "Content-Type: application/json" \
  -d '{"rp_id": "quick-test.com", "wallet_type": "manual_test"}' && echo
```

### **One-Line UI Test:**
```bash
curl -I https://lemma-enterprise-0f6ba17076c1.herokuapp.com/advanced-wallet
```

---

## 📱 **Browser Testing Steps**

### **Test Advanced Wallet UI:**

1. **Navigate to Advanced Wallet:**
   - URL: https://lemma-enterprise-0f6ba17076c1.herokuapp.com/advanced-wallet

2. **Check Page Sections:**
   - ✅ Wallet Status (should show initialization)
   - ✅ Performance Metrics (should show timing data)
   - ✅ Advanced Features (4 features with status indicators)
   - ✅ RP Integration Demo (interactive form)
   - ✅ Device Transfer Demo (transfer buttons)
   - ✅ Wallet Details (cryptographic state)

3. **Test Interactive Features:**
   - Enter "manual-test.com" in RP integration
   - Click "Test RP Signup" 
   - Check console for wallet operations
   - Click "Initialize Transfer"
   - Click "Test Vault Backup"

4. **Check Browser Console:**
   - Open DevTools (F12) → Console
   - Should see wallet initialization logs
   - Should see performance timing data
   - Should see advanced feature status

---

## 🔍 **Troubleshooting Guide**

### **If Pairwise Tagging Returns 404:**
- App may need restart on Heroku
- Try again in 5-10 minutes
- Check if blueprint is registered: Look for "Pairwise Tagging Service registered" in logs

### **If Vault Operations Return 404:**
- Same issue - app restart needed
- Core vault health should still work
- Storage/retrieval endpoints may need time to register

### **If Advanced Wallet UI Doesn't Load:**
- Check URL: `/advanced-wallet` (not `/wallet`)
- Ensure JavaScript is enabled
- Check browser console for errors

### **If Performance Seems Slow:**
- First request is always slower (cold start)
- Subsequent requests should be faster
- Cloud infrastructure adds network latency vs local

---

## 📊 **Expected Performance Benchmarks**

### **Production Performance Targets:**
- **Pairwise Tag Generation**: <50ms (including network)
- **Vault Operations**: <100ms (including network)
- **UI Load Time**: <2 seconds
- **Wallet Operations**: <20μs (client-side)

### **Performance Validation:**
```bash
# Time a pairwise tag request
time curl -X POST https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/issuer/pairwise-tag \
  -H "Content-Type: application/json" \
  -d '{"rp_id": "perf-test.com", "wallet_type": "performance_test"}' \
  > /dev/null 2>&1
```

---

## 🎯 **Complete Manual Test Script**

Save this as `test_advanced_wallet_manual.sh`:

```bash
#!/bin/bash

echo "🧪 ADVANCED WALLET MANUAL TEST SCRIPT"
echo "======================================"

BASE_URL="https://lemma-enterprise-0f6ba17076c1.herokuapp.com"

echo "🔐 Testing Pairwise Tagging..."
curl -X POST $BASE_URL/api/issuer/pairwise-tag \
  -H "Content-Type: application/json" \
  -d '{"rp_id": "manual-script-test.com", "wallet_type": "script_test"}' \
  && echo "✅ Pairwise tagging working" || echo "❌ Pairwise tagging failed"

echo -e "\n🏥 Testing Vault Health..."
curl $BASE_URL/vault/health \
  && echo "✅ Vault health working" || echo "❌ Vault health failed"

echo -e "\n📱 Testing Advanced UI..."
curl -I $BASE_URL/advanced-wallet 2>/dev/null | grep "200 OK" \
  && echo "✅ Advanced UI working" || echo "❌ Advanced UI failed"

echo -e "\n🎯 Manual testing complete!"
echo "Open $BASE_URL/advanced-wallet in browser for interactive testing"
```

Run with: `bash test_advanced_wallet_manual.sh`

---

## 🏆 **Testing Success Criteria**

### **Minimum Success (Core Features):**
- ✅ Pairwise tagging generates tags
- ✅ Vault health returns "healthy"
- ✅ Advanced wallet UI loads

### **Full Success (All Features):**
- ✅ All API endpoints respond correctly
- ✅ Vault storage/retrieval works
- ✅ Device transfer completes
- ✅ Security monitoring active
- ✅ Performance within targets
- ✅ Browser integration functional

### **Enterprise Success (Production Ready):**
- ✅ Rate limiting triggers appropriately
- ✅ Rollback protection prevents attacks
- ✅ Security monitoring detects threats
- ✅ All operations complete under performance targets
- ✅ UI provides real-time status and controls

---

## 💡 **Testing Tips**

1. **Start with simple tests** (health checks) before complex flows
2. **Check browser console** for detailed error messages
3. **Test same operations multiple times** to verify caching and consistency
4. **Try invalid inputs** to test error handling
5. **Monitor timing** to validate performance claims

**Your advanced wallet system is now ready for comprehensive manual testing on production infrastructure!** 🚀
