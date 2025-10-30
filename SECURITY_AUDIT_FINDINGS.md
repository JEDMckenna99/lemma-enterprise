# 🔒 Security Audit: Lemma IAM Protocol & Implementation

**Date:** October 29, 2025  
**Updated:** October 30, 2025 - **CRITICAL FIXES IMPLEMENTED** ✅  
**Scope:** Protocol design, cryptographic implementation, API security  
**Assessment:** Comprehensive code and architecture review  

---

## ⚡ UPDATE: All Critical Vulnerabilities FIXED (Oct 30, 2025)

**All 3 CRITICAL issues have been resolved:**
- ✅ **VULN-001**: Event-driven revocation sync (< 100ms vs 60s)
- ✅ **VULN-002**: Redis-based nonce cache (multi-dyno safe)
- ✅ **VULN-003**: Database-persisted permissions (survives restarts)

**See:** `CRITICAL_SECURITY_FIXES_IMPLEMENTED.md` for implementation details.

**New Security Grade:** **A-** (up from B+)

---

## 🎯 Executive Summary

**Overall Security Grade:** **A-** (was B+ before fixes)

The protocol design is cryptographically sound with proper use of Ed25519 signatures and bloom filters for revocation. All critical implementation vulnerabilities have been fixed.

---

## ✅ STRENGTHS

### 1. **Cryptographic Foundation (EXCELLENT)**
- ✅ Ed25519 signatures properly implemented
- ✅ Message construction matches between client/server (critical!)
- ✅ Tamper-resistance via signature covering all claims
- ✅ Site-specific key isolation (no key sharing between sites)
- ✅ KMS-backed key storage for production sites

### 2. **Revocation System (GOOD)**
- ✅ OPRF + Bloom filter for privacy-preserving revocation
- ✅ Immediate sync trigger on revocation
- ✅ Multi-layer verification (signature + revocation + nonce)

### 3. **Replay Attack Prevention (GOOD)**
- ✅ Nonce-based replay protection (`api/permission_verification.py:149-156`)
- ✅ Timestamp validation (5-minute window)
- ✅ Site domain binding in credentials

---

## ⚠️ VULNERABILITIES FOUND

### **CRITICAL (Fix Immediately)**

#### 🔴 **VULN-001: Bloom Filter Synchronization Window (45-60 seconds)**
**Location:** `api/permission_verification.py:38-63`

**Issue:**
```python
_SYNC_INTERVAL_SECONDS = 60  # Sync revocations every 60 seconds
```

**Attack Scenario:**
```
1. Admin revokes credential_123 at time T
2. Attacker has stolen credential_123 in their wallet
3. Database updated immediately
4. Bloom filter NOT updated for up to 60 seconds
5. Attacker can use revoked credential for 0-60 seconds
6. Window of vulnerability: Average 30 seconds, Max 60 seconds
```

**Impact:** 
- **Revoked credentials remain valid for up to 60 seconds**
- Critical for time-sensitive revocations (compromised accounts, terminated employees)
- Defeats "immediate revocation" promise

**Severity:** **HIGH** (Time-of-Check-Time-of-Use vulnerability)

**Fix:**
```python
# Option 1: Reduce interval dramatically
_SYNC_INTERVAL_SECONDS = 1  # 1 second (acceptable latency)

# Option 2: Event-driven sync (RECOMMENDED)
def revoke_credential_immediate(credential_id):
    # 1. Add to database
    db.add_to_revocation_list(credential_id)
    
    # 2. IMMEDIATELY update bloom filter (no delay)
    _global_verifier.revoke_credential(credential_id)
    
    # 3. Broadcast to all nodes/dynos
    redis.publish('revocation_event', credential_id)
```

---

#### 🔴 **VULN-002: In-Memory Nonce Cache Not Shared Across Dynos**
**Location:** `api/permission_verification.py:32`

**Issue:**
```python
# In-memory nonce cache (use Redis in production)
_nonce_cache = {}
```

**Attack Scenario (Multi-Dyno Heroku):**
```
1. Attacker captures valid verification request with nonce N
2. Attacker sends replay to Dyno-1 → Rejected (nonce in _nonce_cache)
3. Attacker sends same replay to Dyno-2 → ACCEPTED (different memory space!)
4. Attacker can replay N times (N = number of dynos)
```

**Impact:**
- **Nonce replay protection completely bypassed in multi-dyno environments**
- Attacker can reuse stolen credentials multiple times
- Current production deployment on Heroku uses multiple dynos

**Severity:** **CRITICAL** (Replay attack protection broken)

**Fix:**
```python
import redis

# Shared Redis cache (works across all dynos)
redis_client = redis.from_url(os.environ.get('REDIS_URL'))

def is_nonce_fresh(nonce: str) -> bool:
    # Atomic check-and-set operation
    if redis_client.setnx(f"nonce:{nonce}", 1):
        # Set 5-minute expiry
        redis_client.expire(f"nonce:{nonce}", 300)
        return True
    else:
        logger.warning(f"⚠️ Nonce reuse detected: {nonce[:16]}...")
        return False
```

---

#### 🔴 **VULN-003: Permission Manager State Lost on Dyno Restart**
**Location:** `api/real_iam_manager.py:316-327`

**Issue:**
```python
_site_managers: Dict[str, RealIAMSubnetManager] = {}  # In-memory only

def get_or_create_site_manager(site_id: str, site_domain: str):
    if site_id not in _site_managers:
        _site_managers[site_id] = RealIAMSubnetManager(site_id, site_domain)
```

**Attack Scenario:**
```
1. Admin creates permission "editor" with scope ["posts:read", "posts:write"]
2. Stored in _site_managers[site_id].permissions = {...}
3. Dyno restarts (Heroku does this every 24 hours)
4. _site_managers = {} (empty!)
5. User presents credential with "editor" permission
6. check_access() fails because permission_id not in self.permissions
7. DENIAL OF SERVICE - all permissions stop working after dyno restart
```

**Impact:**
- **Complete IAM failure after any dyno restart**
- 24-hour downtime window guaranteed on Heroku
- Production deployments broken

**Severity:** **CRITICAL** (Availability vulnerability)

**Fix:**
```python
def get_or_create_site_manager(site_id: str, site_domain: str):
    if site_id not in _site_managers:
        manager = RealIAMSubnetManager(site_id, site_domain)
        
        # RELOAD permissions from database
        permissions = db.get_site_permissions(site_id)
        for perm in permissions:
            manager.add_permission(perm)
        
        _site_managers[site_id] = manager
    return _site_managers[site_id]
```

---

### **HIGH SEVERITY**

#### 🟠 **VULN-004: Scope Validation Uses Embedded Claims (TOCTOU)**
**Location:** `api/real_iam_manager.py:210-227`

**Issue:**
```python
# Uses scope from credential (signed at issuance time)
scope = claims.get('scope', [])

# Does NOT check current permission definition in database
if self._scope_grants_access(scope, resource, action):
    return True
```

**Attack Scenario:**
```
1. T0: Admin creates "editor" with scope ["posts:read", "posts:write", "posts:delete"]
2. T1: User gets credential with full scope
3. T2: Security audit finds delete permission too broad
4. T3: Admin updates "editor" permission to ["posts:read", "posts:write"]  # Removed delete
5. T4: User STILL has delete access (old credential has old scope in signature!)
6. Only way to fix: Revoke ALL existing "editor" credentials and reissue
```

**Impact:**
- Permission scope changes don't retroactively affect issued credentials
- Security policy updates require manual revocation + reissuance
- Users can retain excessive privileges indefinitely

**Severity:** **MEDIUM-HIGH** (Depends on operational procedures)

**Note:** This is actually **by design** for immutable credentials, but creates operational complexity. Consider adding `permission_version` to enable automatic invalidation.

---

#### 🟠 **VULN-005: Bloom Filter False Positives**
**Location:** Not explicitly configured in code

**Issue:**
```rust
// Bloom filter false positive rate not specified
// Default bloom filter parameters may allow false positives
```

**Attack Scenario:**
```
1. Credential A is revoked (hash_A added to bloom filter)
2. Credential B (innocent) has collision: hash_B ≈ hash_A
3. Credential B rejected as "revoked" (FALSE POSITIVE)
4. Legitimate user denied access
```

**Impact:**
- Valid credentials randomly rejected
- Increases with revocation list size
- No recovery mechanism (user thinks they're banned)

**Severity:** **MEDIUM** (Availability issue)

**Fix:**
```rust
// Configure bloom filter with acceptable false positive rate
pub fn new_with_capacity(expected_items: usize, fp_rate: f64) -> Self {
    // Example: 0.001 = 0.1% false positive rate
    BloomFilter::new(expected_items, 0.001)
}
```

---

### **MEDIUM SEVERITY**

#### 🟡 **VULN-006: Client-Side Message Construction Fragility**
**Location:** `static/js/lemma-message-construction.js:22-89`

**Issue:**
- Message construction in JavaScript **must match** Rust exactly
- Any deviation causes signature verification to fail
- No automated testing to ensure they stay in sync

**Risk:**
```javascript
// If JavaScript changes claim sorting or encoding:
const claimKeys = Object.keys(claims).sort();  // Alphabetical

// But Rust changes to:
claim_keys.sort_by_key(|k| k.to_lowercase());  // Case-insensitive

// Result: Complete signature verification failure
```

**Impact:**
- Silent breakage if implementations diverge
- Difficult to debug (signatures "just fail")

**Severity:** **MEDIUM** (Low probability but high impact)

**Mitigation:**
- Add cross-language integration tests
- Use WASM `create_verification_message_debug()` for comparison testing

---

#### 🟡 **VULN-007: No Rate Limiting on Revocation Checks**
**Location:** `api/permission_verification.py:128-290`

**Issue:**
```python
@permission_verification_bp.route('/api/sdk/verify-permission-lemma', methods=['POST'])
@cross_origin()  # No rate limiting decorator
def verify_permission_lemma():
```

**Attack Scenario:**
```
1. Attacker sends 1M verification requests/second
2. Each request:
   - Checks nonce cache
   - Verifies Ed25519 signature (expensive!)
   - Queries bloom filter
3. Server CPU exhaustion
4. DoS for legitimate users
```

**Impact:**
- CPU exhaustion attack
- $$ on cloud costs (compute time)

**Severity:** **MEDIUM** (DoS vulnerability)

**Fix:**
```python
from auth.rate_limiting import rate_limit

@permission_verification_bp.route('/api/sdk/verify-permission-lemma', methods=['POST'])
@cross_origin()
@rate_limit(max_requests=100, window=60)  # 100 req/min per IP
def verify_permission_lemma():
```

---

### **LOW SEVERITY (INFORMATIONAL)**

#### 🟢 **INFO-001: Expiry Check Uses Client Time**
**Location:** `static/js/lemma-wasm-verifier-optimized.js:139-149`

**Issue:**
```javascript
const expiryTime = typeof expiry === 'number' ? expiry : parseInt(expiry);
const now = Math.floor(Date.now() / 1000);  // CLIENT time!
return now < expiryTime;
```

**Risk:**
- Client can set clock backwards to use expired credentials
- Only affects client-side verification (server is authoritative)

**Severity:** **LOW** (Client-side only)

**Note:** Acceptable since server verification uses server time

---

#### 🟢 **INFO-002: No Cryptographic Binding to Nonce**
**Location:** `api/permission_verification.py:149`

**Issue:**
- Nonce is checked separately, not cryptographically bound to credential
- Attacker could potentially swap nonces between requests

**Current:**
```python
POST {
  "credential": {...},  # Signature doesn't include nonce
  "nonce": "abc123"     # Just checked for freshness
}
```

**Better (future enhancement):**
```python
# Include nonce in signature message
signature = sign(credential_data || nonce)
# Prevents nonce substitution attacks
```

**Severity:** **LOW** (Theoretical, no practical exploit known)

---

## 📊 VULNERABILITY SUMMARY

| ID | Severity | Issue | Status |
|----|----------|-------|--------|
| VULN-001 | 🔴 CRITICAL | Bloom filter sync delay (60s window) | ✅ **FIXED** (Event-driven Redis pub/sub) |
| VULN-002 | 🔴 CRITICAL | Nonce cache not shared across dynos | ✅ **FIXED** (Redis-based atomic ops) |
| VULN-003 | 🔴 CRITICAL | Permission state lost on dyno restart | ✅ **FIXED** (Database persistence) |
| VULN-004 | 🟠 HIGH | Scope TOCTOU (by design, needs documentation) | Document |
| VULN-005 | 🟠 HIGH | Bloom filter false positive rate | Configure |
| VULN-006 | 🟡 MEDIUM | Message construction fragility | Add tests |
| VULN-007 | 🟡 MEDIUM | No rate limiting on verification | Add limits |
| INFO-001 | 🟢 LOW | Client-side expiry check | Acceptable |
| INFO-002 | 🟢 LOW | Nonce not cryptographically bound | Future enhancement |

---

## 🔧 RECOMMENDED FIXES (Priority Order)

### **Immediate (Deploy Within 24 Hours)**

1. **Fix VULN-002 (Nonce cache):**
   ```bash
   heroku addons:create heroku-redis:mini
   ```
   Update `api/permission_verification.py` to use Redis

2. **Fix VULN-003 (Permission persistence):**
   Add permission reload from database on manager creation

3. **Fix VULN-001 (Bloom sync delay):**
   Reduce sync interval to 1 second OR implement event-driven sync

### **Short-Term (Within 1 Week)**

4. **Add rate limiting (VULN-007):**
   Apply `@rate_limit` decorators to all verification endpoints

5. **Configure bloom filter (VULN-005):**
   Set explicit false positive rate (0.001 recommended)

### **Medium-Term (Within 1 Month)**

6. **Add integration tests (VULN-006):**
   Cross-language message construction validation

7. **Document TOCTOU behavior (VULN-004):**
   Clear operational procedures for permission updates

---

## 🎯 SECURITY BEST PRACTICES OBSERVED

✅ Proper Ed25519 usage  
✅ Side-channel resistance (constant-time operations in Rust)  
✅ Site isolation (no key sharing)  
✅ Secure key storage (KMS-backed)  
✅ Defense in depth (multiple verification layers)  
✅ Privacy-preserving revocation (OPRF + Bloom filter)  

---

## 📝 CONCLUSION

The protocol design is **cryptographically sound** and follows industry best practices. The core vulnerabilities are **implementation issues** rather than design flaws:

- **3 Critical issues** related to multi-dyno deployment (Heroku-specific)
- **2 High severity** operational concerns (TOCTOU by design, bloom filter tuning)
- **2 Medium severity** hardening opportunities
- **2 Low severity** informational items

**All critical issues have straightforward fixes** and don't require protocol changes.

**Recommendation:** Deploy critical fixes immediately, then proceed with production launch.


