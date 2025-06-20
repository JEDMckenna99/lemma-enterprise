# OPRF-Cascaded Bloom Filter Implementation Checklist

**Goal:** Replace fake byte pattern matching with real OPRF-cascaded bloom filter for production-grade offline revocation checking.

## 📋 **Phase 1: Dependencies & Setup**

### ✅ **1.1 Install Required Libraries**
```bash
# Python dependencies
pip install pybloom-live>=4.0.0
pip install cryptography>=41.0.0
pip install pycryptodome>=3.19.0

# For OPRF implementation
pip install ristretto255-python>=0.1.0  # Or equivalent OPRF library
```

### ✅ **1.2 Update requirements.txt**
```python
# Add to requirements.txt
pybloom-live==4.0.0
ristretto255-python==0.1.0
bitarray==2.8.3
mmh3==4.0.1  # For multiple hash functions
```

### ✅ **1.3 Verify Current Fake Implementation**
- [ ] Locate fake bloom filter code in `lemma/core/credential_service.py:1529`
- [ ] Locate fake bloom filter code in `static/js/lemma-offline-sdk.js:226`
- [ ] Document current behavior for testing comparison

## 📋 **Phase 2: OPRF Implementation**

### ✅ **2.1 Implement OPRF Server Component**
```python
# File: lemma/core/oprf_cascade.py
class OPRFCascadeManager:
    def __init__(self, secret_key=None):
        """Initialize OPRF with secret key for server operations"""
        pass
    
    def blind_credential_id(self, credential_id):
        """Client: Blind credential ID before sending to server"""
        pass
    
    def evaluate_oprf(self, blinded_input):
        """Server: Evaluate OPRF on blinded input"""
        pass
    
    def unblind_result(self, server_response, blind_factor):
        """Client: Unblind server response to get OPRF output"""
        pass
```

**Checklist:**
- [ ] Create `lemma/core/oprf_cascade.py`
- [ ] Implement OPRF key generation with ristretto255
- [ ] Implement client blinding operations
- [ ] Implement server evaluation (without learning inputs)
- [ ] Implement client unblinding
- [ ] Add OPRF key rotation mechanism
- [ ] Write unit tests for OPRF operations

### ✅ **2.2 Implement Real Bloom Filter Operations**
```python
# File: lemma/core/bloom_cascade.py
from pybloom_live import BloomFilter
import mmh3

class CascadedBloomFilter:
    def __init__(self, levels=3, capacity_per_level=100000, error_rate=0.01):
        """Initialize cascaded bloom filter with multiple levels"""
        self.levels = []
        for i in range(levels):
            # Each level has different capacity for optimization
            level_capacity = capacity_per_level // (2 ** i)
            bf = BloomFilter(capacity=level_capacity, error_rate=error_rate)
            self.levels.append(bf)
    
    def add_oprf_hash(self, oprf_output):
        """Add OPRF output to appropriate cascade level"""
        pass
    
    def check_oprf_hash(self, oprf_output):
        """Check if OPRF output exists in cascade"""
        pass
    
    def serialize(self):
        """Serialize cascade to bytes for transmission"""
        pass
    
    def deserialize(self, cascade_bytes):
        """Deserialize cascade from bytes"""
        pass
```

**Checklist:**
- [ ] Create `lemma/core/bloom_cascade.py`
- [ ] Implement 3-level cascaded bloom filter structure
- [ ] Add OPRF hash insertion with proper level selection
- [ ] Add OPRF hash checking across all levels
- [ ] Implement serialization/deserialization
- [ ] Add cascade optimization (level sizing)
- [ ] Write unit tests for bloom operations

## 📋 **Phase 3: Backend Integration**

### ✅ **3.1 Replace Fake Bloom Filter in credential_service.py**

**Current fake code to replace:**
```python
# Line 1529 - REMOVE THIS FAKE CODE
revoked = credential_hash[:8] in bloom_filter_bytes  # Simple byte search
```

**Replace with real implementation:**
```python
def check_revocation_offline(self, credential_id, offline_witness):
    """Real OPRF-cascaded bloom filter revocation checking"""
    try:
        # Get revocation snapshot
        revocation_snapshot = offline_witness.get('revocation_snapshot', {})
        cascade_data = revocation_snapshot.get('bloom_filter', '')
        
        if not cascade_data:
            return {'revoked': False, 'method': 'no_revocation_data'}
        
        # Deserialize cascaded bloom filter
        cascade = CascadedBloomFilter()
        cascade.deserialize(base64.b64decode(cascade_data))
        
        # Get OPRF output for this credential
        oprf_manager = OPRFCascadeManager()
        oprf_output = oprf_manager.get_cached_oprf_output(credential_id)
        
        if not oprf_output:
            # Need to compute OPRF (requires server call for full privacy)
            return {'revoked': False, 'method': 'oprf_cache_miss'}
        
        # Check against cascaded bloom filter
        revoked = cascade.check_oprf_hash(oprf_output)
        
        return {
            'revoked': revoked,
            'method': 'oprf_cascaded_bloom_filter',
            'cascade_levels': len(cascade.levels),
            'oprf_verified': True
        }
        
    except Exception as e:
        self.logger.error(f"OPRF cascade revocation check failed: {e}")
        return {'revoked': False, 'method': 'oprf_cascade_error'}
```

**Checklist:**
- [ ] Replace fake bloom filter in `check_revocation_offline()`
- [ ] Update `create_revocation_snapshot()` to use real cascade
- [ ] Update `create_compact_bloom_filter()` with real implementation
- [ ] Add OPRF cache management for offline operations
- [ ] Update credential issuance to include OPRF witnesses
- [ ] Add error handling for OPRF operations

## 📋 **Phase 4: Frontend JavaScript Implementation**

### ✅ **4.1 Replace Fake Bloom Filter in lemma-offline-sdk.js**

**Current fake code to replace:**
```javascript
// Lines 224-240 - REMOVE THIS FAKE CODE
// Simple bloom filter check (in production, use proper bloom filter implementation)
const hashBytes = new Uint8Array(credentialHash);
const filterBytes = new Uint8Array(bloomFilterBytes);

// Check if first 8 bytes of hash appear in filter
const searchPattern = hashBytes.slice(0, 8);
// ... fake pattern matching code
```

**Replace with real implementation:**
```javascript
class OPRFCascadeClient {
    constructor() {
        // Initialize OPRF client operations
    }
    
    async checkRevocationCascade(credentialId, cascadeData, oprfWitness) {
        try {
            // Deserialize cascaded bloom filter
            const cascade = this.deserializeCascade(cascadeData);
            
            // Get OPRF output from witness or compute
            const oprfOutput = await this.getOrComputeOPRFOutput(credentialId, oprfWitness);
            
            // Check against each cascade level
            for (let level = 0; level < cascade.levels.length; level++) {
                if (this.checkBloomFilter(cascade.levels[level], oprfOutput)) {
                    return {
                        revoked: true,
                        method: 'oprf_cascaded_bloom_filter',
                        detected_at_level: level
                    };
                }
            }
            
            return {
                revoked: false,
                method: 'oprf_cascaded_bloom_filter',
                levels_checked: cascade.levels.length
            };
            
        } catch (error) {
            console.error('OPRF cascade check failed:', error);
            return { revoked: false, method: 'oprf_cascade_error' };
        }
    }
    
    checkBloomFilter(bloomFilter, oprfOutput) {
        // Implement real bloom filter checking with multiple hash functions
        const hashes = this.computeBloomHashes(oprfOutput, bloomFilter.numHashes);
        
        for (const hash of hashes) {
            const bitIndex = hash % bloomFilter.bitArray.length;
            if (!bloomFilter.bitArray[bitIndex]) {
                return false;  // Definitely not in set
            }
        }
        
        return true;  // Probably in set (may be false positive)
    }
    
    computeBloomHashes(input, numHashes) {
        // Use multiple hash functions for bloom filter
        const hashes = [];
        for (let i = 0; i < numHashes; i++) {
            // Implement proper hash functions (e.g., MurmurHash variants)
            const hash = this.murmurHash3(input, i);
            hashes.push(hash);
        }
        return hashes;
    }
}
```

**Checklist:**
- [ ] Create `OPRFCascadeClient` class in JavaScript
- [ ] Replace fake pattern matching with real bloom filter math
- [ ] Implement multiple hash functions (MurmurHash3)
- [ ] Add cascade deserialization in JavaScript
- [ ] Implement OPRF output computation/caching
- [ ] Add proper bit array operations
- [ ] Write JavaScript unit tests

## 📋 **Phase 5: Testing & Validation**

### ✅ **5.1 Unit Tests**
```python
# File: tests/test_oprf_cascade.py
class TestOPRFCascade:
    def test_oprf_blinding_unblinding(self):
        """Test OPRF blind/unblind operations"""
        pass
    
    def test_cascaded_bloom_filter_operations(self):
        """Test bloom filter add/check operations"""
        pass
    
    def test_false_positive_rate(self):
        """Verify bloom filter false positive rate"""
        pass
    
    def test_cascade_serialization(self):
        """Test cascade serialize/deserialize"""
        pass
    
    def test_offline_revocation_with_oprf(self):
        """Test complete offline revocation flow"""
        pass
```

**Checklist:**
- [ ] Create `tests/test_oprf_cascade.py`
- [ ] Test OPRF operations (blind/evaluate/unblind)
- [ ] Test cascaded bloom filter operations
- [ ] Verify false positive rates are within bounds
- [ ] Test serialization/deserialization
- [ ] Test complete offline revocation workflow
- [ ] Add performance benchmarks
- [ ] Test with large revocation sets (100K+ entries)

## 📋 **Phase 6: Production Deployment**

### ✅ **6.1 Configuration Updates**
```python
# Add to app configuration
OPRF_CASCADE_ENABLED = True
OPRF_CASCADE_LEVELS = 3
OPRF_CASCADE_ERROR_RATE = 0.01
OPRF_KEY_ROTATION_DAYS = 30
OPRF_CACHE_SIZE_MB = 100
```

**Checklist:**
- [ ] Add OPRF cascade configuration options
- [ ] Update environment variables for production
- [ ] Add OPRF key management configuration
- [ ] Configure cascade update schedules
- [ ] Add monitoring and alerting for OPRF operations

### ✅ **6.2 Migration Strategy**
```python
def migrate_from_fake_to_real_oprf():
    """Migrate existing credentials from fake to real OPRF implementation"""
    # 1. Issue new credentials with real OPRF witnesses
    # 2. Mark old credentials for migration
    # 3. Provide fallback during transition period
    # 4. Complete migration and remove fake implementation
    pass
```

**Checklist:**
- [ ] Plan migration from fake to real implementation
- [ ] Create migration scripts for existing credentials
- [ ] Implement backward compatibility during transition
- [ ] Plan rollback strategy if issues occur
- [ ] Schedule production deployment window

## 📋 **Success Criteria**

### ✅ **Technical Success Metrics**
- [ ] False positive rate ≤ 1% for bloom filters
- [ ] OPRF operations complete in <100ms
- [ ] Cascade creation for 100K entries in <10 seconds
- [ ] Memory usage <1MB per 100K revoked credentials
- [ ] Zero false negatives (all revoked credentials detected)

### ✅ **Security Success Metrics**
- [ ] OPRF server never learns which credentials are checked
- [ ] Cascade cannot be reverse-engineered to reveal revoked IDs
- [ ] Key rotation works without breaking existing witnesses
- [ ] No timing side-channels in OPRF operations
- [ ] Cryptographic review passes security audit

---

## 🚨 **Critical Implementation Notes**

1. **OPRF Privacy Guarantee**: The server must NEVER learn which credential IDs are being checked
2. **Bloom Filter Math**: Must use proper hash functions and bit arrays, not byte pattern matching
3. **Cascade Optimization**: Different levels should have different capacities for efficiency
4. **Key Rotation**: OPRF keys must rotate without breaking existing offline witnesses
5. **Performance**: Real implementation must still achieve sub-100ms verification times

**Estimated Timeline:** 4-6 weeks for complete implementation with proper testing and security review.

**Priority Order:**
1. Phase 2: OPRF & Bloom Filter Implementation (core crypto)
2. Phase 3: Backend Integration (replace fake code)
3. Phase 4: Frontend JavaScript (client-side real implementation)
4. Phase 5: Testing & Validation (ensure correctness)
5. Phase 6: Production Deployment (migration strategy) 