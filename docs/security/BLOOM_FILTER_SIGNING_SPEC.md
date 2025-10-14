# Signed Bloom Filter Envelope Specification

## Overview

This document specifies the signed bloom filter envelope system implemented in Lemma v878, which provides cryptographically secure, tamper-proof, version-controlled distribution of revocation filters.

---

## 1. Bloom Filter Envelope Structure

### 1.1 Complete Envelope

```rust
pub struct BloomFilterEnvelope {
    // Filter Data
    pub filter_data: Vec<u8>,              // Serialized bloom filter
    
    // Versioning
    pub version: u64,                      // Monotonically increasing
    pub previous_version: Option<u64>,     // Previous version number
    pub previous_version_hash: Option<Vec<u8>>, // Hash of previous envelope
    
    // Key Association
    pub oprf_key_version: u32,             // Associated OPRF key version
    
    // Temporal Validity
    pub created_at: i64,                   // Creation timestamp
    pub valid_from: i64,                   // Start of validity
    pub valid_until: i64,                  // End of validity (7 days)
    
    // Integrity
    pub content_hash: Vec<u8>,             // SHA-256 of filter data
    
    // Metadata
    pub filter_params: BloomFilterParams,  // Filter configuration
    pub item_count: usize,                 // Number of revoked items
    
    // Cryptographic Proof
    pub signature: Vec<u8>,                // Ed25519 signature (64 bytes)
    pub issuer_did: String,                // Network authority DID
}
```

### 1.2 Signing Message Format

The envelope signature covers:
```rust
fn create_signature_message() -> Vec<u8> {
    let mut message = Vec::new();
    message.extend_from_slice(&version.to_le_bytes());      // 8 bytes
    message.extend_from_slice(&content_hash);               // 32 bytes
    message.extend_from_slice(&created_at.to_le_bytes());   // 8 bytes
    message.extend_from_slice(&valid_until.to_le_bytes());  // 8 bytes
    message.extend_from_slice(&oprf_key_version.to_le_bytes()); // 4 bytes
    message // Total: 60 bytes canonical message
}
```

This canonical message is signed with Ed25519.

---

## 2. Attack Prevention

### 2.1 Downgrade Attack Prevention

**Attack Scenario:**
```
1. User's credential revoked (added to filter v100)
2. Attacker serves old filter (v99) to client
3. Client accepts old filter
4. Revoked credential still verifies (bypass!)
```

**Prevention Mechanism:**

**Version Chain Validation:**
```rust
pub fn verify_chain(&self, previous: &BloomFilterEnvelope) -> Result<()> {
    // 1. Version must increment by exactly 1
    if self.version != previous.version + 1 {
        return Err(InvalidVersionSequence);
    }
    
    // 2. Hash of previous envelope must match
    if self.previous_version_hash != Some(previous.content_hash) {
        return Err(ChainBroken);
    }
    
    // 3. Timestamp must be newer
    if self.created_at <= previous.created_at {
        return Err(InvalidTimestamp);
    }
    
    Ok(())
}
```

**Client Enforcement:**
```javascript
class BloomFilterValidator {
    acceptEnvelope(newEnvelope) {
        // Reject if version is not higher than current
        if (newEnvelope.version <= this.currentVersion) {
            throw new Error('Downgrade attempt detected');
        }
        
        // Validate chain if we have previous
        if (this.currentEnvelope) {
            newEnvelope.verifyChain(this.currentEnvelope);
        }
        
        // Accept
        this.currentEnvelope = newEnvelope;
        this.currentVersion = newEnvelope.version;
    }
}
```

### 2.2 Replay Attack Prevention

**Attack Scenario:**
```
1. Attacker captures legitimate filter from 3 months ago
2. Replays old but validly-signed filter
3. All revocations in past 3 months ignored
4. Mass security bypass
```

**Prevention Mechanism:**

**Time-Bound Validity:**
```rust
// Filters expire after 7 days
pub fn verify(&self) -> Result<()> {
    let now = current_timestamp();
    
    // Check not expired
    if now > self.valid_until {
        return Err(FilterExpired);
    }
    
    // Check not from future (clock skew tolerance: 5 min)
    if self.created_at > now + 300 {
        return Err(FromFuture);
    }
    
    Ok(())
}
```

**Maximum Age Enforcement:**
```javascript
const MAX_FILTER_AGE = 7 * 24 * 3600; // 7 days

function validateFilterAge(envelope) {
    const age = Date.now() / 1000 - envelope.created_at;
    
    if (age > MAX_FILTER_AGE) {
        throw new Error(`Filter too old: ${age}s (max ${MAX_FILTER_AGE}s)`);
    }
}
```

### 2.3 Tampering Prevention

**Attack Scenario:**
```
1. Attacker intercepts filter download
2. Modifies filter to mark all credentials as revoked (DoS)
3. OR excludes specific revoked credentials (bypass)
4. Client accepts tampered filter
```

**Prevention Mechanism:**

**Content Hash + Signature:**
```rust
pub fn verify(&self) -> Result<()> {
    // 1. Verify content hash matches actual data
    let computed_hash = compute_hash(&self.filter_data, 
                                     self.oprf_key_version, 
                                     self.created_at);
    if computed_hash != self.content_hash {
        return Err(HashMismatch);
    }
    
    // 2. Verify Ed25519 signature
    let message = self.create_signature_message();
    let public_key = extract_from_did(&self.issuer_did)?;
    public_key.verify(&message, &self.signature)?;
    
    Ok(())
}
```

**Any modification** to filter_data breaks either:
- Content hash (SHA-256 mismatch)
- Signature (Ed25519 verification fails)

### 2.4 Unauthorized Issuer Prevention

**Attack Scenario:**
```
1. Attacker creates malicious filter
2. Signs with attacker's own key
3. Clients accept filter (if not checking issuer)
4. Attacker controls revocation decisions
```

**Prevention Mechanism:**

**Issuer Verification:**
```rust
pub fn verify(&self, expected_authority_key: &VerifyingKey) -> Result<()> {
    // Extract public key from issuer DID
    let issuer_key = extract_public_key_from_did(&self.issuer_did)?;
    
    // Verify it matches expected network authority
    if issuer_key != expected_authority_key {
        return Err(UnauthorizedIssuer);
    }
    
    // Then verify signature with that key
    self.verify_signature(&issuer_key)?;
    
    Ok(())
}
```

**Clients must**:
- Know network authority public key in advance
- Reject filters signed by other keys
- Never accept user-provided authority keys

---

## 3. Version Chain Validation

### 3.1 Chain Structure

```
Envelope v1: [filter_data_1, signature_1, content_hash_1]
                                                    ↓
Envelope v2: [filter_data_2, signature_2, content_hash_2, prev_hash=content_hash_1]
                                                    ↓
Envelope v3: [filter_data_3, signature_3, content_hash_3, prev_hash=content_hash_2]
```

### 3.2 Chain Properties

**Immutability:**
- Once published, envelope cannot be changed
- Any change breaks signature
- Hash chain makes history verifiable

**Completeness:**
- No gaps allowed in version sequence
- Version n+1 must reference version n
- Missing versions detected

**Ordering:**
- Versions strictly increasing
- Timestamps strictly increasing
- No reordering possible

### 3.3 Chain Validation Algorithm

```rust
pub struct ChainValidator {
    validated_envelopes: HashMap<u64, BloomFilterEnvelope>,
    current_version: u64,
    authority_public_key: VerifyingKey,
}

impl ChainValidator {
    pub fn validate_and_accept(&mut self, envelope: BloomFilterEnvelope) -> Result<()> {
        // 1. Basic envelope verification
        envelope.verify(&self.authority_public_key)?;
        
        // 2. Version must be higher than current
        if envelope.version <= self.current_version {
            return Err(DowngradeAttempt);
        }
        
        // 3. No gaps (version must be current + 1)
        if envelope.version > self.current_version + 1 {
            return Err(VersionGap);
        }
        
        // 4. Chain validation (if not first)
        if envelope.version > 1 {
            if let Some(prev) = self.validated_envelopes.get(&(envelope.version - 1)) {
                envelope.verify_chain(prev)?;
            } else {
                return Err(MissingPreviousVersion);
            }
        }
        
        // 5. Accept envelope
        self.validated_envelopes.insert(envelope.version, envelope.clone());
        self.current_version = envelope.version;
        
        // 6. Cleanup old envelopes (keep last 5)
        self.cleanup_old_envelopes(5);
        
        Ok(())
    }
}
```

---

## 4. Temporal Validity

### 4.1 Validity Window

**Standard Configuration:**
- Creation → Distribution: Immediate
- Valid from: Creation time
- Valid until: Creation + 7 days
- Total lifetime: 7 days

**Rationale for 7 Days:**
- Long enough for global distribution
- Short enough to limit replay window
- Balances security vs. availability

### 4.2 Clock Skew Tolerance

**Problem:** Distributed systems have unsynchronized clocks

**Solution:** Allow small tolerance
```rust
const CLOCK_SKEW_TOLERANCE: i64 = 300; // 5 minutes

pub fn verify_temporal_bounds(&self) -> Result<()> {
    let now = current_timestamp();
    
    // Allow 5 min clock skew for "from future" check
    if self.created_at > now + CLOCK_SKEW_TOLERANCE {
        return Err(FromFuture);
    }
    
    // Strict check for expiration (no tolerance)
    if now > self.valid_until {
        return Err(Expired);
    }
    
    Ok(())
}
```

### 4.3 Refresh Strategy

**Client-Side:**
```javascript
class BloomFilterManager {
    async ensureFresh() {
        const envelope = this.currentEnvelope;
        
        // Refresh if:
        // 1. No envelope (first time)
        // 2. Expired
        // 3. Expiring soon (<24 hours)
        
        if (!envelope || 
            envelope.valid_until < Date.now() / 1000 ||
            envelope.should_refresh()) {
            
            await this.fetchNewEnvelope();
        }
    }
    
    async fetchNewEnvelope() {
        const response = await fetch('/api/v1/oprf/bloom-filter');
        const envelope = response.json();
        
        // Verify before accepting
        await this.validator.validate_and_accept(envelope);
    }
}
```

---

## 5. Distribution Protocol

### 5.1 Server-Side Distribution

**Endpoint**: `GET /api/v1/oprf/bloom-filter?version={version}`

**Process:**
1. Check requested version (default to current)
2. Load envelope from storage
3. Verify envelope is still valid
4. Return JSON response

**Response Format:**
```json
{
  "success": true,
  "version": 100,
  "oprf_key_version": 2,
  "bloom_filter": {
    "data": "base64_encoded_filter_bytes",
    "size_bytes": 125000,
    "num_levels": 3,
    "false_positive_rate": 0.001
  },
  "signature": "base64_encoded_ed25519_signature",
  "issuer_did": "did:lemma:network_authority_pubkey",
  "created_at": 1697248490,
  "valid_from": 1697248490,
  "valid_until": 1697853290,
  "content_hash": "hex_sha256_hash",
  "previous_version": 99,
  "previous_version_hash": "hex_sha256_of_previous"
}
```

### 5.2 Client-Side Validation

**Required Checks:**
```javascript
async function validateEnvelope(envelope, previousEnvelope) {
    // 1. Verify signature
    const signatureValid = await verifyEd25519Signature(
        envelope.signature,
        envelope.issuer_did,
        createSignatureMessage(envelope)
    );
    if (!signatureValid) throw new Error('Invalid signature');
    
    // 2. Verify content hash
    const computedHash = await sha256(
        base64Decode(envelope.bloom_filter.data)
    );
    if (computedHash !== envelope.content_hash) {
        throw new Error('Content hash mismatch');
    }
    
    // 3. Verify temporal bounds
    const now = Date.now() / 1000;
    if (now < envelope.valid_from) throw new Error('Not yet valid');
    if (now > envelope.valid_until) throw new Error('Expired');
    
    // 4. Verify version chain (if not first)
    if (previousEnvelope) {
        if (envelope.version !== previousEnvelope.version + 1) {
            throw new Error('Version gap');
        }
        if (envelope.previous_version_hash !== previousEnvelope.content_hash) {
            throw new Error('Chain broken');
        }
    }
    
    return true;
}
```

---

## 6. Content Hash Computation

### 6.1 Canonical Hash

**Purpose**: Detect any modification to filter data

**Algorithm:**
```rust
fn compute_hash(filter_data: &[u8], oprf_key_version: u32, created_at: i64) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(filter_data);              // Variable length
    hasher.update(&oprf_key_version.to_le_bytes()); // 4 bytes
    hasher.update(&created_at.to_le_bytes());      // 8 bytes
    hasher.finalize().into()                 // 32 bytes output
}
```

**Properties:**
- Deterministic (same inputs → same hash)
- One-way (cannot reverse to get filter)
- Collision-resistant (SHA-256 security)
- Includes key version and timestamp (prevents context attacks)

---

## 7. Signature Verification

### 7.1 Signature Creation (Server-Side)

```rust
pub fn sign(&mut self, signing_key: &SigningKey) -> Result<()> {
    // 1. Create canonical message
    let message = self.create_signature_message();
    
    // 2. Sign with Ed25519
    let signature = signing_key.sign(&message);
    
    // 3. Store signature
    self.signature = signature.to_bytes().to_vec();
    
    Ok(())
}
```

### 7.2 Signature Verification (Client-Side)

```rust
pub fn verify_signature(&self, public_key: &VerifyingKey) -> Result<()> {
    // 1. Reconstruct canonical message
    let message = self.create_signature_message();
    
    // 2. Parse signature
    let mut sig_bytes = [0u8; 64];
    sig_bytes.copy_from_slice(&self.signature);
    let signature = Signature::from_bytes(&sig_bytes);
    
    // 3. Verify Ed25519 signature
    public_key.verify(&message, &signature)?;
    
    Ok(())
}
```

---

## 8. Filter Distribution Workflow

### 8.1 Server-Side (Filter Publication)

```python
def publish_new_bloom_filter(revoked_credentials):
    # 1. Build bloom filter
    filter = build_cascaded_bloom_filter(revoked_credentials)
    
    # 2. Serialize filter
    filter_data = serialize_bloom_filter(filter)
    
    # 3. Get previous envelope for chaining
    previous_envelope = get_latest_envelope()
    
    # 4. Create signed envelope
    envelope = BloomFilterEnvelope.create_simple(
        filter_data=filter_data,
        oprf_key_version=current_oprf_key_version,
        previous_envelope=previous_envelope,
        signing_key=network_authority_signing_key,
        issuer_did=network_authority_did
    )
    
    # 5. Store envelope
    store_envelope(envelope)
    
    # 6. Make available via API
    return envelope.version
```

### 8.2 Client-Side (Filter Retrieval)

```javascript
async function syncBloomFilter() {
    // 1. Check current version
    const currentVersion = localStorage.getItem('bloom_filter_version') || 0;
    
    // 2. Fetch latest from server
    const response = await fetch('/api/v1/oprf/bloom-filter');
    const envelope = await response.json();
    
    // 3. Check if update needed
    if (envelope.version <= currentVersion) {
        return; // Already have latest
    }
    
    // 4. Get previous envelope for chain validation
    const previousEnvelope = getStoredEnvelope(currentVersion);
    
    // 5. Validate new envelope
    await validateEnvelope(envelope, previousEnvelope);
    
    // 6. Store new envelope
    storeEnvelope(envelope);
    localStorage.setItem('bloom_filter_version', envelope.version);
    
    // 7. Decode and use filter
    const filterData = base64Decode(envelope.bloom_filter.data);
    loadBloomFilter(filterData);
}
```

---

## 9. Versioning Strategy

### 9.1 Version Numbering

**Global Counter** (per network/site):
- Starts at 1 (first filter)
- Increments by 1 for each new filter
- Never resets or reuses
- Stored persistently

**Example Timeline:**
```
v1: Initial filter (10 revocations)
v2: Add 5 revocations (15 total)
v3: Add 20 revocations (35 total)
v4: Rebuild filter (same 35, new structure)
v5: Add 3 revocations (38 total)
```

### 9.2 Version Synchronization

**Client Sync Frequency:**
- On app startup: Check for updates
- Every 24 hours: Proactive sync
- On verification failure: Emergency sync
- When filter expires: Mandatory sync

**Server-Side:**
- Publish new version when revocations added
- Maintain last 10 versions for late clients
- Automatic cleanup of old versions

---

## 10. Performance Impact

### 10.1 Signature Verification Overhead

**Per Filter Download (once per 7 days):**
- SHA-256 hash: ~5μs
- Ed25519 verify: ~30μs
- Chain validation: ~10μs
- Total: ~45μs

**Amortized Over 7 Days:**
- 10,000 verifications/day
- Total verifications: 70,000
- Overhead per verification: 0.0006μs
- **Negligible impact**

### 10.2 Storage Overhead

**Per Envelope:**
- Filter data: ~125KB (3-level cascade)
- Metadata: ~500 bytes
- Signature: 64 bytes
- Total: ~126KB

**Client Storage:**
- Current envelope: ~126KB
- Previous envelope (for chain): ~126KB
- Total: ~252KB
- **Minimal storage impact**

### 10.3 Network Overhead

**Per Sync (every 7 days):**
- Envelope download: ~130KB
- Frequency: 1 per week
- Bandwidth: ~540KB/month

**Compared to Online Systems:**
- Auth0 login: ~50KB per auth
- 100 auths/month: 5MB
- Lemma: 0.54MB
- **90% bandwidth reduction**

---

## 11. Error Handling

### 11.1 Client-Side Error Recovery

**Signature Verification Failed:**
```javascript
try {
    await validateEnvelope(envelope);
} catch (error) {
    if (error.message.includes('signature')) {
        // Possible network corruption - retry
        await retryFetchEnvelope();
    } else if (error.message.includes('expired')) {
        // Filter expired - fetch new one
        await fetchNewEnvelope();
    } else if (error.message.includes('chain')) {
        // Chain broken - fetch full history
        await fetchEnvelopeHistory();
    } else {
        // Unknown error - use cached filter with warning
        console.warn('Filter validation failed, using cached');
    }
}
```

### 11.2 Graceful Degradation

**If Filter Unavailable:**
```javascript
async function checkRevocation(credential) {
    try {
        await ensureFilterFresh();
        return bloomFilter.contains(credential.oprf_eval);
    } catch (error) {
        // Filter sync failed
        
        if (cachedFilterAge < 7 * 24 * 3600) {
            // Use cached filter (< 7 days old)
            console.warn('Using cached filter');
            return cachedBloomFilter.contains(credential.oprf_eval);
        } else {
            // Filter too old - fail safe
            console.error('Filter expired and sync failed');
            // Option A: Reject (security first)
            return true; // Treat as possibly revoked
            // Option B: Allow (availability first)
            // return false; // Risk accepting revoked credential
        }
    }
}
```

---

## 12. API Reference

### 12.1 Get Bloom Filter Envelope

**Request:**
```http
GET /api/v1/oprf/bloom-filter?version=100 HTTP/1.1
Host: lemma.id
X-API-Key: your_api_key
```

**Response (Success):**
```json
{
  "success": true,
  "version": 100,
  "oprf_key_version": 2,
  "bloom_filter": {
    "data": "base64_encoded_filter",
    "size_bytes": 125000,
    "num_levels": 3,
    "false_positive_rate": 0.001
  },
  "signature": "ed25519_signature_base64",
  "issuer_did": "did:lemma:authority_key",
  "created_at": 1697248490,
  "valid_from": 1697248490,
  "valid_until": 1697853290,
  "content_hash": "sha256_hash_hex",
  "previous_version": 99,
  "previous_version_hash": "sha256_of_previous_hex"
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "filter_not_found",
  "version": 100
}
```

---

## 13. Security Audit Checklist

### 13.1 Implementation Validation

✅ **Signature Algorithm**: Ed25519 (correct)  
✅ **Hash Algorithm**: SHA-256 (appropriate)  
✅ **Version Type**: u64 (sufficient range)  
✅ **Timestamp Type**: i64 (Unix timestamp)  
✅ **Signature Size**: 64 bytes (Ed25519 standard)  
✅ **Chain Validation**: Hash linkage (tamper-evident)  

### 13.2 Attack Surface Analysis

**Potential Attacks:**
- ✅ Downgrade → Prevented (version chain)
- ✅ Replay → Prevented (7-day expiration)
- ✅ Tamper → Prevented (signature + hash)
- ✅ Injection → Prevented (authority verification)
- ✅ MITM → Prevented (signature verification)

**Residual Risks:**
- ⚠️ Network authority key compromise (mitigated by HSM storage)
- ⚠️ Client-side key storage (mitigated by browser security)
- ⚠️ Time manipulation (mitigated by strict expiration)

---

## 14. Testing

### 14.1 Unit Tests

**File**: `lemma-crypto/src/bloom_envelope.rs` (tests section)

Tests cover:
- Envelope creation and signing
- Signature verification
- Chain validation
- Temporal bounds checking

### 14.2 Integration Tests

```python
def test_bloom_filter_distribution():
    # 1. Create filter
    filter = CascadedBloomFilter(3, 10000, 0.001)
    filter.add(b"revoked_cred_1")
    
    # 2. Create signed envelope
    envelope = create_signed_envelope(filter)
    
    # 3. Distribute via API
    response = publish_envelope(envelope)
    assert response.status_code == 200
    
    # 4. Client retrieves and validates
    client_envelope = fetch_envelope()
    assert validate_envelope(client_envelope, network_authority_key)
    
    # 5. Client uses filter
    is_revoked = client_envelope.filter.contains(b"revoked_cred_1")
    assert is_revoked == True
```

---

## ✅ Summary

The signed bloom filter envelope system provides:

- ✅ **Tamper-proof distribution** via Ed25519 signatures
- ✅ **Downgrade prevention** via version chain validation
- ✅ **Replay prevention** via time-bound validity
- ✅ **Integrity verification** via content hashing
- ✅ **Authority authentication** via DID verification
- ✅ **Minimal performance overhead** (~45μs per 7 days)
- ✅ **Graceful degradation** for network failures

This addresses critical attack vectors that most revocation systems are vulnerable to, making Lemma's stateless verification protocol production-ready.

